"""
merge_json_merge.py

複数の動画にまたがる物体追跡を実現するため、マージ済みのJSONファイル（merge_json）間で
インスタンスIDをIoU（Intersection over Union）ベースで引き継ぎ、ID統合を行うスクリプト。

このスクリプトは以下の処理を行います：

1. 一つ前の動画と現在の動画でmerge_jsonフォルダを比較し、IoUに基づいて同一物体のIDを継承。
2. マッチしたインスタンスのIDおよびカメラ情報を後続のJSONに反映。
3. 特定のCCIDが割り当てられた場合、旧IDに遡ってJSONファイルとDBへ反映。
4. 日本語名のラベル付き画像生成（任意：Pillowによるテキスト描画）。
5. 動画内画像（.jpg）から動画（.mp4）を生成。
6. 動画間の連続性を保つため、末尾のmerge_jsonファイルを次動画処理用に一時保存。

使用例:
```bash
python merge_json_merge.py \
    --merge_dir ./merged_jsons/current_video \
    --former_merge_dir ./merged_jsons/previous_video \
    --frame_count 5 \
    --camera_id CAM001

引数:
    --merge_dir : 現在処理している動画のmerge_jsonディレクトリ
    --former_merge_dir : ひとつ前の動画のmerge_jsonディレクトリ（ID引継ぎ元）
    --frame_count : 動画間で重ねて処理するフレーム数（IoUマッチング対象）
    --camera_id : 対象のカメラID（DB更新や動画名生成に使用）

要件:
    torch, torchvision, cv2, Pillow, mysql-connector-python が必要
    utils3/DB_serch_camera_conf_utils.py にDB更新ロジックが実装されている必要あり
    cc_name.txt にCCIDと名称のマッピングが格納されている必要あり
    NotoSansJP-VariableFont_wght.ttf フォントファイルが存在する必要あり（画像への日本語描画用）

出力:
    IDが引き継がれたmerge_jsonファイル（上書き）
    必要に応じて、名称入りのJPEG画像（既存画像に上書き保存）
    対象フォルダに output2.mp4 として画像を結合した動画ファイル
    次動画処理用にmerge_jsonの末尾ファイルがコピーされる

作成日: 2025年5月
作成者: インフォファーム
"""

import json
import torch
from torchvision.ops import box_iou
import os
import argparse
import shutil
from datetime import datetime
from utils3.DB_serch_camera_conf_utils import config
import mysql.connector
import re
import cv2
from PIL import Image, ImageDraw , ImageFont
import numpy as np

