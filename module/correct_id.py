"""
corrected_id.py

マスク画像とそれに対応するJSONラベル、および外部CSVファイルに基づいて、物体のIDを修正するためのスクリプト。

このスクリプトは、マスク領域とCSVで提供される矩形領域（および対応するCCID）を突き合わせ、
IDのマッピングを行い、修正済みのマスクファイルおよびJSONファイルを別ディレクトリに出力します。

主な処理内容:
- 指定フォルダからマスク (`.npy`) ファイルとラベル (`.json`) ファイルを読み込む
- CSVに定義された矩形領域がマスクに含まれているかを確認
- 含まれていれば、その領域内のオブジェクトIDをCSVのCCIDに置き換える
- 対応するJSONの `instance_id` も同様に更新
- 更新後のマスク・JSONを別ディレクトリに保存

使用例:
```bash
python corrected_id.py \
    --mask_data_dir ./data/masks \
    --json_data_dir ./data/jsons \
    --csv_file_path ./results/result.csv \
    --corrected_mask_dir ./corrected/masks \
    --corrected_json_dir ./corrected/jsons \
    --device cuda

引数:
    --mask_data_dir : 元のマスク画像（.npy）が格納されたディレクトリ
    --json_data_dir : 元のラベルJSONが格納されたディレクトリ
    --csv_file_path : ID変換ルールを含むCSVファイルのパス（矩形座標 + CCID）
    --corrected_mask_dir : 修正後のマスクファイルの出力先ディレクトリ
    --corrected_json_dir : 修正後のJSONファイルの出力先ディレクトリ
    --device : 使用するPyTorchのデバイス（例: cuda または cpu）

注意点:
- CSVの ReadTime によってマスクファイル名を特定するため、ファイル名に対応する mask_*.npy が存在する必要があります。
- 領域がマスク内にない場合、その行はスキップされます。
- マスクIDの置換は一時的に負の値を使用して処理されます（競合回避のため）。
- JSONに含まれる labels の instance_id も cc_id123 のように更新されます。

作成者: インフォファーム
作成日: 2025年5月
"""


import os
import numpy as np
import pandas as pd
import json
import glob
import torch
import argparse

