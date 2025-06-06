import os
import cv2
import torch
import numpy as np
import supervision as sv
from PIL import Image
from sam2.build_sam import build_sam2_video_predictor, build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
# from utils2.track_utils import sample_points_from_masks
# from utils2.video_utils import create_video_from_images
from utils2.common_utils import CommonUtils
from utils2.mask_dictionary_model import MaskDictionaryModel, ObjectInfo
import json
import copy
import argparse  # argparseを追加

class VideoProcessor:
    def __init__(self, input_folder, output_dir="./outputs", device_id=0,camera_id=None):
        # 入力フォルダとデバイスの設定
        self.input_folder = input_folder
        self.output_dir = output_dir
        self.device_id = device_id
        self.camera_id = camera_id
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
        #フレーム間隔の変更2024.10.28 torisato
        self.step = 15  # Grounding DINOのフレーム間隔
        self.sam2_masks = MaskDictionaryModel()
        self.PROMPT_TYPE_FOR_VIDEO = "mask"
        #2024.10.29 torisato
        # self.objects_count = 0
        with open(str(self.camera_id)+"/last_object_count.txt", "r") as file:
            last_object_count = file.readline().strip()
        self.objects_count = int(last_object_count)
        self.text = "person."  # テキストプロンプト

    def setup_environment(self):
        # 自動キャストとデバイスプロパティの設定
        torch.autocast(device_type="cuda", dtype=torch.float16).__enter__()
        if torch.cuda.get_device_properties(self.device_id).major >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

    def initialize_models(self):
        # SAM2ビデオ予測器と画像予測器の初期化
        sam2_checkpoint = "./gsam2/checkpoints/sam2_hiera_large.pt"
        model_cfg = "sam2_hiera_l.yaml"
        self.video_predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
        sam2_image_model = build_sam2(model_cfg, sam2_checkpoint, device=self.device)
        self.image_predictor = SAM2ImagePredictor(sam2_image_model)

        # Grounding DINOモデルの初期化
        #2024.10.28 torisato
        # model_id = "IDEA-Research/grounding-dino-tiny"
        model_id = "IDEA-Research/grounding-dino-base"
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(self.device)

    def setup_directories(self):
        # 出力ディレクトリの作成
        CommonUtils.creat_dirs(self.output_dir)
        self.mask_data_dir = os.path.join(self.output_dir, "mask_data")
        self.json_data_dir = os.path.join(self.output_dir, "json_data")
        # self.result_dir = os.path.join(self.output_dir, "result")
        CommonUtils.creat_dirs(self.mask_data_dir)
        CommonUtils.creat_dirs(self.json_data_dir)
        # CommonUtils.creat_dirs(self.result_dir)
        # self.output_video_path = os.path.join(self.output_dir, "output.mp4")

    def get_frame_names(self):
        # フレーム名の取得とソート
        frame_names = [
            p for p in os.listdir(self.input_folder)
            if os.path.splitext(p)[-1].lower() in [".jpg", ".jpeg", ".png"]
        ]
        frame_names.sort(key=lambda p: int(os.path.splitext(p)[0]))
        return frame_names

    import time  # 処理時間測定用

    def process_frames(self):
        empty_mask_cache = {}

        for start_frame_idx in range(0, len(self.frame_names), self.step):
            start_step_time = time.time()  # ⏱️処理時間測定開始

            objects_found = False
            valid_image = None
            valid_results = None
            valid_idx = None

            for offset in range(self.step):
                current_idx = start_frame_idx + offset
                if current_idx >= len(self.frame_names):
                    break

                frame_name = self.frame_names[current_idx]
                img_path = os.path.join(self.input_folder, frame_name)
                image = Image.open(img_path).convert("RGB")

                inputs = self.processor(images=image, text=self.text, return_tensors="pt").to(self.device)
                with torch.no_grad():  # 推論最適化
                    outputs = self.grounding_model(**inputs)

                results = self.processor.post_process_grounded_object_detection(
                    outputs,
                    inputs.input_ids,
                    box_threshold=0.35,
                    text_threshold=0.25,
                    target_sizes=[image.size[::-1]],
                )

                if len(results[0]["boxes"]) > 0 and not (len(results[0]["boxes"]) == 1 and results[0]["scores"][0] < 0.7):
                    objects_found = True
                    valid_idx = current_idx
                    valid_image = image
                    valid_results = results
                    break

                self._save_empty_mask_and_json(frame_name, image.size, empty_mask_cache)

            if not objects_found:
                continue

            image = valid_image
            image_base_name = self.frame_names[valid_idx].split(".")[0]
            mask_dict = MaskDictionaryModel(promote_type=self.PROMPT_TYPE_FOR_VIDEO,
                                            mask_name=f"mask_{image_base_name}.npy")

            self.image_predictor.set_image(np.array(image))
            input_boxes = valid_results[0]["boxes"]
            OBJECTS = valid_results[0]["labels"]

            with torch.no_grad():  # 推論最適化
                masks, scores, logits = self.image_predictor.predict(
                    point_coords=None,
                    point_labels=None,
                    box=input_boxes,
                    multimask_output=False,
                )

            if masks.ndim == 2:
                masks = masks[None]
            elif masks.ndim == 4 and masks.shape[1] == 1:
                masks = masks.squeeze(1)

            mask_dict.add_new_frame_annotation(
                mask_list=torch.as_tensor(masks, device=self.device).detach(),
                box_list=torch.as_tensor(input_boxes, device=self.device).detach(),
                label_list=OBJECTS
            )

            self.objects_count = mask_dict.update_masks(
                tracking_annotation_dict=self.sam2_masks, iou_threshold=0.8, objects_count=self.objects_count
            )

            self.video_predictor.reset_state(self.inference_state)
            for obj_id, obj_info in mask_dict.labels.items():
                self.video_predictor.add_new_mask(self.inference_state, valid_idx, obj_id, obj_info.mask)

            for out_frame_idx, out_obj_ids, out_mask_logits in self.video_predictor.propagate_in_video(
                self.inference_state, max_frame_num_to_track=self.step, start_frame_idx=valid_idx
            ):
                frame_masks = MaskDictionaryModel()
                for i, obj_id in enumerate(out_obj_ids):
                    mask = (out_mask_logits[i] > 0.0)[0]
                    obj_info = ObjectInfo(instance_id=obj_id, mask=mask,
                                        class_name=mask_dict.get_target_class_name(obj_id))
                    obj_info.update_box()
                    image_base_name = self.frame_names[out_frame_idx].split(".")[0]
                    frame_masks.mask_name = f"mask_{image_base_name}.npy"
                    frame_masks.mask_height, frame_masks.mask_width = mask.shape
                    frame_masks.labels[obj_id] = obj_info

                self.sam2_masks = copy.deepcopy(frame_masks)
                self._save_mask_and_json(frame_masks)

            torch.cuda.empty_cache()  # メモリ最適化
            print(f"✅ フレーム {start_frame_idx} - 処理時間: {time.time() - start_step_time:.2f} 秒")


    def _save_empty_mask_and_json(self, frame_name, size, cache):
        base_name = frame_name.split(".")[0]
        if size not in cache:
            cache[size] = np.zeros((size[1], size[0]), dtype=np.uint16)
        np.save(os.path.join(self.mask_data_dir, f"mask_{base_name}.npy"), cache[size])
        with open(os.path.join(self.json_data_dir, f"mask_{base_name}.json"), "w") as f:
            json.dump({}, f)

    def _save_mask_and_json(self, frame_masks_info):
        mask_img = torch.zeros(frame_masks_info.mask_height, frame_masks_info.mask_width)
        for obj_id, obj_info in frame_masks_info.labels.items():
            mask_img[obj_info.mask] = obj_id
        np.save(os.path.join(self.mask_data_dir, frame_masks_info.mask_name), mask_img.numpy().astype(np.uint16))
        json_path = os.path.join(self.json_data_dir, frame_masks_info.mask_name.replace(".npy", ".json"))
        with open(json_path, "w") as f:
            json.dump(frame_masks_info.to_dict(), f)



    # def draw_results_and_save_video(self):
    #     # 結果の描画とビデオの保存
    #     CommonUtils.draw_masks_and_box_with_supervision(
    #         self.input_folder, self.mask_data_dir, self.json_data_dir, self.result_dir
    #     )
    #     create_video_from_images(self.result_dir, self.output_video_path, frame_rate=30)

    def run(self):
        # 全体の処理を実行
        self.process_frames()
        #2024.10.29 torisato
        with open(str(self.camera_id)+"/last_object_count.txt", "w") as file:
            file.write(str(self.objects_count))
        #結果の描画とビデオの保存 2024.10.28 torisato
        # self.draw_results_and_save_video()


