import tkinter as tk
import os
import mysql.connector
from utils3.DB_serch_camera_conf_utils import config
import cv2
import shutil
from datetime import datetime
from subprocess import Popen
import json
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from utils3.Camera_conf_utils import *

def open_new_window(button_texts, date_folder_path, folder_path):
    # 新しいウィンドウを作成
    new_window = tk.Toplevel()
    new_window.title("再生動画選択")
    # モーダルウィンドウに設定
    # new_window.grab_set()

    new_buttons = []  # 新しいウィンドウのボタンリスト

    camera_id = folder_path.split('\\')[0]

    # 新しいウィンドウにボタンを配置
    def new_button_clicked(clicked_button, camera_id):
        # すべてのボタンの色を元に戻す
        for button in new_buttons:
            button.config(bg="SystemButtonFace")
        # 押されたボタンの色を黄色にする
        clicked_button.config(bg="yellow")

        #例) -> MOVIE_FOLDER\20241030\171737322
        path = os.path.join(folder_path, date_folder_path, clicked_button['text'])

        folder_list = get_num_folders(os.path.join(folder_path, date_folder_path), clicked_button['text'], num_folders=2)

        first_path = os.path.join(folder_path, date_folder_path, folder_list[0])
        last_path = os.path.join(folder_path, date_folder_path, folder_list[-1])

        # print(first_path)
        first_file, last_file = get_first_and_last_jpg_filenames(first_path, last_path)
        if first_file != None and last_file != None:

            first_file = convert_filename_to_time_format(first_file, date_folder_path)
            last_file = convert_filename_to_time_format(last_file, date_folder_path)

            records = get_data(first_file ,last_file)
            tid_list = []

            #id, chameleon_code,camera_id, transform_center_x, transform_center_y, log_datetime, TID ,update_camera_id
            for record in records:
                TID = str(record['TID'])
                update_camera_id = record['update_camera_id']
                camera_id = str(camera_id)
                if record['chameleon_code'] == None:
                    if update_camera_id != None and str(update_camera_id) + "_" + TID not in tid_list:
                        tid_list.append(str(update_camera_id) + "_" + TID)
                    elif update_camera_id == None and camera_id + "_" + TID not in tid_list:
                        tid_list.append(camera_id + "_" + TID)

            #2024.10.31 torisato
            create_mapping_image(records, os.path.join(folder_path,date_folder_path),folder_list)
            folder_list_str = ','.join(folder_list)  # リストをカンマ区切りの文字列に変換
            if tid_list != []:
                tid_list_str=','.join(tid_list)
            else:
                tid_list_str=""
            date_obj = datetime.strptime(date_folder_path, "%Y%m%d")

            # 希望する形式で出力
            formatted_date = date_obj.strftime("%Y/%m/%d")
            # 他のPythonスクリプトに引数として渡す
            Popen(['python', 'start_movie_world.py', os.path.join(folder_path,date_folder_path),folder_list_str,formatted_date,date_folder_path,first_file,last_file,tid_list_str,str(camera_id)])

    for i, text in enumerate(button_texts):
        row = i // 19
        col = i % 19
        button = tk.Button(new_window, text=text, width=10, height=3)
        button.config(command=lambda b=button: new_button_clicked(b, camera_id))
        button.grid(row=row, column=col, padx=10, pady=10)
        new_buttons.append(button)

    # new_window.wait_window()  # ウィンドウが閉じるまで待機（モーダル化）


def create_buttons(button_texts,folder_path):
    root = tk.Tk()
    root.title("日付選択")
    # モーダルウィンドウに設定
    root.grab_set()

    buttons = []  # すべてのボタンを格納するリスト

    def button_clicked(clicked_button, buttons):
        # すべてのボタンの色を元に戻す
        for button in buttons:
            button.config(bg="SystemButtonFace")
        # 押されたボタンの色を黄色にする
        clicked_button.config(bg="yellow")
        #print(f"Button clicked: {clicked_button['text']}")

        # 新しいウィンドウに指定のボタンを表示
        #new_button_texts = [f"New Button {i+1}" for i in range(15)]
        subfolders = get_subfolders(folder_path + "/" + clicked_button['text'])
        open_new_window(subfolders,clicked_button['text'],folder_path)

    # メインウィンドウのボタンを配置
    for i, text in enumerate(button_texts):
        row = i // 10
        col = i % 10
        button = tk.Button(root, text=text, width=10, height=3)
        button.config(command=lambda b=button: button_clicked(b, buttons))
        button.grid(row=row, column=col, padx=10, pady=10)
        buttons.append(button)

    root.mainloop()
    # root.wait_window()  # ウィンドウが閉じるまで待機（モーダル化）

def camera_button_clicked(clicked_button, buttons):
    # すべてのボタンの色を元に戻す
    for button in buttons:
        button.config(bg="SystemButtonFace")
    # 押されたボタンの色を黄色にする
    clicked_button.config(bg="yellow")
    #print(f"Button clicked: {clicked_button['text']}")

    # 新しいウィンドウに指定のボタンを表示
    #new_button_texts = [f"New Button {i+1}" for i in range(15)]
    folder_path="MOVIE_FOLDER"
    folder_path=os.path.join(str(clicked_button['text']),folder_path)
    subfolders = get_subfolders(folder_path)
    
    create_buttons(subfolders,folder_path)

