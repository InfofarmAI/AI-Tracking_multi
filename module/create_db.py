"""
create_db.py

このスクリプトは、検出された人物のバウンディングボックス情報（JSON形式）と元画像をもとに、画像上の位置情報を変換・補正し、データベースに記録するためのデータリストを作成し、非同期で挿入処理を行います。

## 主な機能
- 指定されたマージJSONディレクトリ内の最新フレーム情報を読み取り、各インスタンスID（TIDまたはcc_id）を一意に識別
- バウンディングボックスの底辺中心を「画像上の座標」および「変換後の平面座標」に変換
- カメラキャリブレーション情報に基づいて歪み補正・変換を実行
- INSERT用データリストとして保持し、DBへ非同期で登録
- 特定のID（"cc_id"を含む）をもつエントリはCC判定済として別扱い
- 前回のフレームと比較して一貫性を保ちながら、座標の補正/保持を継続
- 処理終了を示すために、指定の `confirm.txt` に対象フレームフォルダを追記

## 実行例:
```bash
python create_db.py \
    --merge_dir ./data/merged_jsons \
    --duration 155 \
    --frame_count 5 \
    --frames_folder ./frames/111643295 \
    --camera_id 1 \
    --confirm_text confirm.txt

引数:
    --merge_dir (str): マージ済みJSONデータが格納されているディレクトリパス
    --duration (int): 使用するフレーム数（例：最新155フレームなど）
    --frame_count (int): 動画間の重なりフレーム数（ID引継ぎ処理のために使用）
    --frames_folder (str): 処理対象の画像フォルダパス（画像ファイルが格納されている場所）
    --camera_id (int): 使用するカメラのID（DB登録・補正パラメータ識別用）
    --confirm_text (str): 処理完了フラグを書き込むテキストファイル

注意事項:
    カメラ情報は utils3.DB_serch_camera_conf_utils 経由でDBから取得
    カメラの歪み補正行列や変換行列は utils3.Camera_conf_utils の CAMERA_CONFIG から読み込み
    INSERT処理は非同期で実行（createpool() 〜 insert()）
    utils3.get_transform_pt により、画像座標から平面変換を実施
    カメラ別の領域定義・スケール調整には CAMERA_AREA, REDUCTION_RATIO が利用される
    拡張予定/コメントアウト済み機能:
    骨格推定（Pose Estimator）による足位置補完
    人物下半身が隠れている場合の位置推定ロジック（未使用ブロックあり）

作成日：2025年5月
作成者：インフォファーム
"""

import os
import json
import cv2
from utils3.get_transform_pt import transform_pt, to_two_dimension
from utils3.DB_insert_utils import get_timestamp_conversion, get_current_time, createpool, insert
from utils3.DB_serch_camera_conf_utils import async_config, fetch_camera_info
from utils3.Camera_conf_utils import REDUCTION_RATIO, CAMERA_AREA, CAMERA_CONFIG
import argparse
import asyncio
import numpy as np
import re
from PIL import Image
# from utils3.Estimator.estimator import PoseEstimator

# def call_insert(camera_id,bbox,bottom_center_x,bottom_center_y,id,time_stamp_number,update_camera_id):
#     #print("a")
#     #取得したIDに文字列"cc_id"が含まれているかチェックする
#     if "cc_id" in str(id):
#         id = int(str(id).replace("cc_id", ""))
#         # print("True",id)
#         #INSER用のデータ格納 2024.10.11 torisato
#         INSERT_DATA_LIST.append([
#             (1), #company_id,
#             (id), #CCID
#             (bbox[0]), #top_leftX
#             (bbox[1]), #top_leftY
#             (bbox[2]), #bottom_rightX
#             (bbox[3]), #bottom_rightY
#             (bottom_center_x), #bottom_center_x
#             (bottom_center_y), #bottom_center_y
#             get_timestamp_conversion(time_stamp_number), #log_datetime
#             get_current_time(), #created
#             get_current_time(), #modified
#             (camera_id), #camera_id
#         ])
#         cc_detection_flg_list.append(True)
#     else:
#         # print("False",id)
#         #INSER用のデータ格納 2024.10.11 torisato
#         INSERT_DATA_LIST.append([
#             (1), #company_id,
#             (bbox[0]), #top_leftX
#             (bbox[1]), #top_leftY
#             (bbox[2]), #bottom_rightX
#             (bbox[3]), #bottom_rightY
#             (bottom_center_x), #bottom_center_x
#             (bottom_center_y), #bottom_center_y
#             get_timestamp_conversion(time_stamp_number), #log_datetime
#             get_current_time(), #created
#             get_current_time(), #modified
#             id,
#             (camera_id), #camera_id
#             update_camera_id
#         ])
#         cc_detection_flg_list.append(False)


