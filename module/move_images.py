"""
画像移動ユーティリティスクリプト

このスクリプトは、指定された2つのフォルダ間で JPG 画像を移動するためのものです。
前回の動画処理結果として一時保存された画像を、現在の処理対象フォルダへ移動する用途を想定しています。

主な機能:
    - .jpg 画像の移動（コピー後削除）
    - ファイル名の数値順ソート（将来的な処理用）
    - エラー処理による安全なファイル操作

実行例:
    python move_images.py --frames_folder ./frames --former_images_dir ./former_images
"""

import argparse
import os
import shutil
import re
import stat

def move_images(image_path,former_image_path):
    print(f"image_path:{image_path}, former_image_path:{former_image_path}")
    #former_imagesからimage_pathに画像をコピーする
    # フォルダが存在するかどうかを確認
    if os.path.exists(image_path) and os.path.isdir(former_image_path):
        # .jpgファイルをすべてコピー
        for filename in os.listdir(former_image_path):
            # .jpgファイルのみを選択
            if filename.endswith(".jpg"):
                source_path = os.path.join(former_image_path, filename)
                destination_path = os.path.join(image_path, filename)
                shutil.copy2(source_path, destination_path)
                try:
                    shutil.copy2(source_path, destination_path)
                    os.remove(source_path)
                except FileNotFoundError:
                    print(f"⚠ ファイルが見つかりませんでした: {source_path}")
                except PermissionError:
                    print(f"⚠ ファイルにアクセスできませんでした（ロックされている可能性）: {source_path}")
        print("former_images を処理しました。")
        #すべての画像をコピー完了すると「former_images」フォルダを削除する
        # shutil.rmtree(former_image_path)

        print("former_imagesを削除しました。")
        # フレームファイルのリストを取得し、ファイル名の数字部分でソート
        frame_files = os.listdir(image_path)
        sorted(frame_files, key=lambda f: int(re.search(r'\d+', f).group()) if re.search(r'\d+', f) else float('inf'))

    return #存在しない場合何も処理しない


def main():
    parser = argparse.ArgumentParser(description='Instance ID Unifier')
    parser.add_argument('--frames_folder', type=str ,help='画像スライスフォルダ')
    parser.add_argument('--former_images_dir', type=str, required=True, help='動画間の画像を保存するディレクトリのパス')
    args = parser.parse_args()

    move_images(args.frames_folder,args.former_images_dir)

if __name__ == "__main__":
    main()