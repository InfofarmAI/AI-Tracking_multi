import argparse
import os
from utils3.DB_serch_camera_conf_utils import config
import mysql.connector
import cv2
import shutil
from datetime import datetime
import json
from PIL import Image, ImageDraw , ImageFont
import numpy as np
from collections import defaultdict
import math
import re
from utils3.Camera_conf_utils import camera_list, camera_pairs, CAMERA_AREA
import time

def get_data(first_file,last_file,x_range_start,x_range_end,y_range_start,y_range_end,camera_id1,camera_id2):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "SELECT id, camera_id, chameleon_code, center_x, center_y, log_datetime, TID, update_camera_id FROM cclog_db.test_logs where log_datetime BETWEEN %s AND %s AND center_x BETWEEN %s AND %s AND center_y BETWEEN %s AND %s AND (camera_id = %s OR camera_id = %s);"
        query = "SELECT id, camera_id, chameleon_code, center_x, center_y, log_datetime, TID, update_camera_id FROM cclog_db.logs where log_datetime BETWEEN %s AND %s AND center_x BETWEEN %s AND %s AND center_y BETWEEN %s AND %s AND (camera_id = %s OR camera_id = %s);"
        params=(first_file,last_file,x_range_start,x_range_end,y_range_start,y_range_end,camera_id1,camera_id2)

        db.execute(query,params) # 有効な区分のカメラのみ取得
        # 結果を取得
        results = db.fetchall()

        return results

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()


def id_handover(results):
    # log_datetimeごとにデータをグループ化
    grouped_data = defaultdict(list)
    for row in results:
        # print(row[5])
        grouped_data[row[5]].append(row)

    # log_datetimeごとのペアを生成
    pairs = []

    #ペア管理用indexリスト
    pair_index_list=[]

    #ペアにしないリスト
    not_pairs=[]

    pairs_list=[]

    for log_datetime, records in grouped_data.items():
        used_indices = set()  # 既にペアリングされたレコードのインデックスを追跡
        odd_list=[]

        for i, record1 in enumerate(records):
            for j, record2 in enumerate(records):
                if (
                    i != j and 
                    j not in used_indices and 
                    record1[1] != record2[1]  # カメラIDが異なるものを選択
                ):
                    # 距離を計算
                    distance = math.sqrt(
                        (record1[3] - record2[3])**2 +
                        (record1[4] - record2[4])**2
                    )
                    # print(distance)
                    if distance <= 150:
                        id1 = "cc_id" + str(record1[2]) if record1[2] is not None else str(record1[6])
                        id2 = "cc_id" + str(records[j][2]) if records[j][2] is not None else str(records[j][6])

                        # カメラID順でペアを一貫性のある順序に
                        camera_id1 = record1[1]
                        camera_id2 = records[j][1]

                        update_camera_id1=record1[7]
                        update_camera_id2=records[j][7]

                        if update_camera_id1 and update_camera_id2:
                            if update_camera_id1 < update_camera_id2:
                                pair = ((update_camera_id1,id1),(update_camera_id2,id2))
                            elif update_camera_id1 == update_camera_id2:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((update_camera_id1,id1),(update_camera_id2,id2))
                                    else:
                                        pair = ((update_camera_id2,id2),(update_camera_id1,id1))
                                else:
                                    pair = ((update_camera_id1,id1),(update_camera_id2,id2))
                            else:
                                pair = ((update_camera_id2,id2),(update_camera_id1,id1))

                        elif update_camera_id1 and update_camera_id2==None:
                            if update_camera_id1 < camera_id2:
                                pair = ((update_camera_id1,id1),(camera_id2,id2))
                            elif update_camera_id1 == camera_id2:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((update_camera_id1,id1),(camera_id2,id2))
                                    else:
                                        pair = ((camera_id2,id2),(update_camera_id1,id1))
                                else:
                                    pair = ((update_camera_id1,id1),(camera_id2,id2))
                            else:
                                pair = ((camera_id2,id2),(update_camera_id1,id1))
                        elif update_camera_id1==None and update_camera_id2:
                            if camera_id1 < update_camera_id2:
                                pair = ((camera_id1,id1),(update_camera_id2,id2))
                            elif update_camera_id2 == camera_id1:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((camera_id1,id1),(update_camera_id2,id2))
                                    else:
                                        pair = ((update_camera_id2,id2),(camera_id1,id1))
                                else:
                                    pair = ((camera_id1,id1),(update_camera_id2,id2))
                            else:
                                pair = ((update_camera_id2,id2),(camera_id1,id1))
                        else:
                            if camera_id1 < camera_id2:
                                pair = ((camera_id1,id1),(camera_id2,id2))
                            else:
                                pair = ((camera_id2,id2),(camera_id1,id1))

                        odd_list.append((pair,distance,i,j))
                        if distance==78.29431652425353:
                            print(log_datetime,record1,record2)
        # print(odd_list)    
        if odd_list:
            odd_list_sorted = sorted(odd_list, key=lambda x: x[1])
            # print("odd",odd_list_sorted)
            counter=0
            used_list=[]
            for odd in odd_list_sorted:
                if counter == len(records) // 2:
                    if odd[0] not in not_pairs:
                            not_pairs.append(odd[0])

                if counter == 0:
                    if (odd[0],odd[1]) not in pairs_list and odd[0] not in not_pairs:
                        pairs_list.append((odd[0],odd[1]))
                        used_list.append(odd[2])
                        used_list.append(odd[3])
                        counter+=1
                    elif odd[0] not in not_pairs:
                        not_pairs.append(odd[0])
                else:
                    if odd[2] not in used_list and odd[3] not in used_list:
                        pairs_list.append((odd[0],odd[1]))
                        used_list.append(odd[2])
                        used_list.append(odd[3])
                        counter+=1
                    else:
                        if odd[0] not in not_pairs:
                            not_pairs.append(odd[0])

                for i, (left, right) in enumerate(pairs_list):
                    # print(left,right,odd[0],odd[1])
                    if left == odd[0]:
                        if right > odd[1]:
                            pairs_list[i] = (left, odd[1])  # 右側を更新
                        break

    pairs_list_sorted = sorted(pairs_list, key=lambda x: x[1])
    print("pairs_list",pairs_list_sorted)
    for pair,distance in pairs_list_sorted:
        # count=0
        # for i, (left, right) in enumerate(pairs):
        #     if right == pair[1]:
        #         if pair not in not_pairs:
        #             not_pairs.append(pair)
        #         count+=1
        #         break

        # if count==0:
        #     if pair not in pairs:
        #         pairs.append(pair)
        if pair not in pairs:
            pairs.append(pair)
    print("pairs",pairs)

    return pairs,not_pairs

