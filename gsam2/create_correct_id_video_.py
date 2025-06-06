import os
import cv2
import torch
import numpy as np
import supervision as sv
from PIL import Image
from sam2.build_sam import build_sam2_video_predictor, build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection 
from utils.track_utils import sample_points_from_masks
from utils.video_utils import create_video_from_images
from utils.common_utils import CommonUtils
from utils.mask_dictionary_model import MaskDictionaryModel, ObjectInfo
import json
import copy

class VideoProcessor:
    def __init__(self, input_folder, output_dir="./outputs", device_id=0):
        # 入力フォルダとデバイスの設定
        self.input_folder = input_folder
        self.output_dir = output_dir
        self.device_id = device_id
        self.device = f"cuda:{device_id}" if torch.cuda.is_available() else "cpu"
        torch.cuda.set_device(device_id)
        
        # 環境設定とモデルの初期化
        self.setup_environment()
        self.initialize_models()
        self.setup_directories()
        
        # その他の初期設定
        self.frame_names = self.get_frame_names()
        self.inference_state = self.video_predictor.init_state(
            video_path=self.input_folder, offload_video_to_cpu=True, async_loading_frames=True
        )
        self.step = 20  # Grounding DINOのフレーム間隔
        self.sam2_masks = MaskDictionaryModel()
        self.PROMPT_TYPE_FOR_VIDEO = "mask"
        self.objects_count = 0
        self.text = "person."  # テキストプロンプト

    def setup_environment(self):
        # 自動キャストとデバイスプロパティの設定
        torch.autocast(device_type="cuda", dtype=torch.float16).__enter__()
        if torch.cuda.get_device_properties(self.device_id).major >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

    def initialize_models(self):
        # SAM2ビデオ予測器と画像予測器の初期化
        sam2_checkpoint = "./checkpoints/sam2_hiera_large.pt"
        model_cfg = "sam2_hiera_l.yaml"
        self.video_predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
        sam2_image_model = build_sam2(model_cfg, sam2_checkpoint, device=self.device)
        self.image_predictor = SAM2ImagePredictor(sam2_image_model)
        
        # Grounding DINOモデルの初期化
        model_id = "IDEA-Research/grounding-dino-tiny"
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(self.device)

    def setup_directories(self):
        # 出力ディレクトリの作成
        CommonUtils.creat_dirs(self.output_dir)
        self.mask_data_dir = os.path.join(self.output_dir, "mask_data")
        self.json_data_dir = os.path.join(self.output_dir, "json_data")
        self.result_dir = os.path.join(self.output_dir, "result")
        CommonUtils.creat_dirs(self.mask_data_dir)
        CommonUtils.creat_dirs(self.json_data_dir)
        CommonUtils.creat_dirs(self.result_dir)
        self.output_video_path = os.path.join(self.output_dir, "output.mp4")

    def get_frame_names(self):
        # フレーム名の取得とソート
        frame_names = [
            p for p in os.listdir(self.input_folder)
            if os.path.splitext(p)[-1].lower() in [".jpg", ".jpeg", ".png"]
        ]
        frame_names.sort(key=lambda p: int(os.path.splitext(p)[0]))
        return frame_names

    def process_frames(self):
        print("総フレーム数:", len(self.frame_names))
        for start_frame_idx in range(0, len(self.frame_names), self.step):
            print("処理中のフレームインデックス:", start_frame_idx)
            img_path = os.path.join(self.input_folder, self.frame_names[start_frame_idx])
            image = Image.open(img_path)
            image_base_name = self.frame_names[start_frame_idx].split(".")[0]
            mask_dict = MaskDictionaryModel(
                promote_type=self.PROMPT_TYPE_FOR_VIDEO, mask_name=f"mask_{image_base_name}.npy"
            )

            # Grounding DINOでの物体検出
            inputs = self.processor(images=image, text=self.text, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.grounding_model(**inputs)
            results = self.processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                box_threshold=0.25,
                text_threshold=0.25,
                target_sizes=[image.size[::-1]]
            )

            # SAM画像予測器でのマスク生成
            self.image_predictor.set_image(np.array(image.convert("RGB")))
            input_boxes = results[0]["boxes"]
            OBJECTS = results[0]["labels"]
            masks, scores, logits = self.image_predictor.predict(
                point_coords=None,
                point_labels=None,
                box=input_boxes,
                multimask_output=False,
            )
            if masks.ndim == 2:
                masks = masks[None]
                scores = scores[None]
                logits = logits[None]
            elif masks.ndim == 4:
                masks = masks.squeeze(1)

            # マスクの登録
            if mask_dict.promote_type == "mask":
                mask_dict.add_new_frame_annotation(
                    mask_list=torch.tensor(masks).to(self.device),
                    box_list=torch.tensor(input_boxes),
                    label_list=OBJECTS
                )
            else:
                raise NotImplementedError("SAM 2ビデオ予測器はマスクプロンプトのみサポートしています")

            # マスクの伝播
            self.objects_count = mask_dict.update_masks(
                tracking_annotation_dict=self.sam2_masks, iou_threshold=0.8, objects_count=self.objects_count
            )
            print("オブジェクト数:", self.objects_count)
            self.video_predictor.reset_state(self.inference_state)
            if len(mask_dict.labels) == 0:
                print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。スキップします。")
                continue
            self.video_predictor.reset_state(self.inference_state)

            for object_id, object_info in mask_dict.labels.items():
                self.video_predictor.add_new_mask(
                    self.inference_state,
                    start_frame_idx,
                    object_id,
                    object_info.mask,
                )

            # 各フレームのマスクを保存
            video_segments = {}
            for out_frame_idx, out_obj_ids, out_mask_logits in self.video_predictor.propagate_in_video(
                self.inference_state, max_frame_num_to_track=self.step, start_frame_idx=start_frame_idx
            ):
                frame_masks = MaskDictionaryModel()
                for i, out_obj_id in enumerate(out_obj_ids):
                    out_mask = (out_mask_logits[i] > 0.0)
                    object_info = ObjectInfo(
                        instance_id=out_obj_id,
                        mask=out_mask[0],
                        class_name=mask_dict.get_target_class_name(out_obj_id)
                    )
                    object_info.update_box()
                    frame_masks.labels[out_obj_id] = object_info
                    image_base_name = self.frame_names[out_frame_idx].split(".")[0]
                    frame_masks.mask_name = f"mask_{image_base_name}.npy"
                    frame_masks.mask_height = out_mask.shape[-2]
                    frame_masks.mask_width = out_mask.shape[-1]

                video_segments[out_frame_idx] = frame_masks
                self.sam2_masks = copy.deepcopy(frame_masks)

            print("ビデオセグメント数:", len(video_segments))

            # マスクとJSONファイルの保存
            for frame_idx, frame_masks_info in video_segments.items():
                mask = frame_masks_info.labels
                mask_img = torch.zeros(frame_masks_info.mask_height, frame_masks_info.mask_width)
                for obj_id, obj_info in mask.items():
                    mask_img[obj_info.mask == True] = obj_id

                mask_img = mask_img.numpy().astype(np.uint16)
                np.save(os.path.join(self.mask_data_dir, frame_masks_info.mask_name), mask_img)

                json_data = frame_masks_info.to_dict()
                json_data_path = os.path.join(
                    self.json_data_dir, frame_masks_info.mask_name.replace(".npy", ".json")
                )
                with open(json_data_path, "w") as f:
                    json.dump(json_data, f)

    def draw_results_and_save_video(self):
        # 結果の描画とビデオの保存
        CommonUtils.draw_masks_and_box_with_supervision(
            self.input_folder, self.mask_data_dir, self.json_data_dir, self.result_dir
        )
        create_video_from_images(self.result_dir, self.output_video_path, frame_rate=30)

    def run(self):
        # 全体の処理を実行
        self.process_frames()
        self.draw_results_and_save_video()


if __name__ == "__main__":
    input_folder = "notebooks/videos/images"
    mask_data_dir = "./outputs/mask_data"  # マスクが保存されている元のディレクトリ
    json_data_dir = "./outputs/corrected_jsons"  # JSONデータが保存されている元のディレクトリ
    result_dir = "./outputs/result2"  # 結果を保存するディレクトリ
    output_video_path = "./outputs/output2.mp4"
    def draw_results_and_save_video():
        # 結果の描画とビデオの保存
        CommonUtils.draw_masks_and_box_with_supervision(
            input_folder, mask_data_dir, json_data_dir, result_dir
        )
        create_video_from_images(result_dir, output_video_path, frame_rate=5)
    draw_results_and_save_video()