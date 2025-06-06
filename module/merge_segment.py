"""
merge_segment.py

このスクリプトは、複数のセグメントに分割された JSON アノテーションデータを統合し、オブジェクトの `instance_id` を整合性のある形で統一することを目的としています。

## 主な処理内容:
1. 各セグメントディレクトリ（segment_0, segment_1, ...）から `corrected_jsons` フォルダ内のファイルを収集。
2. 同一ファイル名を持つ複数の JSON ファイル間でオブジェクトのバウンディングボックスを比較し、`IoU` が 1.0 以上かつクラス名が一致する場合に `instance_id` を統一。
3. 統一した `instance_id` を元にマージし、`merge_dir` に保存。
4. 残された単一セグメントのファイルについても、IoU による ID 統合を行う。
5. 統一された ID で最後に `merge_dir` 内の最新 `duration` 件のファイルを更新。

## 使用方法:
```bash
python merge_segment.py
    --base_dir ./segments --merge_dir ./merged_json \
    --former_merge_dir ./former_merged_json --frame_count 5 \
    --former_images_dir ./former_images --video ./video_data \
    --duration 100

引数:
    --base_dir: 各セグメントが格納されたベースディレクトリパス（必須）
    --merge_dir: マージされた JSON を保存するディレクトリパス（必須）
    --former_merge_dir: 過去動画のマージデータを保存するパス（未使用）
    --frame_count: 動画間で共有するフレーム数（未使用）
    --former_images_dir: 前動画の画像保存先（未使用）
    --video: 処理中のフォルダを記したパス（未使用）
    --duration: マージされた JSON のうち ID 統一対象とするフレーム数（デフォルト: 100）

注意:
- IoU による一致判定には torchvision.ops.box_iou を使用。
- instance_id_mapping により複数セグメントに跨る ID の一貫性を担保。
- 0座標のバウンディングボックスや不正なデータはスキップまたは削除対象。

作成日：2025年5月
作成者：インフォファーム
"""

import os
import json
import argparse
import shutil
import torch
from torchvision.ops import box_iou