def create_pair(record1, record2):
    """
    2つのレコードをペアとして一意に識別可能なタプルに変換。
    距離で計算後、ccidがあればそれを使用、なければtidを使用。
    """
    id1 = "cc_id" + record1["chameleon_code"] if record1["chameleon_code"] is not None else record1["TID"]
    id2 = "cc_id" + record2["chameleon_code"] if record2["chameleon_code"] is not None else record2["TID"]
    return (id1, id2)

# def pairs_processing(pairs,log_datetime_first,log_datetime_last,camera_id1,camera_id2):
#     delete_flg(log_datetime_first,log_datetime_last)
#     for pair in pairs:
#         if pair[0] in "ccid" and pair[1] not in "ccid":
#             update_data(str(pair[0]).replace("ccid",""),log_datetime_first,log_datetime_last,pair[1],camera_id1,True)
#         elif pair[1] in "ccid" and pair[0] not in "ccid":
#             update_data(str(pair[1]).replace("ccid",""),log_datetime_first,log_datetime_last,pair[0],camera_id2,True)
#         elif pair[0] not in "ccid" and pair[1] not in "ccid":
#             update_data(pair[0],log_datetime_first,log_datetime_last,pair[1],camera_id1,False)

def pairs_processing(updated_list,log_datetime_first,log_datetime_last):
    delete_flg(log_datetime_first,log_datetime_last)
    for item in updated_list:
        # print(item[1][1])
        if "cc_id" in item[1][1]:
            # print(str(item[1][1]).replace("cc_id",""))
            update_data(str(item[1][1]).replace("cc_id",""),log_datetime_first,log_datetime_last,int(item[0][1]),item[0][0],True,None)
        else:
            update_data(str(item[1][1]),log_datetime_first,log_datetime_last,int(item[0][1]),item[0][0],False,item[1][0])