def camera_create_buttons(camera_list):
    root = tk.Tk()
    root.title("カメラ選択")
    # root.grab_set()

    buttons = []  # すべてのボタンを格納するリスト

    # メインウィンドウのボタンを配置
    for i, text in enumerate(camera_list):
        row = i // 10
        col = i % 10
        button = tk.Button(root, text=text, width=10, height=3)
        button.config(command=lambda b=button: camera_button_clicked(b, buttons))
        button.grid(row=row, column=col, padx=10, pady=10)
        buttons.append(button)

    root.mainloop()

def get_subfolders(folder_path):
    # 指定したフォルダ内のサブフォルダの名前を取得
    subfolder_names = [f.name for f in os.scandir(folder_path) if f.is_dir()]
    return subfolder_names

def get_first_and_last_jpg_filenames(first_path,last_path):
    # 指定したフォルダ内のファイル名をリストアップ
    first_files = [f for f in os.listdir(first_path) if f.lower().endswith('.jpg')]
    last_files = [f for f in os.listdir(last_path) if f.lower().endswith('.jpg')]
    
    # print(first_files)
    # ファイル名を昇順にソート
    first_files.sort()

    # 最初と最後のファイル名を取得
    if first_files:
        first_file = first_files[0]
        last_file = last_files[-1]
        return first_file, last_file
    else:
        return None, None  # jpgファイルがない場合
    