def call_insert(camera_id, bbox, bottom_center_x, bottom_center_y, id, time_stamp_number, transform_center_x, transform_center_y):
    """
    物体検出結果を元に INSERT 用データをリストに追加する処理。

    与えられた検出ID（id）に "cc_id" プレフィックスが含まれているかを判定し、
    対応する形式で INSERT データを `INSERT_DATA_LIST` に格納します。
    また、"cc_id" の有無に応じて `cc_detection_flg_list` に真偽値を追加します。

    引数:
        camera_id (int or str): カメラ識別子
        bbox (list): バウンディングボックス [top_left_x, top_left_y, bottom_right_x, bottom_right_y]
        bottom_center_x (float): バウンディングボックスの底辺中心のX座標
        bottom_center_y (float): バウンディングボックスの底辺中心のY座標
        id (int or str): 検出されたID。'cc_id' 接頭辞がある可能性あり
        time_stamp_number (int): タイムスタンプ（数値形式）
        transform_center_x (float): 射影変換後の中心X座標
        transform_center_y (float): 射影変換後の中心Y座標

    グローバル変数:
        INSERT_DATA_LIST (list): DBへの挿入データを保持するグローバルリスト
        cc_detection_flg_list (list): 'cc_id' 付きIDであったかどうかを記録するフラグリスト

    備考:
        - `id` に "cc_id" が含まれている場合はその文字列を除去し、整数に変換して格納。
        - タイムスタンプや日時は `get_timestamp_conversion()` および `get_current_time()` によって変換。
    """
    #取得したIDに文字列"cc_id"が含まれているかチェックする
    if "cc_id" in str(id):
        id = int(str(id).replace("cc_id", ""))
        #INSER用のデータ格納
        INSERT_DATA_LIST.append([
            (1), #company_id,
            (id), #CCID
            (bbox[0]), #top_leftX
            (bbox[1]), #top_leftY
            (bbox[2]), #bottom_rightX
            (bbox[3]), #bottom_rightY
            (bottom_center_x), #bottom_center_x
            (bottom_center_y), #bottom_center_y
            get_timestamp_conversion(time_stamp_number), #log_datetime
            get_current_time(), #created
            get_current_time(), #modified
            (camera_id), #camera_id
            (transform_center_x),
            (transform_center_y),
        ])
        cc_detection_flg_list.append(True)
    else:
        #INSER用のデータ格納
        INSERT_DATA_LIST.append([
            (1), #company_id,
            (bbox[0]), #top_leftX
            (bbox[1]), #top_leftY
            (bbox[2]), #bottom_rightX
            (bbox[3]), #bottom_rightY
            (bottom_center_x), #bottom_center_x
            (bottom_center_y), #bottom_center_y
            get_timestamp_conversion(time_stamp_number), #log_datetime
            get_current_time(), #created
            get_current_time(), #modified
            id,
            (camera_id), #camera_id
            (transform_center_x),
            (transform_center_y),
        ])
        cc_detection_flg_list.append(False)