def update_data(ccid,log_datetime_first,log_datetime_last,TID,camera_id,ccid_flg,update_camera_id):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        if ccid_flg:
            # query = "UPDATE cclog_db.test_logs SET chameleon_code =%s,update_flg=1,update_camera_id=null where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            query = "UPDATE cclog_db.logs SET chameleon_code =%s,update_flg=1,update_camera_id=null where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            params=(ccid,log_datetime_first,log_datetime_last,TID,camera_id)
        else:
            # query = "UPDATE cclog_db.test_logs SET TID =%s,update_flg=1,update_camera_id=%s where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            query = "UPDATE cclog_db.logs SET TID =%s,update_flg=1,update_camera_id=%s where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            params=(ccid,update_camera_id,log_datetime_first,log_datetime_last,TID,camera_id)

        db.execute(query,params)
        connection.commit()

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

def time_format(strat_time):

    # 日付部分をフォーマット
    formatted_date = datetime.now().strftime("%Y/%m/%d")

    # フォーマットして返す
    return formatted_date + f" {strat_time}",formatted_date + " 23:59:59.999"

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

# def update_images(first_file,last_file,x_range_start,x_range_end,y_range_start,y_range_end,camera_id1,camera_id2,merge_dir,camera_id):
#     #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
#     with open('cc_name.txt', 'r', encoding='utf-8') as file:
#         cc_name_dict = json.load(file)

#     #HACK　日本語フォント　2024/11/15 torisato(削除予定)
#     font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)
#     results=get_update_date(first_file,last_file,x_range_start,x_range_end,y_range_start,y_range_end,camera_id1,camera_id2)
#     for row in results:
#         #画像に更新処理をかける
#         filename=row["log_datetime"].strftime("%H%M%S%f")[:9]+".jpg"
#         root_folder=camera_id+"/MOVIE_FOLDER"+"/"+datetime.now().strftime("%Y%m%d")
#         image_file,current_folder_name=find_file(root_folder, filename)
#         merged_json_name="mask_" +"/"+row["log_datetime"].strftime("%H%M%S%f")[:9]+".json"
#         if image_file != None:
#             image = cv2.imread(image_file)
#             if row["chameleon_code"]!=None:
#                 ccid = int(str(row["chameleon_code"]))
#                 cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
#                 text = cc['name']
#                 #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
#                 image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

#                 #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
#                 draw = ImageDraw.Draw(image_pil)

#                 # 画像にテキストを描画
#                 draw.text((int(row['top_left_x']), int((int(row['top_left_y'])+int(row['bottom_right_y']))/2-40)), text, font=font, fill=(0, 255, 0))
#                 # Pillow形式からcv2形式に戻す
#                 image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
#                 # image = cv2.putText(image, str(item[1]), (label['x1'], int((label['y1']+label['y2'])/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
#             else:
#                 image = cv2.putText(image, str(row['TID']), (int(row['top_left_x']),int((int(row['top_left_y'])+int(row['bottom_right_y']))/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
#             cv2.imwrite(image_file,image)
#             if last_folder_name != current_folder_name and last_folder_name != "":
#                 movie_create(last_folder_name)
#             last_folder_name=current_folder_name
#             update_merged_json(merge_dir,merged_json_name,row['camera_id'],camera_id1,camera_id2,pairs)
#     if last_folder_name != "":
#             movie_create(last_folder_name)