def update_instance_ids_based_on_iou(former_merge_folder, merge_folder, iou_threshold=0.8):
    """現在処理されている動画のmerge_jsonが作られた時に、ひとつ前の動画のmerge_jsonを指定した時間重なる部分を別フォルダから呼び出しiou計算してidを引き継ぐ"""
    #重なり部分のmergeフォルダからファイルを取得
    if os.path.exists(former_merge_folder):
        files = os.listdir(former_merge_folder)
    else:
        files = []

    for file in files:
        # 1つ目のmerge_jsonを読み込み
        with open(os.path.join(former_merge_folder, file) , 'r') as f:
            merge_data_1 = json.load(f)

        # 2つ目のmerge_jsonを読み込み
        with open(os.path.join(merge_folder, file) , 'r') as f:
            merge_data_2 = json.load(f)

        # 各ラベルを取得（バウンディングボックスとinstance_idを含む）
        labels_1 = merge_data_1.get('labels', {})
        labels_2 = merge_data_2.get('labels', {})

        # 1つ目のmerge_jsonからbbox, instance_id, class_nameを抽出
        bboxes_1 = []
        instance_ids_1 = []
        class_names_1 = []
        update_camera_id_1 = []
        for key, label in labels_1.items():
            bbox = [label['x1'], label['y1'], label['x2'], label['y2']]
            bboxes_1.append(bbox)
            instance_ids_1.append(label['instance_id'])
            class_names_1.append(label['class_name'])
            update_camera_id_1.append(label['update_camera_id'])

        # 2つ目のmerge_jsonからbbox, instance_id, class_nameを抽出
        bboxes_2 = []
        instance_ids_2 = []
        class_names_2 = []
        update_camera_id_2 = []
        for key, label in labels_2.items():
            bbox = [label['x1'], label['y1'], label['x2'], label['y2']]
            bboxes_2.append(bbox)
            instance_ids_2.append(label['instance_id'])
            class_names_2.append(label['class_name'])
            update_camera_id_2.append(label['update_camera_id'])

        # バウンディングボックスをテンソルに変換
        bboxes_tensor_1 = torch.tensor(bboxes_1, dtype=torch.float32)
        bboxes_tensor_2 = torch.tensor(bboxes_2, dtype=torch.float32)

        # IoUを計算
        if bboxes_tensor_1.size(0) > 0 and bboxes_tensor_2.size(0) > 0:
            ious = box_iou(bboxes_tensor_1, bboxes_tensor_2)

            # IoUが閾値以上のペアを見つける
            matching_pairs = torch.nonzero(ious >= iou_threshold, as_tuple=False)
            # print(matching_pairs)

            # マッチしたペアのインスタンスIDを反映
            for idx_pair in matching_pairs:
                idx_1 = idx_pair[0].item()  # merge_json_1のインデックス
                idx_2 = idx_pair[1].item()  # merge_json_2のインデックス

                # クラス名が一致するか確認
                if class_names_1[idx_1] == class_names_2[idx_2]:
                    # 1つ目のmerge_jsonのinstance_idを2つ目に反映
                    old_instance_id_2 = instance_ids_2[idx_2]
                    new_instance_id = instance_ids_1[idx_1]
                    new_camera_id = update_camera_id_1[idx_1]

                    # 2つ目のmerge_jsonのラベルに反映
                    for key, label in labels_2.items():
                        if label['instance_id'] == old_instance_id_2:
                            label['instance_id'] = new_instance_id
                            if (old_instance_id_2, new_instance_id) not in instance_list and old_instance_id_2 != new_instance_id:
                                if "cc_id" in str(old_instance_id_2) and "cc_id" not in str(new_instance_id):
                                    if (new_instance_id, old_instance_id_2) not in reversed_instance_list:
                                        reversed_instance_list.append((new_instance_id, old_instance_id_2))
                                else:
                                    instance_list.append((old_instance_id_2, (new_instance_id, new_camera_id)))

        # 2つ目のmerge_jsonを上書き保存
        # with open(merge_folder + '/' + file, 'w') as f:
        #     json.dump(merge_data_2, f, ensure_ascii=False, indent=4)

    # 動画間で重なりのあるファイルをすべて削除
    # 上位5つのファイルを削除
    # if file_count > frame_count:
    #     for file in files:
    #         file_path = os.path.join(former_merge_folder, file)
    #         if os.path.isfile(file_path):  # ファイルかどうか確認
    #             os.remove(file_path)  # ファイルを削除

def get_merge_json(folder_path, start_file):
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
    # 指定したフォルダ内のファイルをリストアップ
    files = sorted(os.listdir(folder_path))  # ファイルをソート
    if start_file in files:
        # 指定したファイル以降のファイルを取得
        start_index = files.index(start_file)
        return files[start_index:]  # 指定ファイル以降のファイルをリスト化
    else:
        return []  # 指定ファイルが存在しない場合は空のリストを返す