def create_data(merge_folder, marge_file, M, mtx, dist, new_mtx, frames_data, camera_id, former_cordinate_list):
    """
    JSONアノテーションデータと対応する画像をもとに、対象のバウンディングボックス情報を取得し、
    ピクセル座標と変換後の平面座標を計算してデータ登録処理を行う。

    引数:
        merge_folder (str): JSONファイルが格納されたフォルダのパス。
        marge_file (str): 対象のJSONファイル名。
        M (np.ndarray): 射影変換に使用する3x3行列。
        mtx (np.ndarray): カメラの内部行列（camera matrix）。
        dist (np.ndarray): レンズ歪み係数。
        new_mtx (np.ndarray): 最適化された新しいカメラ行列。
        frames_data (str): 対応する画像ファイルが格納されているフォルダのパス。
        camera_id (int or str): 現在処理対象のカメラID。
        former_cordinate_list (dict): 前フレームまでの座標情報を記憶しておく辞書（追跡用）。

    処理内容:
        - JSONファイルを読み込んで人検出ラベルを取得。
        - 対応する画像を読み込む。
        - 各検出対象ごとに、以下の処理を実施：
            - バウンディングボックスの底辺中心座標を算出。
            - 歪み補正と射影変換を通して、平面マップ上の座標へ変換。
            - ピクセルと変換後の座標を `call_insert()` 関数で登録用データとして蓄積。
        - 登録対象がいない場合、過去の座標情報を一定回数まで引き継ぐ。
        - `former_cordinate_list` を `current_cordinate_list` で更新。
        - 最終的にDBへの非同期登録処理（`insert()`）を実行。
    """
    # 正規表現で9桁の数値を抽出
    match = re.search(r'\d{9}', marge_file)
    if match:
        number = match.group()

    # JSONファイルを読み込む
    with open(os.path.join(merge_folder, marge_file), 'r') as file:
        data = json.load(file)

    # 画像ファイルを読み込む
    image = cv2.imread(os.path.join(frames_data, number) + ".jpg")

    # labels部分を取得
    if data:
        labels = data["labels"]
    else:
        labels = {}

    #id管理用リスト
    id_lists = []
    current_cordinate_list = {}

    if labels:
        # labelsの内容をfor文で回す
        for _, label_info in labels.items():
            #idがリストにない場合
            if "cc_id" in str(label_info['instance_id']):
                str_id = label_info['instance_id']
            else:
                if label_info['update_camera_id'] != 0:
                    str_id = str(label_info['update_camera_id']) + "_" + str(label_info['instance_id'])
                else:
                    str_id = str(camera_id) + "_" + str(label_info['instance_id'])

            if str_id not in id_lists:
                # print("test",label_info['instance_id'])
                bbox = [label_info['x1'], label_info['y1'], label_info['x2'], label_info['y2']]

                # 画像を指定した範囲でカット
                # cropped_image = image.crop((label_info['x1'], label_info['y1'], label_info['x2'], label_info['y2']))

                image_path = number + "_" + str(label_info['instance_id']) + ".jpg"

                output_folder2 = os.path.join(str(camera_id), "test_folder", number) + ".jpg"


                # result=judge_leg(image,image_path,bbox)
                # # result=None
                # # バウンディングボックスの比を計算
                # feet_coordinates,estimate_flg,amount_change_x,amount_change_y= get_corrected_feet_coordinates(bbox,result,labels,label_info['instance_id'],obstacle_list[str(camera_id)],image,output_folder2,camera_id)

                # if former_cordinate_list:
                #     if str_id in former_cordinate_list:
                #         if former_cordinate_list[str_id][0]-20 <= int(feet_coordinates[1]) <= former_cordinate_list[str_id][0]+20:
                #             estimate_flg=False
                #             # print("問題ない",number)
                #         else:
                #             if former_cordinate_list[str_id][1]==False and estimate_flg:
                #                 # print("適用",camera_id,number,feet_coordinates)
                #                 height=former_cordinate_list[str_id][0]-((former_cordinate_list[str_id][4]-label_info['y1'])*amount_change_y+(former_cordinate_list[str_id][3] - int(feet_coordinates[0]))*amount_change_x)
                #                 feet_coordinates=(int(feet_coordinates[0]),height+label_info['y1'])
                #                 # print("変化",camera_id,number,feet_coordinates,former_cordinate_list[str_id][0])
                #                 # estimate_flg=False
                #             elif former_cordinate_list[str_id][1] and estimate_flg and ((former_cordinate_list[str_id][0] > int(feet_coordinates[1])) or (bbox[1] >=0 and bbox[1] <=5)):
                #                 height=former_cordinate_list[str_id][0]-((former_cordinate_list[str_id][4]-label_info['y1'])*amount_change_y+(former_cordinate_list[str_id][3] - int(feet_coordinates[0]))*amount_change_x)
                #                 feet_coordinates=(int(feet_coordinates[0]),height+label_info['y1'])
                #             elif estimate_flg and (bbox[1] >=0 and bbox[1] <=5):
                #                 feet_coordinates=(int(feet_coordinates[0]),bbox[3])
                #             elif former_cordinate_list[str_id][1] and estimate_flg and former_cordinate_list[str_id][0] < int(feet_coordinates[1]):
                #                 if former_cordinate_list[str_id][0]-50 <= int(feet_coordinates[1]) <= former_cordinate_list[str_id][0]+50:
                #                     print("許容範囲")
                #                 else:
                #                     feet_coordinates=(int(feet_coordinates[0]),former_cordinate_list[str_id][0])
                #     else:
                #         if estimate_flg and (bbox[1] >=0 and bbox[1] <=5):
                #             feet_coordinates=(int(feet_coordinates[0]),bbox[3])
                # else:
                #     if estimate_flg and (bbox[1] >=0 and bbox[1] <=5):
                #             feet_coordinates=(int(feet_coordinates[0]),bbox[3])

                # current_cordinate_list[str_id]=(int(feet_coordinates[1])-label_info['y1'],estimate_flg,0,int(feet_coordinates[0]),int(label_info['y1']))

                #骨格推定を使用しない場合
                mid_bottom_x = (label_info['x1'] + label_info['x2']) / 2
                mid_bottom_y = label_info['y2']
                feet_coordinates = (mid_bottom_x, mid_bottom_y)

                # カメラ画角を平面マップに落とし込む
                # 座標の歪み補正
                undistorted_point = cv2.undistortPoints(feet_coordinates, mtx, dist, None, new_mtx)
                # 平面座標に変換
                dst_pt = transform_pt(undistorted_point.reshape(-1), M)

                # バウンディングボックス底辺の中心座標
                # bottom_center_x = dst_pt[0]* REDUCTION_RATIO[str(camera_id)][0]+int(x_cordinate_start)
                # bottom_center_y = dst_pt[1]* REDUCTION_RATIO[str(camera_id)][1]+int(y_cordinate_start)

                #平面座標とピクセル値　2025.05.19 torisato
                bottom_center_x = feet_coordinates[0]
                bottom_center_y = feet_coordinates[1]
                transform_center_x = dst_pt[0]* REDUCTION_RATIO[str(camera_id)][0] + int(x_cordinate_start)
                transform_center_y = dst_pt[1]* REDUCTION_RATIO[str(camera_id)][1] + int(x_cordinate_start)

                id_lists.append(str_id)
                # print("idlist",id_lists)

                #2025.05.19 torisato
                # call_insert(camera_id,bbox,bottom_center_x,bottom_center_y,label_info['instance_id'],number,label_info['update_camera_id'])
                call_insert(camera_id, bbox, bottom_center_x, bottom_center_y, label_info['instance_id'], number, transform_center_x, transform_center_y)

                image = cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[2], int(feet_coordinates[1])), (0, 255, 255), 2)
                # cv2.imwrite(output_folder2, image)
            # else:
            #     print("test2", str_id)

        for key, value in former_cordinate_list.items():
            if key not in current_cordinate_list:
                if value[2] < 3:
                    current_cordinate_list[key] = (value[0], value[1], value[2] + 1, value[3], value[4])

        former_cordinate_list.clear()  # former_cordinate_list をクリア
        former_cordinate_list.update(current_cordinate_list)  # 更新

        loop = asyncio.get_event_loop()
        pool = loop.run_until_complete(createpool(async_config, loop=loop))
        loop.run_until_complete(insert(pool, INSERT_DATA_LIST, cc_detection_flg_list))