def get_data(first_file,last_file):
    connection = mysql.connector.connect(**config)
    db = connection.cursor(dictionary=True)

    try:
        # query = "SELECT id, chameleon_code,camera_id, center_x, center_y, log_datetime, TID ,update_camera_id FROM cclog_db.test_logs where log_datetime BETWEEN %s AND %s;"
        query = "SELECT id, chameleon_code,camera_id, transform_center_x, transform_center_y, log_datetime, TID ,update_camera_id FROM cclog_db.logs where log_datetime BETWEEN %s AND %s;"
        params=(first_file,last_file)

        db.execute(query,params) # 有効な区分のカメラのみ取得
        # 結果を取得
        results = db.fetchall()

        return results

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def convert_filename_to_time_format(filename, date_string):
    # 拡張子を除去し、数値部分を取得
    base_name = os.path.splitext(filename)[0]
    
    # 文字列を整数に変換
    total_seconds = int(base_name)
    
    # 時、分、秒、ミリ秒に変換
    hours = total_seconds // 10000000
    minutes = (total_seconds // 100000) % 100
    seconds = (total_seconds // 1000) % 100
    milliseconds = total_seconds % 1000

    # 日付部分をフォーマット
    formatted_date = f"{date_string[:4]}/{date_string[4:6]}/{date_string[6:8]}"

    # フォーマットして返す
    return f"{formatted_date} {hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"

def create_mapping_image(records, folder_path,folder_list):
    """
    取得したデータからperson_map.jpgにマッピング座標を書き込む処理

    :param records:DBから取得したデータレコード
    """
    #前回の座標を確認する辞書
    former_cordinate_dict={}
    current_cordinate_dict={}

    # former_clog_datetime を初期化
    former_log_datetime = None
    image = None
    origin_image = "person_map.jpg"
    destination_folder = "MAPPING_FORDER"
    former_image_name=None

    counter=0

    # MAPPING_FORDERフォルダが存在しない場合は削除
    if os.path.exists(destination_folder):
        shutil.rmtree(destination_folder)
    os.makedirs(destination_folder)

    #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    #HACK　日本語フォント　2024/11/15 torisato(削除予定)
    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)

    # for id, chameleon_code, center_x, center_y, log_datetime, TID in records:
    for folder in folder_list:
        image_path= os.path.join(folder_path,folder)
        # フォルダ内のすべての.jpgファイルを取得
        image_names_folder = [f for f in os.listdir(image_path) if f.endswith(".jpg")]
        # print(image_names_folder)
        # print(records)

        for image_name in image_names_folder:
            # 拡張子を除去して名前を取得
            image_name = os.path.splitext(image_name)[0]
            # image_nameに対応するすべてのlog_datetimeを持つレコードを取得
            # matching_records = [
            #     record for record in records
            #     if datetime.strptime(str(record[5]) if '.' in str(record[5]) else str(record[5]) + '.000', "%Y-%m-%d %H:%M:%S.%f").strftime("%H%M%S%f")[:-3] == image_name
            # ]
            matching_records = [
                record for record in records
                if record['log_datetime'].strftime("%H%M%S%f")[:-3] == image_name
            ]
            if not matching_records:
                # 一致するレコードがない場合、空の画像を保存
                image = cv2.imread(origin_image)
                cv2.imwrite(os.path.join(destination_folder, f"{image_name}.jpg"), image)
                print("NO image_name", image_name)
                former_image_name=image_name
                continue

            # print(matching_records)
            time_dict={}
            for record in matching_records:
                # id, chameleon_code,camera_id, center_x, center_y, log_datetime, TID ,update_camera_id = record
                id = record['id']
                chameleon_code = record['chameleon_code']
                camera_id = record['camera_id']
                center_x = record['transform_center_x']
                center_y = record['transform_center_y']
                log_datetime = record['log_datetime']
                TID = record['TID']
                update_camera_id = record['update_camera_id']

                if chameleon_code is not None:
                    cc = next((item for item in cc_name_dict if item['ccid'] == str(chameleon_code)), None)
                    chameleon_code = cc['name']

                if update_camera_id:
                    text = chameleon_code if chameleon_code else str(update_camera_id) + "_" +str(TID)
                else:
                    text = chameleon_code if chameleon_code else str(camera_id) + "_" +str(TID)

                if text not in time_dict:
                    time_dict[text] = record
                else:
                    if time_dict[text]['transform_center_y'] >= 477 and int(time_dict[text]['camera_id']) == camera1:
                        time_dict[text] = record
                    elif time_dict[text]['transform_center_y'] <= 447 and int(time_dict[text]['camera_id']) == camera5:
                        time_dict[text] = record

            # print(time_dict)

            # 複数の一致するレコードがある場合にそれぞれ処理
            for text, record in time_dict.items():
                # print(record)
                # DBレコードから必要なデータを抽出
                # id, chameleon_code,camera_id, center_x, center_y, log_datetime, TID ,update_camera_id = record
                id = record['id']
                chameleon_code = record['chameleon_code']
                camera_id = record['camera_id']
                center_x = record['transform_center_x']
                center_y = record['transform_center_y']
                log_datetime = record['log_datetime']
                TID = record['TID']
                update_camera_id = record['update_camera_id']

                # current_log_datetime = datetime.strptime(str(log_datetime) if '.' in str(log_datetime) else str(log_datetime) + '.000', "%Y-%m-%d %H:%M:%S.%f")
                current_log_datetime = log_datetime

                center_x = round(center_x * (1080 / world_map[0]))
                center_y = round(center_y * (1920 / world_map[1]))

                #HACK　取得したIDに文字列"cc_id"が含まれているかチェックする 2024/11/15 torisato(削除予定)

                # print(former_log_datetime,current_log_datetime)

                # 秒数が不一致の場合、新しい画像を読み込む
                if former_log_datetime is None or former_log_datetime != current_log_datetime:
                    # 新しい画像を読み込む
                    image = cv2.imread(origin_image)

                if former_cordinate_dict and text in former_cordinate_dict:
                    # print(former_cordinate_dict[text][0],center_x)
                    # print(former_cordinate_dict[text][1],center_y)
                    if former_cordinate_dict[text][0] -30 < center_x < former_cordinate_dict[text][0]+30:
                        if former_cordinate_dict[text][1] -60 < center_y < former_cordinate_dict[text][1]+60:
                            # print("変更有")
                            center_x=former_cordinate_dict[text][0]
                            center_y=former_cordinate_dict[text][1]

                # 一致している場合、同じ画像に〇を描く
                cv2.circle(image, ( round(center_x / 10) * 10, round(center_y / 10) * 10), 50, (0, 0, 0), 3)

                #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
                image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
                draw = ImageDraw.Draw(image_pil)

                # 画像にテキストを描画
                if text == chameleon_code:
                    draw.text((round(center_x / 10) * 10 - 30, round(center_y / 10) * 10 - 30), text, font=font, fill=(0, 0, 0))
                else:
                    draw.text((round(center_x / 10) * 10 - 20, round(center_y / 10) * 10 - 30), text, font=font, fill=(0, 0, 0))
                # Pillow形式からcv2形式に戻す
                image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)

                # former_created を更新
                former_log_datetime = current_log_datetime

                current_cordinate_dict[text]=(center_x,center_y)
            
            # 秒数が不一致の場合、新しい画像を読み込む

            if image is not None:
                # 画像を保存（前の秒数分を保存する）
                cv2.imwrite(os.path.join(destination_folder, f"{image_name}.jpg"), image)

            former_cordinate_dict=current_cordinate_dict
            # print(former_cordinate_dict)
            current_cordinate_dict={}

            former_image_name=image_name

            # counter+=1

def get_num_folders(base_dir, target_folder, num_folders=5):
    # 指定フォルダのサブフォルダを取得してソート
    subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]
    subfolders.sort()  # 昇順にソート

    # ターゲットフォルダの位置を取得
    try:
        target_index = subfolders.index(target_folder)
    except ValueError:
        raise ValueError(f"指定したフォルダ '{target_folder}' が見つかりませんでした。")

    # 指定フォルダから最大 num_folders を取得
    return subfolders[target_index:target_index + num_folders]

if __name__ == "__main__":

    folder_path="MOVIE_FOLDER"
    folder_path=os.path.join(str(camera_list[0]),folder_path)
    subfolders = get_subfolders(folder_path)
    print(subfolders)
    # ボタンごとに異なるテキストをリストで指定
    create_buttons(subfolders,folder_path)