def reversed_get_merge_json(folder_path, start_file):
    """
    指定されたフォルダ内のファイル一覧から、特定のファイル以降のファイル名をリストで返す関数。

    この関数は、フォルダ内のファイルをソートし、指定したファイル（start_file）を含まず
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
    # 指定したフォルダ内のファイルをリストアップ
    files = sorted(os.listdir(folder_path))  # ファイルをソート
    #print(files)
    # print(start_file)
    if start_file in files:
        # 指定したファイル以降のファイルを取得
        start_index = files.index(start_file)
        return files[:start_index]  # 指定ファイル以前のファイルをリスト化
    else:
        return []  # 指定ファイルが存在しない場合は空のリストを返す

def merge_json_correct(files, reversed_files, camera_id):
    """動画ごとのmerge_jsonを更新し、更新後データを使用して動画を再作成する。"""
    last_folder_name=""
    if instance_list != []:
        for file in files:
            with open(os.path.join(merge_folder, file), 'r') as f:
                merge_data = json.load(f)
                labels = merge_data.get('labels', {})
                for key, label in labels.items():
                    for item in instance_list:
                        """
                        例)instance_listの中身
                        old_instance_id
                        (new_instance_id, new_camera_id)
                        """
                        if label['instance_id'] == item[0]:
                            label['instance_id'] = item[1][0]
                            label['update_camera_id'] = item[1][1]
                            break
            with open(os.path.join(merge_folder, file), 'w') as f:
                json.dump(merge_data, f, ensure_ascii=False, indent=4)

    #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    #HACK　日本語フォント　2024/11/15 torisato(削除予定)
    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)
    if reversed_instance_list != []:
        for file in reversed_files:
            id_lists=[]
            with open(os.path.join(merge_folder, file), 'r') as f:
                merge_data = json.load(f)
                labels = merge_data.get('labels', {})
                for key, label in labels.items():
                    for item in reversed_instance_list:
                        #print(instance_list)
                        TID = item[0]
                        ccid = int(str(item[1]).replace("cc_id", ""))
                        if label['instance_id'] == TID:
                            log_time = convert_filename_to_time_format(file)
                            # update_data(int(str(item[1]).replace("cc_id", "")), log_time, int(item[0]), camera_id)
                            update_data(ccid, log_time, int(TID), camera_id)
                            #例)root_folder = 1/MOVIE_FOLDER/20250528    target_folder = 134917000.jpg
                            root_folder, target_file_name = get_day_and_timestamp(file)
                            #例)image_file = 1/MOVIE_FOLDER/20250528\134850000/134917200.jpg
                            image_file, current_folder_name = find_file(root_folder, target_file_name)

                            # 画像を読み込む
                            if image_file != None:
                                image = cv2.imread(image_file)
                                # ccid = int(str(item[1]).replace("cc_id", ""))
                                cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
                                text = cc['name']
                                #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
                                image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                                #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
                                draw = ImageDraw.Draw(image_pil)

                                # 画像にテキストを描画
                                if TID not in id_lists:
                                    draw.text((label['x1'], int((label['y1']+label['y2'])/2-40)), text, font=font, fill=(0, 255, 0))
                                    # Pillow形式からcv2形式に戻す
                                    image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
                                # image = cv2.putText(image, str(item[1]), (label['x1'], int((label['y1']+label['y2'])/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                                    cv2.imwrite(image_file,image)
                                    id_lists.append(TID)
                                if last_folder_name != current_folder_name and last_folder_name != "":
                                    movie_create(last_folder_name)
                                last_folder_name = current_folder_name
                            label['instance_id'] = item[1]
                            break
            with open(os.path.join(merge_folder, file), 'w') as f:
                json.dump(merge_data, f, ensure_ascii=False, indent=4)
        if last_folder_name != "":
            movie_create(last_folder_name)

def get_firstfile(former_merged_json_folder):
    """指定フォルダから最初のファイルを取得する"""
    if os.path.exists(former_merged_json_folder):
        files = os.listdir(former_merge_folder)
    else:
        files = []

    #print(files[0])
    if len(files) == 0:
        return []
    else:
        return files[0]

def copy_merged_json(merged_json_folder, former_merged_json_folder, frame_count):
    """merge_jsonフォルダの下から5件を取得し、コピーする。"""
    if os.path.exists(former_merged_json_folder):
        shutil.rmtree(former_merged_json_folder)

    # コピー先フォルダが存在しない場合は作成
    os.makedirs(former_merged_json_folder, exist_ok=True)

    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(merged_json_folder))

    # ファイルが5つ未満の場合、全てのファイルをコピー
    num_files_to_copy = min(frame_count, len(files))

    # 下から5つのファイルを取得
    files_to_copy = files[-num_files_to_copy:]

    # ファイルをコピー
    for file_name in files_to_copy:
        source_file = os.path.join(merged_json_folder, file_name)
        destination_file = os.path.join(former_merged_json_folder, file_name)
        shutil.copy(source_file, destination_file)

def convert_filename_to_time_format(filename):
    """
    指定されたファイル名から9桁の数値を抽出し、それを時刻形式（HH:MM:SS.mmm）に変換して返します。

    数値は1日のミリ秒表現（例：123456789 → 12時間34分56秒789ミリ秒）として扱われ、
    現在の日付（yyyy/mm/dd）と組み合わせた文字列としてフォーマットされます。

    Args:
        filename (str): ファイル名。9桁の連続した数字（例："123456789"）が含まれている必要があります。

    Returns:
        str: 現在の日付に抽出した時間を加えた文字列（例："2025/05/30 12:34:56.789"）。

    Raises:
        ValueError: ファイル名に9桁の数値が含まれていない場合。
    """
    # 正規表現で9桁の数値を抽出
    match = re.search(r'\d{9}', filename)
    if match:
        number = match.group()

    # 文字列を整数に変換
    total_seconds = int(number)
    # print(total_seconds)

    # 時、分、秒、ミリ秒に変換
    hours = total_seconds // 10000000
    minutes = (total_seconds // 100000) % 100
    seconds = (total_seconds // 1000) % 100
    milliseconds = total_seconds % 1000

    # 日付部分をフォーマット
    formatted_date = datetime.now().strftime("%Y/%m/%d")

    # フォーマットして返す
    return f"{formatted_date} {hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"

def update_data(ccid, log_datetime, TID, camera_id):
    """
    指定された条件に一致するログレコードの `chameleon_code` を更新します。

    この関数は、MySQL データベース内の `cclog_db.logs` テーブルに対して
    `log_datetime`, `TID`, `camera_id` の一致する行の `chameleon_code` を指定された `ccid` に更新します。

    引数:
        ccid (str or int): 更新する chameleon_code の値。
        log_datetime (datetime): 対象ログの日時。
        TID (str): 対象ログの TID（トラッキングIDなど）。
        camera_id (int): 対象のカメラID。
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "UPDATE cclog_db.test_logs SET chameleon_code =%s where log_datetime = %s AND TID = %s AND camera_id=%s;"
        query = "UPDATE cclog_db.logs SET chameleon_code =%s where log_datetime = %s AND TID = %s AND camera_id=%s;"
        params=(ccid, log_datetime, TID, camera_id)

        db.execute(query,params)
        connection.commit()

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def get_day_and_timestamp(filename):
    """
    指定されたファイル名から9桁の数値を抽出し、それをもとに保存先ディレクトリパスと
    ファイル名を生成して返します。

    この関数は、ファイル名に含まれる9桁のタイムスタンプから現在日付を取得し、
    カメラIDおよび "MOVIE_FOLDER" フォルダ構成に基づいたパスを構築します。
    ※グローバル変数 `camera_id` を参照している点に注意してください。

    Args:
        filename (str): 9桁の数値を含むファイル名。

    Returns:
        tuple:
            str: 保存先パス（camera_id/MOVIE_FOLDER/YYYYMMDD）。
            str: 画像ファイル名（例: "123456789.jpg"）。
    """
    # 正規表現で9桁の数値を抽出
    match = re.search(r'\d{9}', filename)
    if match:
        number = match.group()

    # 日付部分をフォーマット
    formatted_date = datetime.now().strftime("%Y%m%d")

    # フォーマットして返す
    # return camera_id+"/MOVIE_FOLDER"+"/"+formatted_date, str(number)+".jpg"
    return os.path.join(camera_id, "MOVIE_FOLDER", formatted_date), str(number)+".jpg"