def get_merge_json(folder_path, num_files_to_get, frame_count):
    """
    指定されたフォルダから、下位にある JSON ファイルの一部を取得する関数。

    指定した最大ファイル数 (`num_files_to_get`) の中から、
    下から `frame_count` 件を除いた直近のファイル群をリストとして返します。

    引数:
        folder_path (str): ファイルを取得するフォルダのパス。
        num_files_to_get (int): 取得対象とする最大ファイル数。
        frame_count (int): 末尾から除外するファイル数（動画の重なり部分などに使用）。

    戻り値:
        list: 除外後のファイル名（ソート済）のリスト。
    """
    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(folder_path))

    # ファイルが指定した数未満の場合、その数まで取得
    num_files_to_get = min(num_files_to_get, len(files))

    # 下から指定した数のファイルを取得
    files_to_get = files[-(num_files_to_get):-(frame_count)]

    return files_to_get

# def judge_leg(image,cropped_image_path,bbox):
#     FACE_INDICES = range(24, 89)
#     FOOT_INDICES = range(17,22)

#     # 足と腰の閾値スコア
#     THRESHOLD_SCORE = 0.6

#     # キーポイントインデックス (COCO format)
#     RIGHT_HIP = 11
#     LEFT_HIP = 12
#     RIGHT_ANKLE = 15
#     LEFT_ANKLE = 16
#     RIGHT_SHOLDER=6
#     LFFT_SHOLDER=5