def unify_instance_ids(base_dir, merge_dir,duration):
    """
    各セグメントフォルダ内のJSONファイルの 'instance_id' を統一し、順番にマージしていきます。
    同じファイル名が存在しない場合は、無条件で 'merge_dir' にコピーします。

    :param base_dir: セグメントフォルダが存在するベースディレクトリ
    :param merge_dir: マージ結果を保存するディレクトリ
    """
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # セグメントフォルダの一覧を取得し、フォルダ名でソート
    segment_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    segment_dirs.sort(key=lambda x: int(x.split('_')[-1]))  # 'segment_0', 'segment_1', ...

    # 各セグメントのファイル名の集合を取得
    segment_files = {}
    for idx, segment_dir in enumerate(segment_dirs):
        corrected_jsons_path = os.path.join(base_dir, segment_dir, 'corrected_jsons')
        if not os.path.exists(corrected_jsons_path):
            # print(f"'corrected_jsons' ディレクトリが見つかりません: {corrected_jsons_path}")
            continue
        files = set(os.listdir(corrected_jsons_path))
        segment_files[idx] = files

    # すべてのファイル名の集合を取得
    all_files = set()
    for files in segment_files.values():
        all_files.update(files)
    # ファイル名を昇順にソート
    all_files = sorted(all_files)

    # ファイル名ごとに、存在するセグメントのリストを作成
    file_segments = {}  # {filename: [segment indices]}
    for filename in all_files:
        file_segments[filename] = []
        for idx, files in segment_files.items():
            if filename in files:
                file_segments[filename].append(idx)

    os.makedirs(merge_dir, exist_ok=True)

    # インスタンスIDのマッピングを初期化
    instance_id_mapping = {}  # {('segment_index', old_instance_id): unified_instance_id}

    # 各ファイルを処理
    for filename in all_files:
        segments_with_file = file_segments[filename]
        # ファイルが複数のセグメントに存在する場合
        if len(segments_with_file) > 1:
            # 各セグメントからデータを読み込み
            data_segments = {}
            labels_segments = {}
            bboxes_segments = {}
            instance_ids_segments = {}
            class_names_segments = {}
            label_keys_segments = {}  # 修正：ラベルキーを保持
            for seg_idx in segments_with_file:
                segment_dir = segment_dirs[seg_idx]
                corrected_jsons_path = os.path.join(base_dir, segment_dir, 'corrected_jsons')
                with open(os.path.join(corrected_jsons_path, filename), 'r') as f:
                    data = json.load(f)
                    data_segments[seg_idx] = data
                    labels = data.get('labels', {})
                    labels_segments[seg_idx] = labels
                    bboxes = []
                    instance_ids = []
                    class_names = []
                    label_keys = []  # 修正：ラベルキーを保持
                    for key, label in labels.items():
                        if label['x1']!=0 and label['y1']!=0 and label['x2']!=0 and label['y2']!=0:
                            bbox = [label['x1'], label['y1'], label['x2'], label['y2']]
                            bboxes.append(bbox)
                            instance_ids.append(label['instance_id'])
                            class_names.append(label['class_name'])
                            label_keys.append(key)  # 修正：ラベルキーを追加
                    # # バウンディングボックスをテンソルに変換
                    # if bboxes:
                    #     bboxes_tensor = torch.tensor(bboxes, dtype=torch.float32, device=device)
                    #     # 同じファイル内でIoUを計算
                    #     ious = box_iou(bboxes_tensor, bboxes_tensor)
                    #     iou_threshold = 0.6
                    #     num_labels = len(bboxes)
                    #     for i in range(num_labels):
                    #         label_i_key = label_keys[i]
                    #         label_i = labels[label_i_key]
                    #         label_i['former_instance_id'] = label_i.get('former_instance_id', label_i['instance_id'])
                    #         old_id_i = label_i['former_instance_id']
                    #         for j in range(i+1, num_labels):
                    #             if ious[i, j] >= iou_threshold and class_names[i] == class_names[j]:
                    #                 label_j_key = label_keys[j]
                    #                 label_j = labels[label_j_key]
                    #                 label_j['former_instance_id'] = label_j.get('former_instance_id', label_j['instance_id'])
                    #                 old_id_j = label_j['former_instance_id']
                    #                 if old_id_i == old_id_j:
                    #                     # instance_idを統一
                    #                     key_i = (seg_idx, old_id_i)
                    #                     unified_id = instance_id_mapping.get(key_i, label_i['instance_id'])
                    #                     label_i['instance_id'] = unified_id
                    #                     label_j['instance_id'] = unified_id
                    #                     # マッピングを更新
                    #                     instance_id_mapping[(seg_idx, old_id_i)] = unified_id
                    #                     instance_id_mapping[(seg_idx, old_id_j)] = unified_id
                    bboxes_segments[seg_idx] = bboxes
                    instance_ids_segments[seg_idx] = instance_ids
                    class_names_segments[seg_idx] = class_names
                    label_keys_segments[seg_idx] = label_keys  # 修正：ラベルキーを保存

            for idx in range(len(segments_with_file)):
            # for idx in range(len(segments_with_file) - 1, -1, -1):
                # 最初のセグメントを基準にする
                base_seg_idx = segments_with_file[idx]
                base_bboxes = bboxes_segments[base_seg_idx]
                base_instance_ids = instance_ids_segments[base_seg_idx]
                base_class_names = class_names_segments[base_seg_idx]
                base_label_keys = label_keys_segments[base_seg_idx]  # 修正：ラベルキーを取得

                # バウンディングボックスをテンソルに変換
                base_bboxes_tensor = torch.tensor(base_bboxes, dtype=torch.float32, device=device)
                exclude_item = idx

                # idx以外を抽出
                filtered_list = [item for item in segments_with_file if item != exclude_item]

                # print(f"base_bboxes{base_bboxes}")

                # 他のセグメントと比較
                # for other_seg_idx in segments_with_file[idx+1:]:
                for other_seg_idx in filtered_list:
                    other_bboxes = bboxes_segments[other_seg_idx]
                    other_instance_ids = instance_ids_segments[other_seg_idx]
                    other_class_names = class_names_segments[other_seg_idx]
                    other_label_keys = label_keys_segments[other_seg_idx]  # 修正：ラベルキーを取得

                    other_bboxes_tensor = torch.tensor(other_bboxes, dtype=torch.float32, device=device)

                    # IoUを計算
                    if base_bboxes_tensor.size(0) > 0 and other_bboxes_tensor.size(0) > 0:
                        ious = box_iou(base_bboxes_tensor, other_bboxes_tensor)
                        # print(ious)
                        iou_threshold = 1
                        matching_pairs = torch.nonzero(ious >= iou_threshold, as_tuple=False)
                        # print(matching_pairs)
                        # print(base_bboxes_tensor,other_bboxes_tensor)

                        for idx_pair in matching_pairs:
                            base_idx = idx_pair[0].item()
                            other_idx = idx_pair[1].item()
                            if base_class_names[base_idx] == other_class_names[other_idx]:
                                base_id = base_instance_ids[base_idx]
                                other_id = other_instance_ids[other_idx]

                                base_label_key = base_label_keys[base_idx]  # ラベルキーを使用
                                other_label_key = other_label_keys[other_idx]  # ラベルキーを使用

                                # former_instance_idを追加
                                labels_segments[base_seg_idx][base_label_key]['former_instance_id'] = base_id
                                labels_segments[other_seg_idx][other_label_key]['former_instance_id'] = other_id

                                # 既存のマッピングを確認
                                unified_id_base = instance_id_mapping.get((base_seg_idx, base_id), base_id)
                                unified_id_other = instance_id_mapping.get((other_seg_idx, other_id), other_id)

                                if isinstance(unified_id_base, int) and isinstance(unified_id_other, int):
                                    # 一貫性を保つため、すでにマッピングされているIDを優先
                                    unified_id = min(unified_id_base, unified_id_other)  # 小さい方を選択して統一
                                elif isinstance(unified_id_base, str):
                                    unified_id = unified_id_base
                                elif isinstance(unified_id_other, str):
                                    unified_id = unified_id_other

                                # 新しいマッピングを追加（既存のものを上書きしない）
                                if (base_seg_idx, base_id) not in instance_id_mapping:
                                    instance_id_mapping[(base_seg_idx, base_id)] = unified_id
                                else:
                                    if isinstance(unified_id, int):
                                        # print(f"instance_id_mapping[(base_seg_idx, base_id)]{instance_id_mapping[(base_seg_idx, base_id)]}")
                                        if instance_id_mapping[(base_seg_idx, base_id)] > unified_id:
                                            instance_id_mapping[(base_seg_idx, base_id)]=unified_id
                                    else:
                                        instance_id_mapping[(base_seg_idx, base_id)]=unified_id

                                if (other_seg_idx, other_id) not in instance_id_mapping:
                                    instance_id_mapping[(other_seg_idx, other_id)] = unified_id
                                else:
                                    if isinstance(unified_id, int):
                                        # print(f"instance_id_mapping[(other_seg_idx, other_id)]{instance_id_mapping[(other_seg_idx, other_id)]}")
                                        if instance_id_mapping[(other_seg_idx, other_id)] > unified_id:
                                            instance_id_mapping[(other_seg_idx, other_id)]=unified_id
                                    else:
                                        instance_id_mapping[(other_seg_idx, other_id)]=unified_id

                                # instance_idを更新
                                labels_segments[base_seg_idx][base_label_key]['instance_id'] = unified_id
                                labels_segments[other_seg_idx][other_label_key]['instance_id'] = unified_id

                # マージしたラベルを作成
                merged_labels = {}
                label_counter = 1
                for seg_idx in segments_with_file:
                    labels = labels_segments[seg_idx]
                    for key in labels:
                        label = labels[key]
                        if 'former_instance_id' not in label:
                            label['former_instance_id'] = label['instance_id']
                            key_mapping = (seg_idx, label['instance_id'])
                            label['instance_id'] = instance_id_mapping.get(key_mapping, label['instance_id'])
                        merged_labels[str(label_counter)] = label
                        label_counter +=1

                # マージされたデータを保存
                merged_data = data_segments[base_seg_idx]
                merged_data['labels'] = merged_labels
                with open(os.path.join(merge_dir, filename), 'w') as f:
                    json.dump(merged_data, f, ensure_ascii=False, indent=4)

        else:
            # ファイルが一つのセグメントにのみ存在する場合
            seg_idx = segments_with_file[0]
            segment_dir = segment_dirs[seg_idx]
            corrected_jsons_path = os.path.join(base_dir, segment_dir, 'corrected_jsons')
            src_file = os.path.join(corrected_jsons_path, filename)
            dst_file = os.path.join(merge_dir, filename)
            shutil.copy2(src_file, dst_file)

            # データを読み込み
            with open(dst_file, 'r') as f:
                data = json.load(f)

            labels = data.get('labels', {})
            bboxes = []
            instance_ids = []
            class_names = []
            label_keys = []
            for key, label in labels.items():
                if label['x1']!=0 and label['y1']!=0 and label['x2']!=0 and label['y2']!=0:
                    bbox = [label['x1'], label['y1'], label['x2'], label['y2']]
                    bboxes.append(bbox)
                    instance_ids.append(label['instance_id'])
                    class_names.append(label['class_name'])
                    label_keys.append(key)

            # バウンディングボックスをテンソルに変換
            if bboxes:
                bboxes_tensor = torch.tensor(bboxes, dtype=torch.float32, device=device)
                # 同じファイル内でIoUを計算
                ious = box_iou(bboxes_tensor, bboxes_tensor)
                iou_threshold = 0.8
                num_labels = len(bboxes)
                for i in range(num_labels):
                    label_i_key = label_keys[i]
                    label_i = labels[label_i_key]
                    label_i['former_instance_id'] = label_i.get('former_instance_id', label_i['instance_id'])
                    old_id_i = label_i['former_instance_id']
                    label_i['update_camera_id'] = 0
                    for j in range(i+1, num_labels):
                        if ious[i, j] >= iou_threshold and class_names[i] == class_names[j]:
                            label_j_key = label_keys[j]
                            label_j = labels[label_j_key]
                            label_j['former_instance_id'] = label_j.get('former_instance_id', label_j['instance_id'])
                            old_id_j = label_j['former_instance_id']
                            label_j['update_camera_id'] = 0
                            if old_id_i == old_id_j:
                                # instance_idを統一
                                key_i = (seg_idx, old_id_i)
                                unified_id = instance_id_mapping.get(key_i, label_i['instance_id'])
                                label_i['instance_id'] = unified_id
                                label_j['instance_id'] = unified_id
                                # マッピングを更新
                                instance_id_mapping[(seg_idx, old_id_i)] = unified_id
                                instance_id_mapping[(seg_idx, old_id_j)] = unified_id

            # instance_idをグローバルマッピングで更新
            updated = False
            for key in labels:
                label = labels[key]
                old_id = label['instance_id']
                label['former_instance_id'] = label.get('former_instance_id', old_id)
                label['update_camera_id'] = 0
                key_mapping = (seg_idx, label['former_instance_id'])
                if key_mapping in instance_id_mapping:
                    unified_id = instance_id_mapping[key_mapping]
                    if unified_id != old_id:
                        label['instance_id'] = unified_id
                        updated = True

            # 更新されたデータを保存
            with open(dst_file, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        # print(instance_id_mapping,filename)
    
    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(merge_dir))

    #更新したいmerged_jsonの数を取得
    num_files_to_copy = min(duration, len(files))

    #更新するmerged_jsonを取得
    files_to_copy = files[-num_files_to_copy:]

    # print(f"num_files_to_copy{num_files_to_copy}")
    # print(files_to_copy)
    # print(instance_id_mapping)

    # マージディレクトリ内のすべてのファイルの instance_id を最終更新
    for json_file in files_to_copy:
        file_path = os.path.join(merge_dir, json_file)
        with open(file_path, 'r') as f:
            data = json.load(f)
        labels = data.get('labels', {})
        keys_to_delete = []
        updated = False
        for key in labels:
            label = labels[key]
            if label['x1']==0 and label['y1']==0 and label['x2']==0 and label['y2']==0:
                keys_to_delete.append(key)
            old_id = label['instance_id']
            label['former_instance_id'] = label.get('former_instance_id', old_id)
            # 全セグメントを探索
            for seg_idx in range(len(segment_dirs)):
                key_mapping = (seg_idx, label['former_instance_id'])
                if key_mapping in instance_id_mapping:
                    unified_id = instance_id_mapping[key_mapping]
                    if unified_id != old_id:
                        label['instance_id'] = unified_id
                        updated = True
                        break
        # # ラベルを削除
        for key in keys_to_delete:
            del labels[key]
            if len(keys_to_delete)!=0:
                updated=True
        if updated:
            with open(file_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            # print("update")

# def copy_merged_json(merged_json_folder,former_merged_json_folder,frame_count):

#     # コピー先フォルダが存在しない場合は作成
#     os.makedirs(former_merged_json_folder, exist_ok=True)
    
#     # フォルダ内のファイル一覧を取得し、ソート
#     files = sorted(os.listdir(merged_json_folder))

#     # ファイルが5つ未満の場合、全てのファイルをコピー
#     num_files_to_copy = min(frame_count, len(files))

#     # 下から5つのファイルを取得
#     files_to_copy = files[-num_files_to_copy:]

#     # ファイルをコピー
#     for file_name in files_to_copy:
#         source_file = os.path.join(merged_json_folder, file_name)
#         destination_file = os.path.join(former_merged_json_folder, file_name)
#         shutil.copy(source_file, destination_file)

def main():
    parser = argparse.ArgumentParser(description='Instance ID Unifier')
    parser.add_argument('--base_dir', type=str, required=True, help='セグメントフォルダが存在するベースディレクトリのパス')
    parser.add_argument('--merge_dir', type=str, required=True, help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--former_merge_dir', type=str, required=True, help='動画間のマージ結果を保存するディレクトリのパス')
    parser.add_argument('--frame_count', type=int, required=True, help='動画間の重ねるフレームの数')
    parser.add_argument('--former_images_dir', type=str, required=True, help='動画間の画像を保存するディレクトリのパス')
    parser.add_argument('--video', type=str, required=True, help='現在処理が行われいるフォルダが記載してあるテキスト')
    parser.add_argument('--duration', type=int, default=100, help='セグメントの長さ（フレーム数）')
    args = parser.parse_args()

    unify_instance_ids(args.base_dir, args.merge_dir,args.duration)

    #copy_merged_json(args.merge_dir,args.former_merge_dir,args.frame_count)

if __name__ == "__main__":
    main()
