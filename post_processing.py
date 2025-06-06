"""
post_processing.py

処理完了後の後処理スクリプト。

このスクリプトは、処理後に生成された画像フォルダとCCID情報（CSVファイルなど）を、
日付付きの保存ディレクトリに自動的に移動させる役割を担います。
保存先は `--save_folder` で指定されたパス配下の `save_data/日付/` にまとめられます。

使い方（例）：
    python post_processing.py --save_folder ./1 --image_path ./1/105030000 --csv_file_path ./1/CCImageReader/result_105030000

引数:
    --save_folder       処理対象のカメラフォルダのルートパス（例: ./1）
    --image_path        処理対象の画像フォルダのパス（例: ./1/105030000）
    --csv_file_path     処理対象のCCデータの保存フォルダ（例: ./1/CCImageReader/result_105030000）

実行結果:
    - 指定された `image_path` を日付付きディレクトリに移動
    - 指定された `csv_file_path` を同様に移動
    - それぞれ移動の成否をコンソールに出力

注意:
    - 指定されたフォルダが存在しない場合、エラーメッセージが出力されますが処理は継続されます。
    - 保存先ディレクトリは存在しない場合、自動作成されます。

作成者: インフォファーム
作成日: 2025年5月
"""


import argparse
import os
import shutil
from datetime import datetime


def main():
    """処理が終わった後に、画像フォルダとCC情報のフォルダを移動させる"""
    today_str = datetime.now().strftime("%Y%m%d")
    save_dir = os.path.join(save_folder, os.path.join("save_data", today_str))
    os.makedirs(save_dir, exist_ok=True)

    if os.path.exists(image_folder):
        dest_image_path = os.path.join(save_dir, os.path.basename(image_folder))
        shutil.move(image_folder, dest_image_path)
        print(f"✅ 画像フォルダを移動しました: {dest_image_path}")
    else:
        print("❌ 画像フォルダが存在しません")

    if os.path.exists(cc_folder):
        dest_cc_path = os.path.join(save_dir, os.path.basename(cc_folder))
        shutil.move(cc_folder, dest_cc_path)
        print(f"✅ CCフォルダを移動しました: {dest_cc_path}")
    else:
        print("❌ CCフォルダが存在しません")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--save_folder",
        type=str,
        help="対象のフォルダパス"
    )
    parser.add_argument(
        "--image_path",
        type=str,
        help="入力フレーム画像が保存されているフォルダのパス"
    )
    parser.add_argument(
        "--csv_file_path",
        type=str,
        help="CCIDが保存されているフォルダのパス"
    )

    args = parser.parse_args()
    save_folder = args.save_folder
    image_folder = args.image_path
    cc_folder = args.csv_file_path

    main()