def update_images(first_file,last_file,merge_dir,updated_list,log_last,frame_count):
    #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    #HACK　日本語フォント　2024/11/15 torisato(削除予定)
    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)
    results=get_update_date(first_file,last_file)
    last_folder_name=""
    if results != None:
        # print(results)
        for row in results:
            #画像に更新処理をかける
            filename=row[7].strftime("%H%M%S%f")[:9]+".jpg"
            # print(filename)
            root_folder=str(row[1])+"/MOVIE_FOLDER"+"/"+datetime.now().strftime("%Y%m%d")
            image_file,current_folder_name=find_file(root_folder, filename)
            merged_json_name="mask_" +row[7].strftime("%H%M%S%f")[:9]+".json"
            # print(image_file)
            if image_file != None:
                image = cv2.imread(image_file)
                if row[2]!=None:
                    ccid = int(str(row[2]))
                    cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
                    text = cc['name']
                    #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
                    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                    #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
                    draw = ImageDraw.Draw(image_pil)

                    # 画像にテキストを描画
                    draw.text((int(row[3]), int((int(row[4])+int(row[6]))/2-40)), text, font=font, fill=(0, 255, 0))
                    # Pillow形式からcv2形式に戻す
                    image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
                    # image = cv2.putText(image, str(item[1]), (label['x1'], int((label['y1']+label['y2'])/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                else:
                    image = cv2.putText(image, str(row[9])+"_"+str(row[8]), (int(row[3]),int((int(row[4])+int(row[6]))/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                cv2.imwrite(image_file,image)
                if last_folder_name != current_folder_name and last_folder_name != "":
                    print(last_folder_name)
                    movie_create(last_folder_name)
                last_folder_name=current_folder_name
        if last_folder_name != "":
                # print(last_folder_name)
                movie_create(last_folder_name)

    results=get_update_date(first_file,log_last)
    # print(results)
    if results != None:
        # print(results)
        for row in results:
            merged_json_name="mask_" +row[7].strftime("%H%M%S%f")[:9]+".json"
            update_merged_json(merge_dir,merged_json_name,row[1],updated_list)

    for camera_id in camera_list:
        under_merged_json=get_under_merged_json(merge_dir,frame_count,camera_id)
        for merged_json in under_merged_json:
            update_merged_json(merge_dir,merged_json,camera_id,updated_list)


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

def convert_filename_to_time_format(filename):
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

# def update_merged_json(merge_folder,file,camera_id,camera_id1,camera_id2,pairs):
#     with open(merge_folder +'/'+camera_id+'/' + file, 'r') as f:
#         merge_data = json.load(f)
#         labels = merge_data.get('labels', {})
#         for key, label in labels.items():
#             for item in pairs:
#                 if camera_id1 < camera_id2:
#                     if camera_id==camera_id1:
#                         if label['instance_id'] == item[0]:
#                             label['instance_id']=item[1]
#                             break
#                     else:
#                         if label['instance_id'] == item[1]:
#                             label['instance_id']=item[0]
#                             break
#                 else:
#                     if camera_id==camera_id1:
#                         if label['instance_id'] == item[1]:
#                             label['instance_id']=item[0]
#                             break
#                     else:
#                         if label['instance_id'] == item[0]:
#                             label['instance_id']=item[1]
#                             break
#     with open(merge_folder +'/'+camera_id+'/' + file, 'w') as f:
#                 json.dump(merge_data, f, ensure_ascii=False, indent=4)

def update_merged_json(merge_folder,file,camera_id,updated_list):
    with open('./'+str(camera_id)+'/'+merge_folder +'/' + file, 'r') as f:
        merge_data = json.load(f)
        labels = merge_data.get('labels', {})
        for key, label in labels.items():
            for item in updated_list:
                # print(item)
                # print(item[0][0],camera_id,item[0][1],label['instance_id'],label['update_camera_id'],item[1][1],item[1][0])
                if label['update_camera_id']==0:
                    if int(item[0][0])==camera_id and int(item[0][1])==label['instance_id']:
                        if "cc_id" not in str(item[1][1]):
                            label['update_camera_id']=int(item[1][0])
                            label['instance_id']=int(item[1][1])
                        else:
                            label['instance_id']=item[1][1]
                        break
                    # print("更新されたよ",'./'+str(camera_id)+'/'+merge_folder +'/' + file)
                else:
                    if int(item[0][0])==label['update_camera_id'] and int(item[0][1])==label['instance_id']:
                        if "cc_id" not in str(item[1][1]):
                            label['update_camera_id']=int(item[1][0])
                            label['instance_id']=int(item[1][1])
                        else:
                            label['instance_id']=item[1][1]
                            label['update_camera_id']=0
                        break

    with open('./'+str(camera_id)+'/'+merge_folder +'/' + file, 'w') as f:
        json.dump(merge_data, f, ensure_ascii=False, indent=4)

def copy_merged_json(merged_json_folder,former_merged_json_folder,frame_count,camera_id):

    former_merged_json_folder='./'+str(camera_id)+'/'+former_merged_json_folder
    merged_json_folder='./'+str(camera_id)+'/'+merged_json_folder

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

def get_under_merged_json(merged_json_folder,frame_count,camera_id):
    merged_json_folder='./'+str(camera_id)+'/'+merged_json_folder

    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(merged_json_folder))

    # ファイルが5つ未満の場合、全てのファイルをコピー
    num_files_to_copy = min(frame_count, len(files))

    # 下から5つのファイルを取得
    files_to_copy = files[-num_files_to_copy:]

    return files_to_copy

def pairs_consistency(all_pairs,all_not_pairs):
    update_pairs_list=[]
    all_not_pairs_list=[]
    # print("ap",all_pairs)
    for pairs in all_pairs:
        for pair in pairs:
            if "cc_id" in pair[0][1] and "cc_id" not in pair[1][1]:
                update_pairs_list.append((pair[1],pair[0]))
            elif "cc_id" not in pair[0][1] and "cc_id" in pair[1][1]:
                update_pairs_list.append((pair[0],pair[1]))
            elif "cc_id" not in pair[0][1] and "cc_id" not in pair[1][1]:
                if pair[0][0] == pair[1][0] and int(pair[0][1]) > int(pair[1][1]):
                    update_pairs_list.append((pair[0],pair[1]))
                else:
                    update_pairs_list.append((pair[1],pair[0]))
    # print("up",update_pairs_list)

    for pairs in all_not_pairs:
        for pair in pairs:
            if "cc_id" in pair[0][1] and "cc_id" not in pair[1][1]:
                all_not_pairs_list.append((pair[1],pair[0]))
            elif "cc_id" not in pair[0][1] and "cc_id" in pair[1][1]:
                all_not_pairs_list.append((pair[0],pair[1]))
            elif "cc_id" not in pair[0][1] and "cc_id" not in pair[1][1]:
                if pair[0][0] == pair[1][0] and int(pair[0][1]) > int(pair[1][1]):
                    all_not_pairs_list.append((pair[0],pair[1]))
                else:
                    all_not_pairs_list.append((pair[1],pair[0]))
    # print("b",all_not_pairs_list)

    all_not_pairs_list = [pair for pair in all_not_pairs_list if pair[0] != pair[1]]

    # print("c",all_not_pairs_list)
    
    # 1. キーごとにグループ化
    pair_dict = defaultdict(list)
    for update_pair in update_pairs_list:
        pair_dict[update_pair[0]].append(update_pair[1])
    print(pair_dict)

    # 2. 各グループで条件に従いフィルタリング
    filtered_pairs = []
    for key, values in pair_dict.items():
        remaining_values = []  # 選ばれなかったvaluesを格納するリスト
        # "ccid" を含むものを優先
        ccid_entry = next((v for v in values if "cc_id" in str(v)), None)
        
        if ccid_entry:
            filtered_pairs.append((key, ccid_entry))
            # ccid_entry以外の選ばれなかったものをremaining_valuesに格納
            remaining_values.extend([v for v in values if v != ccid_entry])
            for remaining in remaining_values:
                filtered_pairs.append((remaining, ccid_entry))
        else:
            # "ccid" がない場合、左の値が最小のものを選ぶ
            min_entry = min(values, key=lambda x: (x[0], int(x[1])))
            filtered_pairs.append((key, min_entry))
            # 最小の値以外は残りとして処理
            remaining_values.extend([v for v in values if v != min_entry])
            # print(min_entry)
            # print(remaining_values)
            for remaining in remaining_values:
                filtered_pairs.append((remaining, min_entry))
    print(filtered_pairs)
    filtered_pairs = [pair for pair in filtered_pairs if pair[0] != pair[1]]

    seen = set()
    result = []

    for item in filtered_pairs:
        left_value = item[0]  # タプルの最初の要素
        if left_value not in seen:
            seen.add(left_value)
            result.append(item)
    # print("result",result)

    # 更新処理
    update_dict = {pair[0]: pair[1] for pair in result}
    # print(update_dict)

    updated_list = []
    delete_list=[]
    # print("all",all_not_pairs_list)
    for pair in result:
        if pair[1] in update_dict:  # pair[1] に対応する新しい値があるか確認
            # print("test",(pair[0], update_dict[pair[1]]))
            if (pair[0], update_dict[pair[1]]) in all_not_pairs_list:
                delete_list.append((pair[1],update_dict[pair[1]]))
                updated_list.append(pair)
            else:
                # print(pair)
                updated_list.append((pair[0], update_dict[pair[1]]))
                # print((pair[0], update_dict[pair[1]]))
        else:
            updated_list.append(pair)

    updated_list = [x for x in updated_list if x not in delete_list]

    # updated_list = [pair for pair in updated_list if pair[0] != pair[1]]
    
    return updated_list


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Instance ID Unifier')
    parser.add_argument('--video', type=str, required=True, help='現在処理が行われいるフォルダが記載してあるテキスト')
    parser.add_argument('--merge_dir', type=str, required=True, help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--former_merge_dir', type=str, required=True, help='動画間のマージ結果を保存するディレクトリのパス')
    parser.add_argument('--frame_count', type=int, required=True, help='動画間の重ねるフレームの数')
    parser.add_argument('--camera_id', type=int, required=True, help='カメラのid')
    parser.add_argument('--id_text', type=str, required=True, help='id管理')
    parser.add_argument('--last_camera_id', type=int, required=True, help='最後のカメラid')
    parser.add_argument('--confirm_text', type=str, required=True, help='処理終了確認用')
    args = parser.parse_args()

    startflg=True

    video_path=str(args.video).replace(str(args.camera_id)+"/","")
    print(f"args.camera_id:{args.camera_id},args.last_camera_id:{args.last_camera_id}")

    if args.camera_id != args.last_camera_id:
        startflg=False
        print("yet")
    else:
        while True:  # 無限ループ
            for camera_id in camera_list:
                videotxt_path = args.confirm_text

                # ファイルを開いて1行目を取得
                # with open(videotxt_path, "r", encoding="utf-8") as f:
                #     # found = any(str(camera_id) + "/" + video_path in line for line in f)

                target = video_path.replace("\\", "/")  # バックスラッシュ→スラッシュに変換
                print("target:",target)

                with open("confirm.txt", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        print("line:", line.strip())
                    found = any(target in line.replace("\\", "/").strip() for line in lines)
                    print("found:", found)

                if found == False:
                    time.sleep(5)  # 5秒待機
                    break  # for を抜けて while の先頭からやり直し
            else:
                # for ループが break されずに最後まで実行された場合、while ループを抜ける
                break
    if startflg:
        # フォルダ内のファイル一覧を取得し、ソート
        files = sorted(os.listdir(args.video))
        # print(files)
        # print(files[0])
        # print(files[-1])
        first_file=convert_filename_to_time_format(files[0])
        last_file=convert_filename_to_time_format(files[-1])
        print(f"first_file:{first_file},last_file:{last_file}")

        # strat_time="11:35:40.000"
        strat_time="11:35:40.000"

        log_datetime_first,log_datetime_last=time_format(strat_time)

        all_pairs=[]

        all_not_pairs=[]

        for camera_id1, camera_id2 in camera_pairs:
            x_range_start=CAMERA_AREA[f"{camera_id2}"][0]
            x_range_end=CAMERA_AREA[f"{camera_id1}"][2]
            y_range_start=CAMERA_AREA[f"{camera_id2}"][1]
            y_range_end=CAMERA_AREA[f"{camera_id1}"][3]
            # x_range_start=0
            # x_range_end=world_map[0]
            # y_range_start=0
            # y_range_end=world_map[1]

            results=get_data(first_file,last_file,x_range_start,x_range_end,y_range_start,y_range_end,camera_id1,camera_id2)
            print("results:",results)
            pairs,not_pairs=id_handover(results)
            print(f"pairs:{pairs},not_pairs]{not_pairs}")
            all_pairs.extend(pairs)
            all_not_pairs.extend(not_pairs)

        all_pairs=[all_pairs]
        all_not_pairs=[all_not_pairs]

        all_pairs = [[pair for pair in all_pairs[0] if pair[0] != pair[1]]]
        all_not_pairs = [[pair for pair in all_not_pairs[0] if pair[0] != pair[1]]]

        updated_list=pairs_consistency(all_pairs,all_not_pairs)

        pairs_processing(updated_list,log_datetime_first,log_datetime_last)
        update_images(log_datetime_first,first_file,args.merge_dir,updated_list,log_datetime_last,args.frame_count)

        for camera_id in camera_list:
            copy_merged_json(args.merge_dir,args.former_merge_dir,args.frame_count,camera_id)

        with open(args.id_text, "a") as file:
            file.write(video_path + "\n")
            print("書き込み完了！")