if __name__ == "__main__":
    # 引数パーサの設定
    # parser = argparse.ArgumentParser(description="Video Processor Script")
    # parser.add_argument(
    #     "--input_folder",
    #     type=str,
    #     required=True,
    #     help="入力フレーム画像が保存されているフォルダのパス"
    # )
    # parser.add_argument(
    #     "--output_dir",
    #     type=str,
    #     default="./outputs",
    #     help="出力を保存するフォルダのパス"
    # )
    # parser.add_argument(
    #     "--device_id",
    #     type=int,
    #     default=0,
    #     help="使用するCUDAデバイスのID（デフォルトは0）"
    # )
    # parser.add_argument('--camera_id', type=int, required=True, help='カメラのid')
    # args = parser.parse_args()

    # VideoProcessorのインスタンスを作成し、処理を実行
    # processor = VideoProcessor(
    #     input_folder=args.input_folder,
    #     output_dir=args.output_dir,
    #     device_id=args.device_id,
    #     camera_id=args.camera_id
    # )
    # processor.run()
    print("a")

    import time
    start_time = time.time()  # 開始時刻

    processor = VideoProcessor(
        input_folder="./1/134920000",
        output_dir="./a_torisato_1349",
        device_id=0,
        camera_id=1
    )

    end_time = time.time()  # 終了時刻

    elapsed_time = end_time - start_time
    print(f"実行時間: {elapsed_time:.2f} 秒")

    start_time = time.time()  # 開始時刻
    processor.run()

    end_time = time.time()  # 終了時刻

    elapsed_time = end_time - start_time
    print(f"完遂時間: {elapsed_time:.2f} 秒")