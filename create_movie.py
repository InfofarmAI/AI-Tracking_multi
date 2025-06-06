"""
create_movie.py

このスクリプトは、物体検出結果が記録されたJSONファイル群と対応する画像を元に、識別ID（instance_id）付きのバウンディングボックスを描画し、動画ファイル (MP4) を生成します。

## 主な機能:
- 指定ディレクトリ内のマージ済みJSONファイルを読み取り、最新 N 件を取得
- 対応する画像にバウンディングボックスと識別IDを描画
- CCIDが存在する場合は、`cc_name.txt` に基づいて日本語名を重ね描画
- 出力動画と描画済み画像を `MOVIE_FOLDER/{日付}/{対象フォルダ}` に保存

## 使用方法（例）:
```bash
python create_movie.py \
    --image_path 111643295 \
    --frame_count 5 \
    --merge_dir ./data/merged_jsons \
    --duration 155 \
    --camera_id CAM01

引数:
    --image_path (str): 対象の画像フォルダ名（例: タイムスタンプ形式）。デフォルトは 'SAVE_DATA'。
    --frame_count (int): ID引き継ぎに使用される前後の重なりフレーム数。
    --merge_dir (str): 統合されたJSONファイルが保存されているディレクトリへのパス。
    --duration (int): 映像に含める総フレーム数（最新から指定数だけ取得）。
    --camera_id (str): 処理対象のカメラID。ファイルパス構成やIDプレフィックスに利用。

注意:
    cc_name.txt は JSON 形式で、cc_id と name を対応付けるリストが必要です。
    日本語ラベル描画には "NotoSansJP-VariableFont_wght.ttf" フォントが必要です。
    出力動画形式は MP4（コーデック: mp4v、解像度: 1920x1080、fps: 5.0）。

作成日：2025年5月
作成者：インフォファーム
"""


import os
import json
import cv2
import argparse
from datetime import datetime
import re
import numpy as np
from PIL import Image, ImageDraw , ImageFont


def get_merge_json(folder_path, num_files_to_get,frame_count):
    """
    指定されたフォルダ内のファイル一覧から、特定のファイル以降のファイル名をリストで返す関数。

    この関数は、フォルダ内のファイルをソートし、指定したファイル（start_file）から
    それ以降に並んでいるすべてのファイル名を取得して返します。

    Args:
        folder_path (str): 対象とするフォルダのパス。
        start_file (str): 開始ファイル名。このファイル以降のファイルを取得する基準。

    Returns:
        list[str]: 指定ファイル以降のファイル名のリスト。指定ファイルが見つからない場合は空リストを返す。

    Example:
        >>> get_merge_json("data/frames", "000001234.json")
        ['000001234.json', '000001235.json', '000001236.json']
    """
    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(folder_path))

    # ファイルが指定した数未満の場合、その数まで取得
    num_files_to_get = min(num_files_to_get, len(files))

    # 下から指定した数のファイルを取得
    files_to_get = files[-(num_files_to_get):-(frame_count)]

    return files_to_get