#     keypoints_list, kp_scores_list = estimator(image, bbox, 0)
#     #骨格の描写
#     image = estimator.draw(image, keypoints_list, kp_scores_list)
#     output_path = os.path.join(output_folder, cropped_image_path)
#     cv2.imwrite(output_path, image)

#     if keypoints_list != [] and kp_scores_list != []:
#         # キーポイントのリストを取得
#         keypoints = keypoints_list[0]
#         scorespoints = kp_scores_list[0]
#         # print(keypoints)
#         # print(scorespoints)

#         # スコアが0.6以上のキーポイントに絞って、最上点と最下点を計算
#         filtered_keypoints = [point for point, score in zip(keypoints, scorespoints) if score >= THRESHOLD_SCORE]

#         visible_foot_points = [keypoints_list[0][i] for i in FOOT_INDICES if kp_scores_list[0][i] > THRESHOLD_SCORE]
#         if visible_foot_points:
#             if filtered_keypoints:
#                 # 最上点のy座標
#                 top_y = min(point[1] for point in filtered_keypoints if point[1] > 0)

#                 # 最下点のy座標
#                 bottom_y = max(point[1] for point in filtered_keypoints if point[1] > 0)
#                 # y座標の差を計算
#                 y_distance = bottom_y - top_y

#                 # print(f"最上点のy座標: {top_y}, 最下点のy座標: {bottom_y}")
#                 # print(f"y軸の距離: {y_distance} ピクセル bbox :{bbox[3]-bbox[1]}")

#                 if (bbox[3]-bbox[1]) // 2 > y_distance:
#                     return False
#                 else:
#                     return True
#             else:
#                 return False
#         else:
#             return False
#     else:
#         return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Creat DB')
    parser.add_argument('--merge_dir', type=str, required=True, help='マージ結果を保存するディレクトリのパス')
    parser.add_argument('--duration', type=int, default=100, help='セグメントの長さ（フレーム数）')
    parser.add_argument('--frame_count', type=int, required=True, help='動画間の重ねるフレームの数')
    parser.add_argument('--frames_folder', type=str, required=True, help='画像スライスフォルダ')
    parser.add_argument('--camera_id', type=int, required=True, help='カメラのid')
    parser.add_argument('--confirm_text', type=str, required=True, help='処理終了確認用')
    args = parser.parse_args()
    #骨格推定
    # estimator = PoseEstimator('rtmpose',None,'True')

    #カメラ情報の取得
    records = fetch_camera_info() #camera_id, code, ip_address

    #DBのカメラとの調合
    count = 0
    # print("records",records)
    for row in records:
        if int(row['id']) == int(args.camera_id):
            count += 1
            camera_id  = row['id']
            code = row['code']
            x_cordinate_start = CAMERA_AREA[f"{camera_id}"][0]
            y_cordinate_start = CAMERA_AREA[f"{camera_id}"][1]
            break

    if count == 0:
        print("codeなし")

    #設定ファイルから値を取得
    M = to_two_dimension(CAMERA_CONFIG[code])
    mtx, dist, new_mtx = np.array(CAMERA_CONFIG[code]['mtx']), np.array(CAMERA_CONFIG[code]['dist']), np.array(CAMERA_CONFIG[code]['new_mtx'])
    # print("mtx",mtx)
    # print("dist",dist)
    # print("new_mtx",new_mtx)
    INSERT_DATA_LIST = []
    cc_detection_flg_list = []
    former_cordinate_list = {}

    marge_folder = args.merge_dir
    files = get_merge_json(marge_folder, args.duration, args.frame_count)

    # 保存先のフォルダ指定
    output_folder = os.path.join(str(camera_id), "born_folder")
    # フォルダが存在しない場合は作成
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    #for文でmarge_jsonの分だけ回す。
    for file in files:
        INSERT_DATA_LIST = []
        cc_detection_flg_list = []
        create_data(args.merge_dir, file, M, mtx, dist, new_mtx, args.frames_folder, camera_id, former_cordinate_list)

    with open(args.confirm_text, "a") as file:
        file.write(args.frames_folder + "\n")