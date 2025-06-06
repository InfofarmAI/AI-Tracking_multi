"""
gsam2_c-idv2.py

このスクリプトは、監視カメラ等の静止フレーム画像から人物を検出し、検出結果をマスクおよびJSON形式で保存する処理を行います。
SAM2（Segment Anything Model 2）および Grounding DINO を用いて、セマンティックセグメンテーションと物体検出を統合し、フレーム内の人物オブジェクトを自動で識別・追跡します。

## 主な機能

- 指定された入力フォルダ内の画像フレームを対象に、一定間隔でフレームを抽出
- Grounding DINO により人物（"person"）のバウンディングボックスを検出
- SAM2 によりセグメンテーションマスクを生成
- 検出オブジェクトがない場合は空のマスク・空のJSONファイルを自動生成
- オブジェクトを一意に識別し、マスクをフレーム間で伝播・追跡
- 検出・追跡結果を `.npy`（マスク）および `.json`（属性情報）として保存
- オブジェクト数を `last_object_count.txt` に記録・更新

## 使用モデル
- Grounding DINO Base: Zero-shot Object Detectionモデル
- SAM2: Hierarchical Mask Propagationに対応した高性能セグメンテーションモデル

## 実行方法（CLI引数）
```bash
python gsam2_c-idv2.py \
  --input_folder ./frames/134920000 \
  --output_dir ./outputs \
  --device_id 0 \
  --camera_id 1

引数:
    --input_folder (str, 必須): 処理対象のフレーム画像が保存されたフォルダ
    --output_dir (str, 任意): 出力ファイル（マスク/JSON）の保存先ディレクトリ（デフォルト: ./outputs）
    --device_id (int, 任意): 使用するCUDAデバイスID（デフォルト: 0）
    --camera_id (int, 必須): カメラ識別用のID。保存ファイルや状態管理に使用されます。

出力:
    ./outputs/mask_data/: フレームごとのマスクファイル（.npy）
    ./outputs/json_data/: マスクに対応する属性情報（.json）
    <camera_id>/last_object_count.txt: オブジェクト識別IDのカウンタ（状態保持）

注意事項:
    SAM2とGrounding DINOのチェックポイントおよび設定ファイルは、./gsam2/checkpoints/ およびルートディレクトリに適切に配置されている必要があります。
    CUDAデバイスが使用可能である必要があります（GPU推論を前提としています）。
    フレーム間隔（step=15）ごとに推論を行います。

作成日：2025年5月
作成者：インフォファーム
"""