def create_movie(iamge_path, frame_count, files,merge_dir,camera_id):
    """
    指定された画像フォルダとJSONファイルから、検出された物体にバウンディングボックスとラベルを描画し、
    画像を保存・動画として出力する処理を行います。

    各画像に対して、該当するJSON（アノテーション）データを読み込み、検出されたIDに基づいて
    ラベルやバウンディングボックスを描画します。
    "cc_id" を含むIDの場合、cc_name.txt から名称を取得して画像に描画します。

    最終的には以下のような処理を行います：
      - 出力先ディレクトリを日付ごとに作成
      - 各画像を加工し保存
      - 画像を連結して MP4 動画を出力

    Args:
        iamge_path (str): 入力画像のパス（カメラID 以下の画像ディレクトリ名）。
        frame_count (int): 使用されていないが、将来的な使用を想定。
        files (list of str): 処理対象となるJSONファイル名のリスト。
        merge_dir (str): JSONファイルが格納されているディレクトリのパス。
        camera_id (str): カメラID。出力先ディレクトリの構築などに使用。

    Notes:
        - `cc_name.txt` というJSONファイルが必要で、その中には `{"ccid": str, "name": str}` の形式で
          CC名称情報が含まれている必要があります。
        - 出力先は `<camera_id>/MOVIE_FOLDER/<YYYYMMDD>/<image_path>/` という構成で保存されます。
        - 出力動画は "output.mp4" として保存されます。
    """
    # 画像ファイルが入っているフォルダを指定
    folder_path = iamge_path
    #2025.05.27 torisato
    # destination_folder = camera_id+"/MOVIE_FOLDER"
    destination_folder = os.path.join(camera_id, "MOVIE_FOLDER")
    # 現在の日付を YYYYMMDD 形式で取得
    current_date = datetime.now().strftime("%Y%m%d")

    # MOVIE_FOLDERフォルダが存在しない場合は作成
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)
        print(f'{destination_folder}は存在しません。')
    else:
        print(f'{destination_folder}は存在します。')

    destination_folder = os.path.join(destination_folder,current_date)
    # コピー先のフォルダが存在しない場合は作成
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    destination_folder = os.path.join(destination_folder,folder_path)
    # コピー先のフォルダが存在しない場合は作成
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    # 動画作成のための VideoWriter オブジェクトを作成
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # mp4形式で保存
    video = cv2.VideoWriter(os.path.join(destination_folder,"output.mp4"), fourcc, 5.0, (1920, 1080))

    # print("clear")

    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)

    # フォルダ内のすべてのファイルを取得
    for  filename in files:
        # 正規表現で9桁の数値を抽出
        match = re.search(r'\d{9}', filename)
        if match:
            number = match.group()

        #画像のパスを作成
        image_file_path = os.path.join(camera_id, folder_path, number + ".jpg")
        # 画像を読み込む
        image = cv2.imread(image_file_path)

        # JSONファイルを読み込む
        with open(os.path.join(merge_dir, filename), 'r') as file:
            data = json.load(file)

        # labels部分を取得
        # labels = data["labels"]
        labels = data.get('labels', {})

        #id管理用リスト
        id_lists=[]
        if labels:
            # labelsの内容をfor文で回す
            for _, label_info in labels.items():
                TID=label_info['instance_id']
                if "cc_id" in str(TID):
                    ID=TID
                else:
                    if label_info['update_camera_id'] == 0:
                        ID = str(camera_id) + "_" + str(TID)
                    else:
                        ID = str(label_info['update_camera_id']) + "_" + str(TID)
                #idがリストにない場合
                if ID not in id_lists:
                    bbox=[label_info['x1'],label_info['y1'],label_info['x2'],label_info['y2']]
                    # バウンディングボックスを描画 (色は青, 太さは2)
                    image = cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)

                    #HACK　取得したIDに文字列"cc_id"が含まれているかチェックする 2024/11/15 torisato(削除予定)
                    if "cc_id" in str(TID):
                        ccid = int(str(TID).replace("cc_id", ""))
                        cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
                        text = cc['name']
                        #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
                        image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                        #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
                        draw = ImageDraw.Draw(image_pil)

                        # 画像にテキストを描画
                        draw.text((bbox[0], int((bbox[1] + bbox[3]) / 2)), text, font=font, fill=(0, 255, 0))
                        # Pillow形式からcv2形式に戻す
                        image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
                        # バウンディングボックスの上にTIDを表示
                        id_lists.append(TID)
                    else:
                        image = cv2.putText(image, ID, (bbox[0], int((bbox[1] + bbox[3]) / 2)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)

                        # 画像にテキストを描画
                        # draw.text((bbox[0], int((bbox[1] + bbox[3]) / 2)), str(TID), font=font, fill=(0, 0, 255))
                        id_lists.append(ID)
                else:
                    continue


        #例)>- MOVIE_FOLDER/111643295/111654095.jpg
        cv2.imwrite(os.path.join(destination_folder,number + ".jpg"),image)
        video.write(image)  # 動画ファイルに書き込み

    # 動画ファイルを保存し終了
    video.release()
    cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description='Instance ID Unifier')
    parser.add_argument('--image_path', type=str, default='SAVE_DATA' ,help='動画名（タイムスタンプ_count)')
    parser.add_argument('--frame_count', type=int ,help='動画間のID継承処理用の画像重なり枚数の設定')
    parser.add_argument('--merge_dir', type=str, required=True, help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--duration', type=int, default=100, help='セグメントの長さ（フレーム数）')
    parser.add_argument('--camera_id', type=str, required=True, help='カメラのid')
    args = parser.parse_args()

    camera_id=args.camera_id

    files = get_merge_json(args.merge_dir, args.duration, args.frame_count)
    print("len(files)",len(files))
    create_movie(args.image_path, args.frame_count, files,args.merge_dir, camera_id)

if __name__ == "__main__":
    main()