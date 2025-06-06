import os
import numpy as np
import shutil
import argparse  # argparseをインポート
from datetime import datetime

def copy(base_dir, merge_dir, image_path):
    """
    推論結果のデータを指定フォルダにコピーする。

    :param base_dir: セグメントフォルダが存在するベースディレクトリ
    :param merge_dir: マージ結果を保存するディレクトリ
    """
    # 保存先のディレクトリ
    destination_folder = "SAVE_DATA"

    # 現在の日付を YYYYMMDD 形式で取得
    current_date = datetime.now().strftime("%Y%m%d")

    # コピー先のフォルダが存在しない場合は作成
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    # # 保存先フォルダ内のファイル数を取得
    # existing_files = os.listdir(destination_folder)
    # file_count = len([f for f in existing_files if f.endswith('.mp4')])

    # # フォルダ内の内容を取得
    # for item in os.listdir(base_dir):
    #     sub_dir = os.path.join(base_dir, item)
    #     if os.path.isdir(sub_dir):  # segment_0, segment_1 ...
    #         output_movie_dir = os.path.join(sub_dir, "output2.mp4")

    #         # 保存する動画名 (例: 1.mp4, 2.mp4, 3.mp4)
    #         file_count += 1
    #         new_filename = f"{image_path}_{file_count}.mp4"  # 順番に 1.mp4, 2.mp4, 3.mp4 の形式で保存
    #         destination_file_path = os.path.join(destination_folder, new_filename)

    #         # 動画ファイルをコピーし、名前を変更
    #         if os.path.exists(output_movie_dir):
    #             shutil.copy(output_movie_dir, destination_file_path)
    #             print(f"{output_movie_dir} を {destination_file_path} にコピーしました")

    # フォルダ内の内容を取得
    for item in os.listdir(base_dir):
        sub_dir = os.path.join(base_dir, item)
        if os.path.isdir(sub_dir):  # segment_0, segment_1 ...
            output_movie_dir = os.path.join(sub_dir, "output2.mp4")

            # 保存する動画名 (例: 20241010_081210123.mp4, 20241010_081220123.mp4, 20241010_081230123.mp4)
            new_filename = f"{current_date}_{image_path}.mp4"  # 動画名（YYYYMMDD_タイムスタンプ.mp4）
            destination_file_path = os.path.join(destination_folder, new_filename)

            # 動画ファイルをコピーし、名前を変更
            if os.path.exists(output_movie_dir):
                shutil.copy(output_movie_dir, destination_file_path)
                print(f"{output_movie_dir} を {destination_file_path} にコピーしました")


def main():
    parser = argparse.ArgumentParser(description='Instance ID Unifier')
    # parser.add_argument('--base_dir', type=str, required=True, default='./data/gsam2_output' ,help='セグメントフォルダが存在するベースディレクトリのパス')
    # parser.add_argument('--merge_dir', type=str, required=True, default='./data/merged_jsons' ,help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--base_dir', type=str, default='./data/gsam2_output' ,help='セグメントフォルダが存在するベースディレクトリのパス')
    parser.add_argument('--merge_dir', type=str, default='./data/merged_jsons' ,help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--image_path', type=str, default='SAVE_DATA' ,help='動画名（タイムスタンプ_count)')
    args = parser.parse_args()

    copy(args.base_dir, args.merge_dir, args.image_path)

if __name__ == "__main__":
    main()