class MaskIDCorrector:
    def __init__(self, mask_data_dir, json_data_dir, csv_file_path, corrected_mask_dir, corrected_json_dir, device='cuda'):
        """
        マスク情報とCSVファイルを読み込み、修正後のデータを保存するための初期化を行います。

        :param mask_data_dir: マスクが保存されているディレクトリのパス
        :param json_data_dir: マスクに対応するJSONファイルが保存されているディレクトリのパス
        :param csv_file_path: CSVファイルのパス
        :param corrected_mask_dir: 修正後のマスクを保存するディレクトリのパス
        :param corrected_json_dir: 修正後のJSONファイルを保存するためのディレクトリのパス
        :param device: 処理に使用するデバイス（'cuda'または'cpu'）
        """
        self.mask_data_dir = mask_data_dir
        self.json_data_dir = json_data_dir
        self.csv_file_path = csv_file_path
        self.corrected_mask_dir = corrected_mask_dir
        self.corrected_json_dir = corrected_json_dir
        self.device = torch.device(device if torch.cuda.is_available() else 'cpu')

        # 保存先ディレクトリの作成
        os.makedirs(self.corrected_mask_dir, exist_ok=True)
        os.makedirs(self.corrected_json_dir, exist_ok=True)

        self.masks = {}
        self.json_data = {}
        self.load_masks_and_json()
        self.load_csv()

        # IDのマッピング（元のID -> 新しいID）
        self.id_mapping = {}

    def load_masks_and_json(self):
        """
        マスクデータと対応するJSONデータを読み込みます。
        """
        mask_files = glob.glob(os.path.join(self.mask_data_dir, "mask_*.npy"))
        for mask_file in mask_files:
            #例) ./../../105030000.npy -> 105030000.npy
            mask_name = os.path.basename(mask_file)
            # マスクをGPU上のtorchテンソルとして読み込み
            mask_array = np.load(mask_file).astype(np.int32)
            mask = torch.from_numpy(mask_array).to(self.device)
            self.masks[mask_name] = mask

            json_file = os.path.join(self.json_data_dir, mask_name.replace('.npy', '.json'))
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.json_data[mask_name] = data
            else:
                print(f"対応するJSONファイルが見つかりません: {json_file}")

    def load_csv(self):
        """
        CSVファイルを読み込み、データフレームとして保持します。
        """
        self.csv_data = pd.read_csv(self.csv_file_path, sep=',', header=0)
        # 列名の前後に余計な空白があれば削除
        self.csv_data.columns = self.csv_data.columns.str.strip()

    def is_rectangle_inside_mask(self, mask, rectangle):
        """
        四角形がマスク内に完全に含まれているかをチェックします。

        :param mask: マスクの2次元テンソル（GPU上）
        :param rectangle: 四角形の座標（リスト形式で [x1, y1, x2, y2, x3, y3, x4, y4]）
        :return: 四角形がマスク内に含まれている場合はTrue、そうでなければFalse
        """
        # 四角形の境界を取得
        x_coords = [rectangle[i] for i in range(0, len(rectangle), 2)]
        y_coords = [rectangle[i] for i in range(1, len(rectangle), 2)]
        x_min, x_max = int(min(x_coords)), int(max(x_coords))
        y_min, y_max = int(min(y_coords)), int(max(y_coords))

        # マスクの範囲内にクリップ
        height, width = mask.shape
        x_min = max(0, x_min)
        x_max = min(width - 1, x_max)
        y_min = max(0, y_min)
        y_max = min(height - 1, y_max)

        # 四角形の領域を抽出
        mask_region = mask[y_min:y_max+1, x_min:x_max+1]

        # マスクIDが0（背景）でないピクセルが存在するか確認
        if torch.all(mask_region > 0):
            return True
        else:
            return False

    def correct_mask_ids(self):
        """
        マスクIDの修正を行います。
        """
        # IDのマッピングを構築
        for index, row in self.csv_data.iterrows():
            # ReadTimeを使用してマスクファイル名を構築
            read_time = str(row['ReadTime']).strip()
            #ReadTimeが 例)085952123　→　85952123に変換されてしまう 2024.10.16 torisato
            #read_timeの文字数が8桁の場合、先頭に”０”を追加する　
            if len(read_time) == 8:
                read_time = str("0") + read_time
            mask_name = f"mask_{read_time}.npy"
            # 2024.10.10 toirsato
            # CSVデータからCCIDの取得
            ccid = int(row['Code'])

            if mask_name in self.masks:
                mask = self.masks[mask_name]
                # 四角形の座標を取得
                rectangle = [
                    row['X1'], row['Y1'], row['X2'], row['Y2'],
                    row['X3'], row['Y3'], row['X4'], row['Y4']
                ]
                rectangle = list(map(int, rectangle))

                # マスク内に四角形が含まれているか確認
                if self.is_rectangle_inside_mask(mask, rectangle):
                    # 四角形の領域内のマスクIDを取得
                    x_coords = [rectangle[i] for i in range(0, len(rectangle), 2)]
                    y_coords = [rectangle[i] for i in range(1, len(rectangle), 2)]
                    x_min, x_max = int(min(x_coords)), int(max(x_coords))
                    y_min, y_max = int(min(y_coords)), int(max(y_coords))

                    # マスクの範囲内にクリップ
                    height, width = mask.shape
                    x_min = max(0, x_min)
                    x_max = min(width - 1, x_max)
                    y_min = max(0, y_min)
                    y_max = min(height - 1, y_max)

                    # 四角形の領域を抽出
                    mask_region = mask[y_min:y_max+1, x_min:x_max+1]

                    # 領域内のユニークなマスクIDを取得
                    ids_in_region = torch.unique(mask_region)
                    ids_in_region = ids_in_region[ids_in_region != 0]  # 背景を除外

                    #CSVデータからCCを紐づける処理 2024.10.10 torisato
                    for obj_id in ids_in_region.tolist():
                        if ccid not in self.id_mapping:
                            self.id_mapping[obj_id] = ccid

                else:
                    # 四角形がマスクに含まれていない場合、何もしない
                    continue
            else:
                print(f"ReadTime {read_time} に対応するマスクファイルが見つかりません: {mask_name}")

        # 全てのマスクとJSONを更新
        for mask_name, mask in self.masks.items():
            # マスク内のユニークなIDを取得
            unique_ids = torch.unique(mask)
            unique_ids = unique_ids[unique_ids != 0]  # 背景を除外

            # IDの置換
            for obj_id in unique_ids.tolist():
                if obj_id in self.id_mapping:
                    new_id = self.id_mapping[obj_id]
                    mask[mask == obj_id] = -new_id  # 一時的に負の値を使用

            # 負の値を正の値に戻す
            mask[mask < 0] = -mask[mask < 0]

            # JSONデータの更新
            json_data = self.json_data.get(mask_name, {})
            if 'labels' in json_data:
                for label_key, label in json_data['labels'].items():
                    original_id = label['instance_id']
                    if original_id in self.id_mapping:
                        label['instance_id'] = f'cc_id{self.id_mapping[original_id]}'
            # print(f"self.id_mapping:{self.id_mapping}",f"original_id:{original_id}")

            # 修正後のマスクとJSONを保存
            self.save_corrected_mask_and_json(mask_name, mask, json_data)

    def save_corrected_mask_and_json(self, mask_name, mask, json_data):
        """
        修正されたマスクとJSONデータを個別に保存します。

        :param mask_name: マスクファイル名
        :param mask: 修正後のマスクテンソル
        :param json_data: 修正後のJSONデータ
        """
        # マスクの保存
        corrected_mask_path = os.path.join(self.corrected_mask_dir, mask_name)
        # マスクをCPU上のnumpy配列に変換し、元のデータ型にキャスト
        mask_array = mask.cpu().numpy().astype(np.uint16)

        # マスクの形状が (H, W) であることを確認
        if mask_array.ndim == 3 and mask_array.shape[0] == 1:
            mask_array = mask_array.squeeze(0)
        elif mask_array.ndim == 3 and mask_array.shape[0] > 1:
            # 複数チャンネルの場合、最初のチャンネルのみを使用
            mask_array = mask_array[0]
        elif mask_array.ndim == 4:
            # 4次元の場合、最初のチャンネルを使用
            mask_array = mask_array[0]

        np.save(corrected_mask_path, mask_array)

        # JSONデータの保存
        corrected_json_path = os.path.join(self.corrected_json_dir, mask_name.replace('.npy', '.json'))
        with open(corrected_json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)

    def run(self):
        """
        全体の処理を実行します。
        """
        self.correct_mask_ids()

if __name__ == "__main__":
    # コマンドライン引数をパース
    parser = argparse.ArgumentParser(description='Mask ID Corrector')
    parser.add_argument('--mask_data_dir', type=str, required=True, help='マスクが保存されている元のディレクトリ')
    parser.add_argument('--json_data_dir', type=str, required=True, help='JSONデータが保存されている元のディレクトリ')
    parser.add_argument('--csv_file_path', type=str, required=True, help='CSVファイルのパス')
    parser.add_argument('--corrected_mask_dir', type=str, required=True, help='修正後のマスクを保存するディレクトリ')
    parser.add_argument('--corrected_json_dir', type=str, required=True, help='修正後のJSONファイルを保存するディレクトリ')
    parser.add_argument('--device', type=str, default='cuda', help="処理に使用するデバイス（'cuda'または'cpu'）")
    args = parser.parse_args()

    corrector = MaskIDCorrector(
        mask_data_dir=args.mask_data_dir,
        json_data_dir=args.json_data_dir,
        csv_file_path=args.csv_file_path,
        corrected_mask_dir=args.corrected_mask_dir,
        corrected_json_dir=args.corrected_json_dir,
        device=args.device
    )
    corrector.run()