import os
import cv2
import torch
import numpy as np
import supervision as sv
from PIL import Image
from sam2.build_sam import build_sam2_video_predictor, build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
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
        with open(os.path.join(str(self.camera_id), "last_object_count.txt"), "r") as file:
            last_object_count = file.readline().strip()
        self.objects_count = int(last_object_count)
        self.text = "person."  # テキストプロンプト

    def setup_environment(self):
        """
        CUDA環境の設定を行う。

        - 半精度 (float16) 自動キャストを有効にしてメモリ効率を向上。
        - 対象GPU（Compute Capability 8.0以上）の場合、TensorFloat-32（TF32）演算を許可し、学習・推論の速度を改善。
        """
        # 自動キャストとデバイスプロパティの設定
        torch.autocast(device_type="cuda", dtype=torch.float16).__enter__()
        if torch.cuda.get_device_properties(self.device_id).major >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

    def initialize_models(self):
        """
        使用する各AIモデル（SAM2、Grounding DINO）を初期化する。

        - SAM2 モデルを動画・画像用にロードして、それぞれ `video_predictor` と `image_predictor` に格納。
        - Grounding DINO のベースモデルをロードし、オブジェクト検出のための `processor` と `grounding_model` をセットアップ。

        使用モデル:
            - SAM2 (GSAM2)
            - Grounding DINO ("IDEA-Research/grounding-dino-base")
        """
        # SAM2ビデオ予測器と画像予測器の初期化
        # sam2_checkpoint = "./gsam2/checkpoints/sam2_hiera_large.pt"
        # model_cfg = "sam2_hiera_l.yaml"
        #TODO モデルを2.1のものを使用するときは、「gsam2/sam2/build_sam.pyのコメントアウトを修正する」
        sam2_checkpoint = "./gsam2/checkpoints/sam2.1_hiera_large.pt"
        model_cfg = "sam2.1_hiera_l.yaml"
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
        """
        出力結果を保存するための各ディレクトリを作成する。

        - `mask_data_dir`: セグメンテーションマスク画像の保存先
        - `json_data_dir`: 推論結果（座標など）のJSONファイル保存先
        - `output_video_path`: 最終的な出力動画（MP4）のパスを定義

        備考:
            必要なディレクトリが存在しない場合は自動的に作成されます。
        """
        # 出力ディレクトリの作成
        CommonUtils.creat_dirs(self.output_dir)
        self.mask_data_dir = os.path.join(self.output_dir, "mask_data")
        self.json_data_dir = os.path.join(self.output_dir, "json_data")
        # self.result_dir = os.path.join(self.output_dir, "result")
        CommonUtils.creat_dirs(self.mask_data_dir)
        CommonUtils.creat_dirs(self.json_data_dir)
        # CommonUtils.creat_dirs(self.result_dir)
        self.output_video_path = os.path.join(self.output_dir, "output.mp4")

    def get_frame_names(self):
        """フレーム名の取得とソート"""
        frame_names = [
            p for p in os.listdir(self.input_folder)
            if os.path.splitext(p)[-1].lower() in [".jpg", ".jpeg", ".png"]
        ]
        frame_names.sort(key=lambda p: int(os.path.splitext(p)[0]))
        return frame_names

    # def process_frames(self):
    #     print("総フレーム数:", len(self.frame_names))
    #     for start_frame_idx in range(0, len(self.frame_names), self.step):
    #         exit_outer_loop = False
    #         print("処理中のフレームインデックス:", start_frame_idx)
    #         img_path = os.path.join(self.input_folder, self.frame_names[start_frame_idx])
    #         image = Image.open(img_path)
    #         image_base_name = self.frame_names[start_frame_idx].split(".")[0]
    #         mask_dict = MaskDictionaryModel(
    #             promote_type=self.PROMPT_TYPE_FOR_VIDEO, mask_name=f"mask_{image_base_name}.npy"
    #         )
    #         print("image_base_name",image_base_name)

    #         # Grounding DINOでの物体検出
    #         inputs = self.processor(images=image, text=self.text, return_tensors="pt").to(self.device)
    #         with torch.no_grad():
    #             outputs = self.grounding_model(**inputs)
    #         results = self.processor.post_process_grounded_object_detection(
    #             outputs,
    #             inputs.input_ids,
    #             box_threshold=0.35,
    #             text_threshold=0.25,
    #             target_sizes=[image.size[::-1]]
    #         )
    #         print(results)

    #         # if len(results[0]["boxes"]) == 0:
    #         #     print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。空のマスクファイルとJSONファイルを作成します。")
    #         #     # 空のマスクとJSONファイルを作成
    #         #     empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 画像サイズに合わせて空のマスクを作成
    #         #     np.save(os.path.join(self.mask_data_dir, mask_dict.mask_name), empty_mask)
    #         #     # JSONファイルを空の辞書として保存
    #         #     json_data = {}
    #         #     json_data_path = os.path.join(
    #         #         self.json_data_dir, mask_dict.mask_name.replace(".npy", ".json")
    #         #     )
    #         #     with open(json_data_path, "w") as f:
    #         #         json.dump(json_data, f)
    #         #         # print("mask_dict.mask_name",mask_dict.mask_name)
    #         #     continue  # 次のフレームへ移る
    #         # counter=20
    #         # if len(results[0]["boxes"]) == 0:
    #         #     counter-=1
    #         #     print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。空のマスクファイルとJSONファイルを作成します。")
    #         #     # 空のマスクとJSONファイルを作成
    #         #     empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 画像サイズに合わせて空のマスクを作成
    #         #     np.save(os.path.join(self.mask_data_dir, mask_dict.mask_name), empty_mask)
    #         #     # JSONファイルを空の辞書として保存
    #         #     json_data = {}
    #         #     json_data_path = os.path.join(
    #         #         self.json_data_dir, mask_dict.mask_name.replace(".npy", ".json")
    #         #     )
    #         #     with open(json_data_path, "w") as f:
    #         #         json.dump(json_data, f)
    #         #     for i in range(self.step-1):
    #         #         if  start_frame_idx+1+i > len(self.frame_names)-5:
    #         #             exit_outer_loop=True
    #         #             break
    #         #         img_path = os.path.join(self.input_folder, self.frame_names[start_frame_idx+1+i])
    #         #         image = Image.open(img_path)
    #         #         image_base_name = self.frame_names[start_frame_idx+1+i].split(".")[0]
    #         #         mask_dict = MaskDictionaryModel(
    #         #             promote_type=self.PROMPT_TYPE_FOR_VIDEO, mask_name=f"mask_{image_base_name}.npy"
    #         #         )
    #         #         print("image_base_name",image_base_name)

    #         #         # Grounding DINOでの物体検出
    #         #         inputs = self.processor(images=image, text=self.text, return_tensors="pt").to(self.device)
    #         #         with torch.no_grad():
    #         #             outputs = self.grounding_model(**inputs)
    #         #         results = self.processor.post_process_grounded_object_detection(
    #         #             outputs,
    #         #             inputs.input_ids,
    #         #             box_threshold=0.35,
    #         #             text_threshold=0.25,
    #         #             target_sizes=[image.size[::-1]]
    #         #         )
    #         #         if len(results[0]["boxes"]) == 0:
    #         #             counter-=1
    #         #             print(f"フレーム{start_frame_idx+1+i}で検出されたオブジェクトがありません。空のマスクファイルとJSONファイルを作成します。")
    #         #             # 空のマスクとJSONファイルを作成
    #         #             empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 画像サイズに合わせて空のマスクを作成
    #         #             np.save(os.path.join(self.mask_data_dir, mask_dict.mask_name), empty_mask)
    #         #             # JSONファイルを空の辞書として保存
    #         #             json_data = {}
    #         #             json_data_path = os.path.join(
    #         #                 self.json_data_dir, mask_dict.mask_name.replace(".npy", ".json")
    #         #             )
    #         #             with open(json_data_path, "w") as f:
    #         #                 json.dump(json_data, f)
    #         #             if i==self.step-2:
    #         #                 exit_outer_loop=True
    #         #         else:
    #         #             print("途中で発見")
    #         #             break
    #         # if exit_outer_loop:
    #         #     print("次の処理")
    #         #     continue
    #                 # print("mask_dict.mask_name",mask_dict.mask_name)
    #                 #continue  # 次のフレームへ移る
    #         # if len(results[0]["boxes"]) == 0:
    #         #     print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。空のマスクファイルとJSONファイルを作成します。")
    #         #     # 空のマスクとJSONファイルを作成 (20個分)
    #         #     for i in range(self.step):
    #         #         current_frame_idx = start_frame_idx + i
    #         #         if current_frame_idx >= len(self.frame_names):
    #         #             break  # 範囲外の場合は終了

    #         #         current_image_base_name = self.frame_names[current_frame_idx].split(".")[0]
    #         #         empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 画像サイズに合わせて空のマスクを作成
    #         #         empty_mask_path = os.path.join(self.mask_data_dir, f"mask_{current_image_base_name}.npy")
    #         #         np.save(empty_mask_path, empty_mask)

    #         #         # 空のJSONファイルを作成
    #         #         json_data = {}
    #         #         json_data_path = os.path.join(
    #         #             self.json_data_dir, f"mask_{current_image_base_name}.json"
    #         #         )
    #         #         with open(json_data_path, "w") as f:
    #         #             json.dump(json_data, f)
    #         #             print(f"空のマスクとJSONを保存: {empty_mask_path}, {json_data_path}")
    #         #     continue  # 次のフレームへ移る
    #         if len(results[0]["boxes"]) == 0:
    #             print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。空のマスクファイルとJSONファイルを作成します。")
    #             empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)
    #             np.save(os.path.join(self.mask_data_dir, mask_dict.mask_name), empty_mask)
    #             json_data = {}
    #             json_data_path = os.path.join(self.json_data_dir, mask_dict.mask_name.replace(".npy", ".json"))
    #             with open(json_data_path, "w") as f:
    #                 json.dump(json_data, f)
    #             continue  # 次のフレームへ進む

    #         # SAM画像予測器でのマスク生成
    #         self.image_predictor.set_image(np.array(image.convert("RGB")))
    #         input_boxes = results[0]["boxes"]

    #         if input_boxes is None or len(input_boxes) == 0:
    #             print(f"フレーム{start_frame_idx}でバウンディングボックスがありません。スキップします。")
    #             continue  # 次のフレームへ進む

    #         # # SAM画像予測器でのマスク生成
    #         # self.image_predictor.set_image(np.array(image.convert("RGB")))
    #         # input_boxes = results[0]["boxes"]
    #         OBJECTS = results[0]["labels"]
    #         print("input_boxes",input_boxes)
    #         masks, scores, logits = self.image_predictor.predict(
    #             point_coords=None,
    #             point_labels=None,
    #             box=input_boxes,
    #             multimask_output=False,
    #         )
    #         if masks.ndim == 2:
    #             masks = masks[None]
    #             scores = scores[None]
    #             logits = logits[None]
    #         elif masks.ndim == 4:
    #             masks = masks.squeeze(1)

    #         # マスクの登録
    #         if mask_dict.promote_type == "mask":
    #             mask_dict.add_new_frame_annotation(
    #                 mask_list=torch.tensor(masks).to(self.device),
    #                 box_list=torch.tensor(input_boxes),
    #                 label_list=OBJECTS
    #             )
    #         else:
    #             raise NotImplementedError("SAM 2ビデオ予測器はマスクプロンプトのみサポートしています")

    #         # マスクの伝播
    #         self.objects_count = mask_dict.update_masks(
    #             tracking_annotation_dict=self.sam2_masks, iou_threshold=0.8, objects_count=self.objects_count
    #         )
    #         print("オブジェクト数:", self.objects_count)
    #         self.video_predictor.reset_state(self.inference_state)
    #         if len(mask_dict.labels) == 0:
    #             print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。スキップします。")
    #             continue
    #         self.video_predictor.reset_state(self.inference_state)

    #         for object_id, object_info in mask_dict.labels.items():
    #             self.video_predictor.add_new_mask(
    #                 self.inference_state,
    #                 start_frame_idx,
    #                 object_id,
    #                 object_info.mask,
    #             )

    #         # 各フレームのマスクを保存
    #         video_segments = {}
    #         for out_frame_idx, out_obj_ids, out_mask_logits in self.video_predictor.propagate_in_video(
    #             self.inference_state, max_frame_num_to_track=self.step, start_frame_idx=start_frame_idx
    #         ):
    #             frame_masks = MaskDictionaryModel()
    #             for i, out_obj_id in enumerate(out_obj_ids):
    #                 out_mask = (out_mask_logits[i] > 0.0)
    #                 object_info = ObjectInfo(
    #                     instance_id=out_obj_id,
    #                     mask=out_mask[0],
    #                     class_name=mask_dict.get_target_class_name(out_obj_id)
    #                 )
    #                 object_info.update_box()
    #                 image_base_name = self.frame_names[out_frame_idx].split(".")[0]
    #                 frame_masks.mask_name = f"mask_{image_base_name}.npy"
    #                 frame_masks.mask_height = out_mask.shape[-2]
    #                 frame_masks.mask_width = out_mask.shape[-1]
    #                 frame_masks.labels[out_obj_id] = object_info

    #             video_segments[out_frame_idx] = frame_masks
    #             self.sam2_masks = copy.deepcopy(frame_masks)

    #         print("ビデオセグメント数:", len(video_segments))

    #         # マスクとJSONファイルの保存
    #         for frame_idx, frame_masks_info in video_segments.items():
    #             mask = frame_masks_info.labels
    #             mask_img = torch.zeros(frame_masks_info.mask_height, frame_masks_info.mask_width)
    #             for obj_id, obj_info in mask.items():
    #                 mask_img[obj_info.mask == True] = obj_id

    #             mask_img = mask_img.numpy().astype(np.uint16)
    #             np.save(os.path.join(self.mask_data_dir, frame_masks_info.mask_name), mask_img)

    #             json_data = frame_masks_info.to_dict()
    #             json_data_path = os.path.join(
    #                 self.json_data_dir, frame_masks_info.mask_name.replace(".npy", ".json")
    #             )
    #             with open(json_data_path, "w") as f:
    #                 json.dump(json_data, f)
                    # print("mask_dict.mask_name",mask_dict.mask_name)
    def process_frames(self):
        """
        動画フレーム群に対してオブジェクト検出・マスク生成・マスク伝播処理を実行し、マスクとJSONファイルを出力する。

        この処理では以下を行う:
        1. 指定ステップ間隔でフレームを読み込み、Grounding DINO によるオブジェクト検出を実施。
        2. 検出結果があれば、そのフレームを基点に SAM2 の画像予測器でマスクを生成。
        3. 得られたマスクを基に、SAM2 のビデオ予測器で以降のフレームへマスクを伝播。
        4. 各フレームごとに `.npy`（マスク画像）と `.json`（インスタンス情報）を保存。

        処理詳細:
            - `self.step` のステップごとに処理をスキップしつつ、指定条件で再試行。
            - 検出できなかった場合は、空のマスク・JSONを保存。
            - マスクは `self.mask_data_dir`、JSONは `self.json_data_dir` に保存される。
            - `self.sam2_masks` は前回のマスク情報として更新され、次回以降の処理に活用される。

        生成ファイル:
            - `mask_*.npy`: マスクデータ（各ピクセルに object_id が格納された NumPy 配列）
            - `mask_*.json`: オブジェクトの位置や ID、クラス名などを含むメタ情報ファイル

        要件:
            - `self.frame_names`, `self.input_folder`, `self.device`, `self.image_predictor`, `self.grounding_model`,
            `self.processor`, `self.video_predictor`, `self.PROMPT_TYPE_FOR_VIDEO`, `self.inference_state` などの事前定義が必要。

        注意:
            - オブジェクトが検出されない場合、空のファイルで出力される。
            - Grounding DINO の検出信頼度やマスク伝播の閾値 (IOUなど) はコード内で固定値として設定されている。

        """
        # print("総フレーム数:", len(self.frame_names))
        for start_frame_idx in range(0, len(self.frame_names), self.step):
            # print("処理中のフレームインデックス:", start_frame_idx)
            img_path = os.path.join(self.input_folder, self.frame_names[start_frame_idx])
            image = Image.open(img_path)
            image_base_name = self.frame_names[start_frame_idx].split(".")[0]
            mask_dict = MaskDictionaryModel(
                promote_type=self.PROMPT_TYPE_FOR_VIDEO, mask_name=f"mask_{image_base_name}.npy"
            )

            # 初期フレームでGrounding DINOを実行
            objects_found = False
            for frame_offset in range(self.step):  # 最大self.stepフレームを確認
                current_frame_idx = start_frame_idx + frame_offset
                if current_frame_idx >= len(self.frame_names):
                    break  # フレーム範囲を超えた場合

                img_path = os.path.join(self.input_folder, self.frame_names[current_frame_idx])
                image = Image.open(img_path)
                inputs = self.processor(images=image, text=self.text, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    outputs = self.grounding_model(**inputs)
                results = self.processor.post_process_grounded_object_detection(
                    outputs,
                    inputs.input_ids,
                    box_threshold=0.35,
                    text_threshold=0.25,
                    target_sizes=[image.size[::-1]],
                )
                if len(results[0]["boxes"]) > 0:  # オブジェクトを検出した場合
                    # print(results[0],current_frame_idx)
                    box = results[0]["boxes"][0]  # 最初のボックスを取得
                    height = box[3] - box[1]  # y_max - y_min

                    if len(results[0]["boxes"]) == 1 and results[0]["scores"][0] < 0.7:
                    # if len(results[0]["boxes"]) == 1 and results[0]["scores"][0] < 0.5 and height < 40:
                        # print(f"フレーム{current_frame_idx}でオブジェクトが検出されませんでした")

                        # オブジェクトが検出されなかった場合、空のJSONとマスクを作成
                        current_image_base_name = self.frame_names[current_frame_idx].split(".")[0]
                        empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 空のマスク
                        empty_mask_path = os.path.join(self.mask_data_dir, f"mask_{current_image_base_name}.npy")
                        np.save(empty_mask_path, empty_mask)

                        # 空のJSONファイルを作成
                        json_data = {}
                        json_data_path = os.path.join(
                            self.json_data_dir, f"mask_{current_image_base_name}.json"
                        )
                        with open(json_data_path, "w") as f:
                            json.dump(json_data, f)
                        # print(f"空のマスクとJSONを保存: {empty_mask_path}, {json_data_path}")
                    else:
                        # print(f"フレーム{current_frame_idx}でオブジェクトを検出しました")
                        objects_found = True
                        start_frame_idx = current_frame_idx  # 検出フレームを新しい基点として設定
                        break
                else:
                    # print(f"フレーム{current_frame_idx}でオブジェクトが検出されませんでした")

                    # オブジェクトが検出されなかった場合、空のJSONとマスクを作成
                    current_image_base_name = self.frame_names[current_frame_idx].split(".")[0]
                    empty_mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint16)  # 空のマスク
                    empty_mask_path = os.path.join(self.mask_data_dir, f"mask_{current_image_base_name}.npy")
                    np.save(empty_mask_path, empty_mask)

                    # 空のJSONファイルを作成
                    json_data = {}
                    json_data_path = os.path.join(
                        self.json_data_dir, f"mask_{current_image_base_name}.json"
                    )
                    with open(json_data_path, "w") as f:
                        json.dump(json_data, f)
                    # print(f"空のマスクとJSONを保存: {empty_mask_path}, {json_data_path}")

            if not objects_found:
                continue  # 次のフレーム群に進む

            # 検出された基点フレームをもとに処理を続行
            image_base_name = self.frame_names[start_frame_idx].split(".")[0]
            mask_dict = MaskDictionaryModel(
                promote_type=self.PROMPT_TYPE_FOR_VIDEO, mask_name=f"mask_{image_base_name}.npy"
            )
            # print("処理を開始する基点フレーム:", start_frame_idx)

            # SAM画像予測器でのマスク生成
            self.image_predictor.set_image(np.array(image.convert("RGB")))
            input_boxes = results[0]["boxes"]

            if input_boxes is None or len(input_boxes) == 0:
                # print(f"フレーム{start_frame_idx}でバウンディングボックスがありません。スキップします。")
                continue

            OBJECTS = results[0]["labels"]
            # print("input_boxes", input_boxes)
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
            # if mask_dict.promote_type == "mask":
            #     mask_dict.add_new_frame_annotation(
            #         mask_list=torch.tensor(masks).to(self.device),
            #         box_list=torch.tensor(input_boxes),
            #         label_list=OBJECTS
            #     )
            if mask_dict.promote_type == "mask":
                mask_dict.add_new_frame_annotation(
                    mask_list=torch.as_tensor(masks, device=self.device).clone().detach(),
                    box_list=torch.as_tensor(input_boxes, device=self.device).clone().detach(),
                    label_list=OBJECTS
                )
            else:
                raise NotImplementedError("SAM 2ビデオ予測器はマスクプロンプトのみサポートしています")

            # マスクの伝播
            self.objects_count = mask_dict.update_masks(
                tracking_annotation_dict=self.sam2_masks, iou_threshold=0.8, objects_count=self.objects_count
            )
            # print("オブジェクト数:", self.objects_count)
            self.video_predictor.reset_state(self.inference_state)
            if len(mask_dict.labels) == 0:
                # print(f"フレーム{start_frame_idx}で検出されたオブジェクトがありません。スキップします。")
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
                    #例) 105030000.jpg -> 105030000
                    image_base_name = self.frame_names[out_frame_idx].split(".")[0]
                    frame_masks.mask_name = f"mask_{image_base_name}.npy"
                    frame_masks.mask_height = out_mask.shape[-2]
                    frame_masks.mask_width = out_mask.shape[-1]
                    frame_masks.labels[out_obj_id] = object_info

                video_segments[out_frame_idx] = frame_masks
                self.sam2_masks = copy.deepcopy(frame_masks)

            # print("ビデオセグメント数:", len(video_segments))

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
        with open(os.path.join(str(self.camera_id), "last_object_count.txt"), "w") as file:
            file.write(str(self.objects_count))
        #結果の描画とビデオの保存 2024.10.28 torisato
        # self.draw_results_and_save_video()


if __name__ == "__main__":
    # 引数パーサの設定
    parser = argparse.ArgumentParser(description="Video Processor Script")
    parser.add_argument(
        "--input_folder",
        type=str,
        required=True,
        help="入力フレーム画像が保存されているフォルダのパス"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./outputs",
        help="出力を保存するフォルダのパス"
    )
    parser.add_argument(
        "--device_id",
        type=int,
        default=0,
        help="使用するCUDAデバイスのID（デフォルトは0）"
    )
    parser.add_argument('--camera_id', type=int, required=True, help='カメラのid')
    args = parser.parse_args()

    # VideoProcessorのインスタンスを作成し、処理を実行
    processor = VideoProcessor(
        input_folder=args.input_folder,
        output_dir=args.output_dir,
        device_id=args.device_id,
        camera_id=args.camera_id
    )
    processor.run()