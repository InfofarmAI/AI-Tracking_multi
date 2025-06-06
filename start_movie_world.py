import cv2
import os
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sys
import mysql.connector
from module.utils3.DB_serch_camera_conf_utils import config
from tkinter import messagebox
import json
import re
from PIL import Image, ImageDraw , ImageFont
import shutil
from datetime import datetime
from module.utils3.Camera_conf_utils import camera_list, world_map

# 画像を更新する関数
def update_image(index):
    global current_index
    current_index = index

    image_path_dict = {}
    img_dict = {}
    hs_dict = {}

    camera_count = 0

    if len(camera_list) % 2 == 1:
        camera_count = len(camera_list) + 1
    else:
        camera_count = len(camera_list)
    
    counter = 0

    # フォルダAとフォルダBから画像を取得してリサイズ
    for camera in camera_list:
        image_path_dict[f"img_path_{camera}"] = image_dict[f"images_{camera}"][current_index]
        img_dict[f"img_{camera}"] = cv2.imread(image_path_dict[f"img_path_{camera}"])
        img_dict[f"img_{camera}"] = cv2.resize(img_dict[f"img_{camera}"], (int(resize_width / ((camera_count + 1) // 2)), int(resize_height / 2)))
        # if camera==5:
        #     img_dict[f"img_{camera}"]=cv2.rotate(img_dict[f"img_{camera}"], cv2.ROTATE_180)
        counter+=1
        if len(camera_list) >= 3 and counter % 2 == 0:
            # print(counter)
            hs_dict[f"com_{camera_list[counter-2]}_{camera_list[counter-1]}"] = np.hstack((img_dict[f"img_{camera_list[counter-2]}"], img_dict[f"img_{camera_list[counter - 1]}"]))
        elif camera == camera_list[-1] and len(camera_list) % 2 ==1:
            infofarm2 = cv2.imread(os.path.join("infofarm", infofarm[0]))
            infofarm2 = cv2.resize(infofarm2, (int(resize_width / ((camera_count+1) // 2)), int(resize_height / 2)))
            hs_dict[f"com_{camera_list[counter - 1]}"] = np.hstack((img_dict[f"img_{camera_list[counter-1]}"], infofarm2))

    if len(hs_dict) >= 2:
        values = list(hs_dict.values())  # 値をリスト化
        left_combined = np.vstack((values[0], values[1]))
    else:
        if len(img_dict) == 2:
            values = list(img_dict.values())
            left_combined = np.vstack((values[0], values[1]))

    img_path_b = images_b[current_index]
    img_b = cv2.imread(img_path_b)
    img_b = cv2.resize(img_b, (resize_width, resize_height))

    

    # 2つの画像を横に連結
    combined_img = np.hstack((left_combined, img_b))

    # 連結画像を表示用に変換
    combined_img = cv2.cvtColor(combined_img, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(combined_img)
    img_tk = ImageTk.PhotoImage(img)
    label.config(image=img_tk)
    label.image = img_tk
    # スライダーの位置も更新
    slider.set(current_index)

# スライダーが動いたときに呼ばれる関数
def on_slider_change(event):
    update_image(slider.get())

# 自動再生を制御する関数
def play_images():
    global is_playing, current_index
    if is_playing:
        current_index = (current_index + 1) % num_images
        update_image(current_index)
        # 100ミリ秒ごとに次の画像を表示
        root.after(100, play_images)

# 再生ボタンが押されたときの処理
def start_playback():
    global is_playing
    if not is_playing:
        is_playing = True
        play_images()

# 停止ボタンが押されたときの処理
def stop_playback():
    global is_playing
    is_playing = False

def close_window():
    root.destroy()

# JSONデータを読み込む関数
def load_options_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

# 更新ボタンが押されたときの処理
def update_text():
    before_selection = before_combobox.get().strip()
    after_selection = after_combobox.get().strip()

    # 入力チェック
    if not before_selection:
        messagebox.showerror("エラー", "変更前の選択肢を選択してください。")
        return
    if not after_selection:
        messagebox.showerror("エラー", "変更後の選択肢を選択してください。")
        return

    # 選択された名前に対応するccidを取得
    selected_option = next((item for item in options if item["name"] == after_selection), None)
    if selected_option is None:
        messagebox.showerror("エラー", "有効な選択肢を選択してください。")
        return

    ccid = selected_option["ccid"]
    log_datetime_first = date_folder + " 00:00:00.000"
    log_datetime_last = date_folder + " 23:59:59.999"
    delete_flg(log_datetime_first, log_datetime_last)
    update_data(ccid,date_folder, str(before_selection))
    update_records = get_update_date(first_file,last_file)

    update_images(update_records, str(before_selection), ccid,camera_id)
    records = get_data(first_file, last_file)
    tid_list = []

    for record in records:
        if record[1] == None:
            if record[7] and str(record[7]) + "_" + str(record[6]) not in tid_list:
                tid_list.append(str(record[7]) + "_" + str(record[6]))
            elif record[7] == None and str(record[2]) + "_" + str(record[6]) not in tid_list:
                tid_list.append(str(record[2]) + "_" + str(record[6]))
    before_combobox["values"] = [tid for tid in tid_list if tid.strip()]
    before_combobox.set("")
    create_mapping_image(records, folder_path, folder_list)

    messagebox.showinfo("成功", f"変更前: {before_selection}, 変更後: {after_selection} (ccid: {ccid})")

def update_data(ccid, log_datetime, TID):
    log_datetime_first = log_datetime + " 00:00:00.000"
    log_datetime_last = log_datetime + " 23:59:59.999"
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    camera_id = TID.split('_')[0]
    TID = TID.split('_')[1]

    try:
        # query = "UPDATE cclog_db.test_logs SET chameleon_code =%s,update_camera_id=null,update_flg=1 where log_datetime >= %s AND log_datetime <= %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s ;"
        query = "UPDATE cclog_db.logs SET chameleon_code =%s,update_camera_id=null,update_flg=1 where log_datetime >= %s AND log_datetime <= %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s ;"
        params=(ccid, log_datetime_first, log_datetime_last, TID, camera_id)

        db.execute(query, params)
        connection.commit()

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def update_images(update_records, before_id, ccid, camera_id):
    last_folder_name = ""
    #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    #HACK　日本語フォント　2024/11/15 torisato(削除予定)
    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)
    
    list_camera_id = before_id.split('_')[0]
    TID=before_id.split('_')[1]

    for record in update_records:
        id_lists=[]
        # print(TID,label['update_camera_id'],list_camera_id,camera_id)
        image_name=datetime.strptime(str(record[7]) if '.' in str(record[7]) else str(record[7]) + '.000', "%Y-%m-%d %H:%M:%S.%f").strftime("%H%M%S%f")[:-3]
        print(image_name)

        root_folder,target_file_name=get_day_and_timestamp(image_name,date_folder_name,str(record[1]))
        print(root_folder,target_file_name)
        image_file,current_folder_name=find_file(root_folder, target_file_name)
        # print(f"root_folder:{root_folder}")
        # print(f"target_file_name:{target_file_name}")
        # print(f"image_file:{image_file}")
        # 画像を読み込む
        if image_file != None:
            image = cv2.imread(image_file)
            cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
            text = cc['name']
            #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
            image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

            #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
            draw = ImageDraw.Draw(image_pil)

            # 画像にテキストを描画
            if ccid not in id_lists:
                # draw.text((label['x1'], int((label['y1']+label['y2'])/2-40)), text, font=font, fill=(0, 255, 255))
                draw.text((int(record[3]), int((int(record[4])+int(record[6]))/2-40)), text, font=font, fill=(0, 255, 255))
                # Pillow形式からcv2形式に戻す
                image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
            # image = cv2.putText(image, str(item[1]), (label['x1'], int((label['y1']+label['y2'])/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                cv2.imwrite(image_file,image)
                id_lists.append(ccid)
            if last_folder_name != current_folder_name and last_folder_name != "":
                movie_create(last_folder_name)
            last_folder_name=current_folder_name
    if last_folder_name != "":
            movie_create(last_folder_name)

# 数値検証関数
def validate_numeric_input(new_value):
    # 空文字は許容（入力を消す場合）
    if new_value == "":
        return True
    # 数値として解釈可能かを確認
    return new_value.isdigit()

def get_day_and_timestamp(filename,formatted_date,camera_id):
    # フォーマットして返す
    return camera_id+"/MOVIE_FOLDER"+"/"+formatted_date,str(filename)+".jpg"

def find_file(root_folder, target_file_name):
    # 指定したフォルダ内の全てのサブフォルダを再帰的に検索
    for root, dirs, files in os.walk(root_folder):
        if target_file_name in files:
            return root +"/"+target_file_name , root
    return None,None

def movie_create(root_folder):
    # 同名のMP4ファイルが存在する場合は削除
    if os.path.exists(os.path.join(root_folder,"output2.mp4")):
        os.remove(os.path.join(root_folder,"output2.mp4"))  # 既存のファイルを削除

    # 動画作成のための VideoWriter オブジェクトを作成
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # mp4形式で保存
    video = cv2.VideoWriter(os.path.join(root_folder,"output2.mp4"), fourcc, 5.0, (1920, 1080))
    # 指定されたディレクトリ内のすべてのファイルを取得
    files = os.listdir(root_folder)
    
    # .jpg拡張子のファイルのみをリストアップ
    jpg_files = [file for file in files if file.lower().endswith('.jpg')]
    for file in jpg_files:
        image = cv2.imread(root_folder+"/"+file)
        video.write(image)  # 動画ファイルに書き込み

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
            matching_records = [
                record for record in records
                if datetime.strptime(str(record[5]) if '.' in str(record[5]) else str(record[5]) + '.000', "%Y-%m-%d %H:%M:%S.%f").strftime("%H%M%S%f")[:-3] == image_name
            ]
            if not matching_records:
                # 一致するレコードがない場合、空の画像を保存
                image = cv2.imread(origin_image)
                cv2.imwrite(os.path.join(destination_folder, f"{image_name}.jpg"), image)
                print("NO image_name", image_name)
                continue

            id_list=[]
            # print(matching_records)

            # 複数の一致するレコードがある場合にそれぞれ処理
            for record in matching_records:
                # print(record)
                # DBレコードから必要なデータを抽出
                id, chameleon_code,camera_id, center_x, center_y, log_datetime, TID ,update_camera_id = record
                current_log_datetime = datetime.strptime(str(log_datetime) if '.' in str(log_datetime) else str(log_datetime) + '.000', "%Y-%m-%d %H:%M:%S.%f")

                center_x=round(center_x*(1080/world_map[0]))
                # center_x=center_x
                # center_y=center_y
                center_y=round(center_y*(1920/world_map[1]))

                #HACK　取得したIDに文字列"cc_id"が含まれているかチェックする 2024/11/15 torisato(削除予定)
                if chameleon_code is not None:
                    cc = next((item for item in cc_name_dict if item['ccid'] == str(chameleon_code)), None)
                    chameleon_code = cc['name']
                
                # print(former_log_datetime,current_log_datetime)

                # 秒数が不一致の場合、新しい画像を読み込む
                if former_log_datetime is None or former_log_datetime != current_log_datetime:             
                    # print(image_name)
                    # if image_name=="162959000" and image is None:
                    #     print("aaaa")
                    # elif image_name=="162959000" and image is not None:
                    #     print("bbbb")
                        
                    if image is not None:
                        # 画像を保存（前の秒数分を保存する）
                        cv2.imwrite(os.path.join(destination_folder, f"{former_image_name}.jpg"), image)
                        # print(image_name)
                        # print(counter)
                    # 新しい画像を読み込む
                    image = cv2.imread(origin_image)
                    # print(origin_image)
                # else:
                #     print(image_name)

                # 円の中にchameleon_codeまたはTIDを書き込む
                if update_camera_id:
                    text = chameleon_code if chameleon_code else str(update_camera_id) + "_" +str(TID)
                else:
                    text = chameleon_code if chameleon_code else str(camera_id) + "_" +str(TID)

                if text in id_list:
                    continue

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

                id_list.append(text)

            former_cordinate_dict=current_cordinate_dict
            # print(former_cordinate_dict)
            current_cordinate_dict={}

            former_image_name=image_name

            # counter+=1

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
            matching_records = [
                record for record in records
                if datetime.strptime(str(record[5]) if '.' in str(record[5]) else str(record[5]) + '.000', "%Y-%m-%d %H:%M:%S.%f").strftime("%H%M%S%f")[:-3] == image_name
            ]
            if not matching_records:
                # 一致するレコードがない場合、空の画像を保存
                image = cv2.imread(origin_image)
                cv2.imwrite(os.path.join(destination_folder, f"{image_name}.jpg"), image)
                print("NO image_name", image_name)
                continue

            id_list=[]
            # print(matching_records)

            # 複数の一致するレコードがある場合にそれぞれ処理
            for record in matching_records:
                # print(record)
                # DBレコードから必要なデータを抽出
                id, chameleon_code,camera_id, center_x, center_y, log_datetime, TID ,update_camera_id = record
                current_log_datetime = datetime.strptime(str(log_datetime) if '.' in str(log_datetime) else str(log_datetime) + '.000', "%Y-%m-%d %H:%M:%S.%f")

                center_x=round(center_x*(1080/world_map[0]))
                # center_x=center_x
                # center_y=center_y
                center_y=round(center_y*(1920/world_map[1]))

                #HACK　取得したIDに文字列"cc_id"が含まれているかチェックする 2024/11/15 torisato(削除予定)
                if chameleon_code is not None:
                    cc = next((item for item in cc_name_dict if item['ccid'] == str(chameleon_code)), None)
                    chameleon_code = cc['name']
                
                # print(former_log_datetime,current_log_datetime)

                # 秒数が不一致の場合、新しい画像を読み込む
                if former_log_datetime is None or former_log_datetime != current_log_datetime:             
                    # print(image_name)
                    # if image_name=="162959000" and image is None:
                    #     print("aaaa")
                    # elif image_name=="162959000" and image is not None:
                    #     print("bbbb")
                        
                    if image is not None:
                        # 画像を保存（前の秒数分を保存する）
                        cv2.imwrite(os.path.join(destination_folder, f"{former_image_name}.jpg"), image)
                        # print(image_name)
                        # print(counter)
                    # 新しい画像を読み込む
                    image = cv2.imread(origin_image)
                    # print(origin_image)
                # else:
                #     print(image_name)

                # 円の中にchameleon_codeまたはTIDを書き込む
                if update_camera_id:
                    text = chameleon_code if chameleon_code else str(update_camera_id) + "_" +str(TID)
                else:
                    text = chameleon_code if chameleon_code else str(camera_id) + "_" +str(TID)

                if text in id_list:
                    continue

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

                id_list.append(text)

            former_cordinate_dict=current_cordinate_dict
            # print(former_cordinate_dict)
            current_cordinate_dict={}

            former_image_name=image_name

            # counter+=1

def get_data(first_file,last_file):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "SELECT id, chameleon_code, camera_id, center_x, center_y, log_datetime, TID,update_camera_id FROM cclog_db.test_logs where log_datetime BETWEEN %s AND %s;"
        query = "SELECT id, chameleon_code, camera_id, transform_center_x, transform_center_y, log_datetime, TID,update_camera_id FROM cclog_db.logs where log_datetime BETWEEN %s AND %s;"
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

def get_update_date(first_file,last_file):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "SELECT id, camera_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y, log_datetime, TID,update_camera_id FROM cclog_db.test_logs where log_datetime >= %s AND log_datetime < %s AND update_flg=1 ORDER BY camera_id ASC, log_datetime ASC;"
        query = "SELECT id, camera_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y, log_datetime, TID,update_camera_id FROM cclog_db.logs where log_datetime >= %s AND log_datetime < %s AND update_flg=1 ORDER BY camera_id ASC, log_datetime ASC;"
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

def delete_flg(log_datetime_first,log_datetime_last):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "UPDATE cclog_db.test_logs SET update_flg = 0 where log_datetime BETWEEN %s AND %s;"
        query = "UPDATE cclog_db.logs SET update_flg = 0 where log_datetime BETWEEN %s AND %s;"
        params=(log_datetime_first,log_datetime_last)

        db.execute(query,params)
        connection.commit()

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

# メイン処理
if __name__ == "__main__":
    folder_path = sys.argv[1]
    folder_list_str = sys.argv[2]
    date_folder=sys.argv[3]
    date_folder_name=sys.argv[4]
    first_file=sys.argv[5]
    last_file=sys.argv[6]
    tid_list_str=sys.argv[7]
    camera_id=sys.argv[8]
    merged_json_folder="/data/merged_jsons"
    # 文字列をリストに変換
    folder_list = folder_list_str.split(',')
    tid_list=tid_list_str.split(',')
    image_dict = {}
    folder_path_dict={}
    for camera in camera_list:
        image_dict[f"images_{camera}"] = []

    folder_path_b = "MAPPING_FORDER"
    for folder in folder_list:
        for camera in camera_list:
            folder_path_dict[f"folder_path_{camera}"] = os.path.join(str(camera), "MOVIE_FOLDER", str(date_folder_name), str(folder))
            image_dict[f"images_{camera}"].extend(sorted([os.path.join(folder_path_dict[f"folder_path_{camera}"], img) for img in os.listdir(folder_path_dict[f"folder_path_{camera}"]) if img.endswith(".jpg")]))
    images_b = sorted(
        [os.path.join(folder_path_b, img) for img in os.listdir(folder_path_b) if img.endswith(".jpg")],
        key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
    )

    infofarm=[f for f in os.listdir("infofarm") if f.lower().endswith('.jpg')]

    # 各リストの画像数を取得し、最小の数を使う（リストの長さが違う場合に対応）
    num_images = min(len(image_dict[f"images_{camera_list[0]}"]), len(images_b))

    # 現在の画像インデックス
    current_index = 0
    is_playing = False  # 再生中かどうかのフラグ

    # リサイズする幅と高さを設定
    resize_width = 960  # 各画像の幅
    resize_height = 840  # 各画像の高さ

    # ウィンドウを作成
    root = tk.Tk()
    root.title("Dual Video Viewer with Slider and Play/Pause")

    # ラベルに画像を表示
    label = ttk.Label(root)
    label.pack()

    # スライダーを作成
    slider = tk.Scale(root, from_=0, to=num_images - 1, orient=tk.HORIZONTAL, command=on_slider_change)
    slider.pack(fill=tk.X)

    # 検証コマンドを登録
    validate_command = root.register(validate_numeric_input)

    # JSONファイルパス
    json_file_path = "cc_name.txt"

    # JSONデータのロード
    options = load_options_from_json(json_file_path)

    # # ウィンドウを作成
    # root = tk.Tk()
    # root.title("変更後の入力にコンボボックスを使用")

    # 入力フィールドとラベル
    input_frame = ttk.Frame(root)
    input_frame.pack(fill=tk.X, pady=10)

    before_label = ttk.Label(input_frame, text="変更前:")
    before_label.grid(row=0, column=0, padx=5)

    before_combobox = ttk.Combobox(input_frame, width=30, state="readonly")
    before_combobox["values"] = [tid for tid in tid_list if tid.strip()]
    before_combobox.grid(row=0, column=1, padx=5)

    after_label = ttk.Label(input_frame, text="変更後:")
    after_label.grid(row=0, column=2, padx=5)

    # コンボボックスを作成
    after_combobox = ttk.Combobox(input_frame, width=30, state="readonly")
    after_combobox["values"] = [option["name"] for option in options]
    after_combobox.grid(row=0, column=3, padx=5)

    update_button = ttk.Button(input_frame, text="更新", command=update_text)
    update_button.grid(row=0, column=4, padx=5)

    # 再生ボタンを作成
    play_button = tk.Button(root, text="再生", command=start_playback)
    play_button.pack(side=tk.LEFT, padx=5, pady=5)

    # 停止ボタンを作成
    stop_button = tk.Button(root, text="停止", command=stop_playback)
    stop_button.pack(side=tk.LEFT, padx=5, pady=5)

    # 終了ボタンを作成
    close_button = tk.Button(root, text="終了", command=close_window)
    close_button.pack(side=tk.RIGHT, padx=5, pady=5)

    # 最初の画像を表示
    update_image(0)

    # メインループの開始
    root.mainloop()