def find_file(root_folder, target_file_name):
    """指定したフォルダ内の全てのサブフォルダを再帰的に検索"""
    for root, dirs, files in os.walk(root_folder):
        if target_file_name in files:
            return os.path.join(root, target_file_name) , root
    return None

def movie_create(root_folder):
    """更新後の動画を作成する。"""
    output2_video_path = os.path.join(root_folder,"output2.mp4")
    # 同名のMP4ファイルが存在する場合は削除
    if os.path.exists(output2_video_path):
        os.remove(output2_video_path)  # 既存のファイルを削除

    # 動画作成のための VideoWriter オブジェクトを作成
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # mp4形式で保存
    video = cv2.VideoWriter(output2_video_path, fourcc, 5.0, (1920, 1080))
    # 指定されたディレクトリ内のすべてのファイルを取得
    files = os.listdir(root_folder)

    # .jpg拡張子のファイルのみをリストアップ
    jpg_files = [file for file in files if file.lower().endswith('.jpg')]
    for file in jpg_files:
        image = cv2.imread(os.path.join(root_folder, file))
        video.write(image)  # 動画ファイルに書き込み

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Merged_json Merge')
    parser.add_argument('--merge_dir', type=str, required=True, help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--former_merge_dir', type=str, required=True, help='動画間のマージ結果を保存するディレクトリのパス')
    parser.add_argument('--frame_count', type=int, required=True, help='動画間の重ねるフレームの数')
    parser.add_argument('--camera_id', type=str, required=True, help='カメラのid')
    args = parser.parse_args()

    #現在の処理している動画の一つ前のmerge_json_folder
    former_merge_folder = args.former_merge_dir
    #現在の動画の一番最初のmerge_json
    merge_folder = args.merge_dir

    camera_id = args.camera_id

    #former_merge_folderに入っている一番最初のファイルを取得
    former_merge_folder_firstfile = get_firstfile(former_merge_folder)

    #動画間引継ぎ用のリスト
    instance_list=[]

    #動画間の途中でカメレオンコードが読み込まれたときのリスト
    reversed_instance_list=[]

    update_instance_ids_based_on_iou(former_merge_folder, merge_folder)

    files = get_merge_json(merge_folder, former_merge_folder_firstfile)

    reversed_files = reversed_get_merge_json(merge_folder, former_merge_folder_firstfile)
    # print(files)
    # print(reversed_files)

    merge_json_correct(files, reversed_files, camera_id)

    # print(instance_list)
    # print(reversed_instance_list)

    copy_merged_json(args.merge_dir, args.former_merge_dir, args.frame_count)

