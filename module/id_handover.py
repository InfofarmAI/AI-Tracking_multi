"""
ID Unifier for Cross-Camera Tracking

このスクリプトは、複数のカメラで取得された人物データに対して、人物のIDの連携と統合を行う処理を実行します。
MySQLデータベースからログデータを取得し、位置情報・ID情報などをもとに人物を照合し、IDの更新処理や
JSONマージファイルへの反映、ラベル付き画像の生成、動画化などを行います。

主な機能：
- 指定された期間・範囲のログデータを取得
- 異なるカメラ間で人物のペアを生成し、IDの対応を決定
- 一貫性のあるIDへの統合（TID ⇄ CCID）
- 対応結果をもとにDBのID情報を更新
- 更新されたIDを画像やJSONマージファイルへ反映
- ラベル付き画像の保存と動画ファイルへの変換
- 一連の処理の完了を管理ファイルに記録

使用方法：
コマンドライン引数により処理対象のフォルダや設定を指定します。
    --video              現在処理が行われている動画のフォルダパス
    --merge_dir          マージJSONファイルの保存先ディレクトリ
    --former_merge_dir   前のフレームのマージJSON保存ディレクトリ
    --frame_count        動画のフレーム重複数
    --camera_id          処理中のカメラID
    --id_text            IDの記録用ファイル
    --last_camera_id     最後のカメラID（全カメラ処理済み確認用）
    --confirm_text       全カメラ処理完了を確認するためのファイル

依存ライブラリ：
- OpenCV (cv2)
- Pillow
- NumPy
- mysql-connector-python
- argparse, os, json, shutil, datetime, subprocess, re, time, math, collections

注意事項：
- カメラごとの設定情報（エリア定義など）は utils3.Camera_conf_utils に依存
- IDの更新対象か否かのロジックが複雑なため、更新リストの生成には pairs_consistency を使用
- 複数のスレッドやプロセスによる同時アクセスを避けるため、処理完了確認ファイルをチェック

作成日：2025年5月
作成者：インフォファーム
"""


import argparse
import os
import mysql.connector
from utils3.DB_serch_camera_conf_utils import config
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

def get_data(first_file, last_file, x_range_start, x_range_end, y_range_start, y_range_end, camera_id1, camera_id2):
    """
    指定された日時・座標・カメラIDの条件に一致するログデータを MySQL データベースから取得する。

    この関数は `cclog_db.logs` テーブルから、以下の条件をすべて満たすレコードを抽出する：
      - log_datetime が `first_file` から `last_file` の範囲内
      - transform_center_x が `x_range_start` 〜 `x_range_end` の範囲内
      - transform_center_y が `y_range_start` 〜 `y_range_end` の範囲内
      - camera_id が `camera_id1` または `camera_id2` に一致する

    Parameters:
        first_file (str or datetime): 抽出対象の開始日時（または文字列形式の時刻）。
        last_file (str or datetime): 抽出対象の終了日時。
        x_range_start (float): X座標の最小値。
        x_range_end (float): X座標の最大値。
        y_range_start (float): Y座標の最小値。
        y_range_end (float): Y座標の最大値。
        camera_id1 (str or int): 抽出対象のカメラIDその1。
        camera_id2 (str or int): 抽出対象のカメラIDその2。

    Returns:
        list[dict]: 抽出されたログレコードのリスト。各要素は辞書形式で、カラム名をキーとする。
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor(dictionary=True)

    try:
        # query = "SELECT id, camera_id, chameleon_code, center_x, center_y, log_datetime, TID, update_camera_id FROM cclog_db.test_logs where log_datetime BETWEEN %s AND %s AND center_x BETWEEN %s AND %s AND center_y BETWEEN %s AND %s AND (camera_id = %s OR camera_id = %s);"

        # TODO 本番用↓
        query = "SELECT id, camera_id, chameleon_code, transform_center_x, transform_center_y, log_datetime, TID, update_camera_id " \
                "FROM cclog_db.logs " \
                "where log_datetime BETWEEN %s AND %s " \
                "AND transform_center_x BETWEEN %s AND %s " \
                "AND transform_center_y BETWEEN %s AND %s " \
                "AND (camera_id = %s OR camera_id = %s);"
        params=(first_file, last_file, x_range_start, x_range_end, y_range_start, y_range_end, camera_id1, camera_id2)

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
    """
    ログデータから時刻ごとに2台の異なるカメラ間で人物が受け渡された可能性のあるIDペアを判定・抽出する。

    与えられた `results`（辞書形式のログレコード一覧）を `log_datetime` ごとにグループ化し、
    同一時刻に異なるカメラに記録された座標が近いIDのペアを構築する。  
    ペアは距離150以内で、IDやupdate_camera_idを考慮しソート・重複排除したうえで整形される。

    条件に一致するものは `pairs` に、条件に一致しなかったかすでに使用済みで採用されなかったペアは `not_pairs` に格納される。

    Parameters:
        results (list[dict]): 
            辞書形式のログデータのリスト。  
            各レコードは以下のキーを含む：
              - 'id' (int): ログID
              - 'camera_id' (int): 撮影カメラのID
              - 'chameleon_code' (str or None): カメレオンID（存在しない場合あり）
              - 'transform_center_x' (float): X座標
              - 'transform_center_y' (float): Y座標
              - 'log_datetime' (datetime): ログの時刻
              - 'TID' (int): トラッキングID
              - 'update_camera_id' (int or None): 更新カメラID（任意）

    Returns:
        tuple:
            - pairs (list[tuple]): 
                距離の近いIDのペアリスト。形式は [((camera_id1, id1), (camera_id2, id2)), ...]
            - not_pairs (list[tuple]):
                採用されなかったペアのリスト。形式は [(camera_id, id), (camera_id, id)], ...
    """
    # log_datetimeごとにデータをグループ化
    grouped_data = defaultdict(list)

    """
    rowの中身
    #例(162492, 1, None, 366, 1004, datetime.datetime(2025, 5, 28, 13, 49, 22, 800000), 4, None)
    #id, camera_id, chameleon_code, transform_center_x, transform_center_y, log_datetime, TID, update_camera_id
    #row[0] = 162492
    #row[1] = 1
    #row[2] = None
    #row[3] = 366
    #row[4] = 1004
    #row[5] = 2025-05-28 13:49:22.800000
    #row[6] = 4
    #row[7] = None
    """

    for row in results:
        grouped_data[row['log_datetime']].append(row)

    # log_datetimeごとのペアを生成
    pairs = []

    #ペア管理用indexリスト
    pair_index_list=[]

    #ペアにしないリスト
    not_pairs=[]

    pairs_list=[]

    for log_datetime, records in grouped_data.items():
        used_indices = set()  # 既にペアリングされたレコードのインデックスを追跡
        odd_list = []

        for i, record1 in enumerate(records):
            for j, record2 in enumerate(records):
                if (
                    i != j and
                    j not in used_indices and
                    record1['camera_id'] != record2['camera_id']  # カメラIDが異なるものを選択
                ):
                    # 距離を計算
                    distance = math.sqrt(
                        (record1['transform_center_x'] - record2['transform_center_x'])**2 +
                        (record1['transform_center_y'] - record2['transform_center_y'])**2
                    )
                    if distance <= 150:
                        id1 = "cc_id" + str(record1['chameleon_code']) if record1['chameleon_code'] is not None else str(record1['TID'])
                        id2 = "cc_id" + str(records[j]['chameleon_code']) if records[j]['chameleon_code'] is not None else str(records[j]['TID'])

                        # カメラID順でペアを一貫性のある順序に
                        camera_id1 = record1['camera_id']
                        camera_id2 = records[j]['camera_id']

                        update_camera_id1 = record1['update_camera_id']
                        update_camera_id2 = records[j]['update_camera_id']

                        if update_camera_id1 and update_camera_id2:
                            if update_camera_id1 < update_camera_id2:
                                pair = ((update_camera_id1, id1), (update_camera_id2, id2))
                            elif update_camera_id1 == update_camera_id2:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((update_camera_id1, id1), (update_camera_id2, id2))
                                    else:
                                        pair = ((update_camera_id2, id2), (update_camera_id1, id1))
                                else:
                                    pair = ((update_camera_id1, id1), (update_camera_id2, id2))
                            else:
                                pair = ((update_camera_id2, id2), (update_camera_id1, id1))

                        elif update_camera_id1 and update_camera_id2 == None:
                            if update_camera_id1 < camera_id2:
                                pair = ((update_camera_id1, id1), (camera_id2, id2))
                            elif update_camera_id1 == camera_id2:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((update_camera_id1, id1), (camera_id2, id2))
                                    else:
                                        pair = ((camera_id2, id2), (update_camera_id1, id1))
                                else:
                                    pair = ((update_camera_id1, id1), (camera_id2, id2))
                            else:
                                pair = ((camera_id2, id2), (update_camera_id1, id1))

                        elif update_camera_id1 == None and update_camera_id2:
                            if camera_id1 < update_camera_id2:
                                pair = ((camera_id1, id1), (update_camera_id2, id2))
                            elif update_camera_id2 == camera_id1:
                                if "cc_id" not in id1 and "cc_id" not in id2:
                                    if int(id1) < int(id2):
                                        pair = ((camera_id1, id1), (update_camera_id2, id2))
                                    else:
                                        pair = ((update_camera_id2, id2), (camera_id1, id1))
                                else:
                                    pair = ((camera_id1, id1), (update_camera_id2, id2))
                            else:
                                pair = ((update_camera_id2, id2), (camera_id1, id1))
                        else:
                            if camera_id1 < camera_id2:
                                pair = ((camera_id1, id1), (camera_id2, id2))
                            else:
                                pair = ((camera_id2, id2), (camera_id1, id1))

                        odd_list.append((pair, distance, i, j))
                        if distance == 78.29431652425353:
                            print(log_datetime,record1,record2)
        # print(odd_list)
        #例)odd_list =  [(((1, 'cc_id2'), (2, '2')), 117.38824472663352, 0, 2), (((1, 'cc_id2'), (2, '2')), 117.38824472663352, 2, 0)]
        if odd_list:
            odd_list_sorted = sorted(odd_list, key=lambda x: x[1])
            counter = 0
            used_list = []
            for odd in odd_list_sorted:
                if counter == len(records) // 2:
                    if odd[0] not in not_pairs:
                            not_pairs.append(odd[0])

                if counter == 0:
                    if (odd[0], odd[1]) not in pairs_list and odd[0] not in not_pairs:
                        pairs_list.append((odd[0], odd[1]))
                        used_list.append(odd[2])
                        used_list.append(odd[3])
                        counter += 1
                    elif odd[0] not in not_pairs:
                        not_pairs.append(odd[0])
                else:
                    if odd[2] not in used_list and odd[3] not in used_list:
                        pairs_list.append((odd[0], odd[1]))
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
    """
    pairs_list = [(((<camera_id1>, <id1>), (<camera_id2>, <id2>)), <distance>)]
    #例) [(((1, '4'), (2, '7')), 14.422205101855956)]
    """
    pairs_list_sorted = sorted(pairs_list, key=lambda x: x[1])

    for pair,distance in pairs_list_sorted:
        if pair not in pairs:
            pairs.append(pair)
    print("pairs", pairs)

    return pairs, not_pairs

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

def pairs_processing(updated_list, log_datetime_first, log_datetime_last):
    """
    ID引き継ぎペアの情報に基づき、対象ログの更新処理を実行する。

    `updated_list` に含まれる各ペアに対し、ログの `chameleon_code` や `update_camera_id` を更新する。
    更新対象期間は `log_datetime_first` から `log_datetime_last` の範囲。
    事前に対象期間のログに対して `update_flg = 0` のリセット処理を行う（delete_flg 関数を使用）。

    パターン：
        - `cc_id` が含まれる場合：`chameleon_code` として扱い、`update_camera_id` は None。
        - `cc_id` が含まれない場合：`update_camera_id` として設定。

    Parameters:
        updated_list (list of tuple): 更新対象のペア一覧。各ペアは ((camera_id, TID), (update_camera_id, chameleon_code or TID)) の形式。
        log_datetime_first (datetime): 更新対象の開始日時。
        log_datetime_last (datetime): 更新対象の終了日時。
    """
    delete_flg(log_datetime_first, log_datetime_last)
    #例)updated_list: [((2, '2'), (1, 'cc_id2')), ((1, '3'), (1, 'cc_id2'))]
    # camera_id: 2
    # TID: 2
    # update_camera_id 1
    # ccid: cc_id2

    for item in updated_list:
        camera_id = item[0][0]
        TID = int(item[0][1])
        update_camera_id = item[1][0]
        ccid = str(item[1][1])

        # print("camera_id:",camera_id)
        # print("TID:",TID)
        # print("ccid:",ccid)
        # print("update_camera_id",item[1][0])

        if "cc_id" in item[1][1]:
            # update_data(str(item[1][1]).replace("cc_id",""), log_datetime_first, log_datetime_last, int(item[0][1]), item[0][0], True, None)
            update_data(ccid.replace("cc_id",""), log_datetime_first, log_datetime_last, TID, camera_id, True, None)
        else:
            # update_data(str(item[1][1]), log_datetime_first, log_datetime_last, int(item[0][1]), item[0][0], False, item[1][0])
            update_data(ccid, log_datetime_first, log_datetime_last, TID, camera_id, False, update_camera_id)

def update_data(ccid, log_datetime_first, log_datetime_last, TID, camera_id, ccid_flg, update_camera_id):
    """
    ログデータを更新し、IDの引き継ぎ情報をデータベースに反映する。

    `ccid_flg` の値に応じて更新処理の内容を切り替える：
      - True の場合は、指定範囲のレコードの `chameleon_code` を `ccid` に更新し、
        `update_camera_id` を NULL に設定する。
      - False の場合は、指定範囲のレコードの `TID` を `ccid` に変更し、
        `update_camera_id` を指定の `update_camera_id` に設定する。

    どちらの場合も、更新対象は `log_datetime` が `log_datetime_first` 〜 `log_datetime_last`
    の範囲にあるものかつ、`TID` と `COALESCE(update_camera_id, camera_id)` が一致するレコード。

    Parameters:
        ccid (str or int): 更新対象の chameleon_code または TID。
        log_datetime_first (datetime): 更新対象の開始日時。
        log_datetime_last (datetime): 更新対象の終了日時。
        TID (int): 対象ログの TID。
        camera_id (int): 対象ログの camera_id。
        ccid_flg (bool): True の場合は chameleon_code を更新、False の場合は TID と update_camera_id を更新。
        update_camera_id (int or None): ccid_flg=False の場合に使用される新しい update_camera_id。
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        if ccid_flg:
            # query = "UPDATE cclog_db.test_logs SET chameleon_code =%s,update_flg=1,update_camera_id=null where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            query = "UPDATE cclog_db.logs SET chameleon_code =%s, update_flg=1, update_camera_id=null where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            params=(ccid, log_datetime_first, log_datetime_last, TID, camera_id)
        else:
            # query = "UPDATE cclog_db.test_logs SET TID =%s,update_flg=1,update_camera_id=%s where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            query = "UPDATE cclog_db.logs SET TID =%s, update_flg=1, update_camera_id=%s where log_datetime BETWEEN %s AND %s AND TID = %s AND COALESCE(update_camera_id, camera_id) = %s;"
            params=(ccid, update_camera_id, log_datetime_first, log_datetime_last, TID, camera_id)

        db.execute(query,params)
        connection.commit()

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def delete_flg(log_datetime_first, log_datetime_last):
    """
    指定された期間に該当するログの `update_flg` を 0 に更新する。

    指定された `log_datetime_first` から `log_datetime_last` の範囲にある
    `cclog_db.logs` テーブル内の全レコードの `update_flg` を 0 に設定することで、
    フラグをリセットまたは論理削除的な処理を行う。

    Parameters:
        log_datetime_first (datetime): 対象期間の開始日時。
        log_datetime_last (datetime): 対象期間の終了日時。
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "UPDATE cclog_db.test_logs SET update_flg = 0 where log_datetime BETWEEN %s AND %s;"
        query = "UPDATE cclog_db.logs SET update_flg = 0 where log_datetime BETWEEN %s AND %s;"
        params=(log_datetime_first, log_datetime_last)

        db.execute(query,params)
        connection.commit()

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def time_format(strat_time):
    """
    指定された時刻を当日の日付と組み合わせて、日時形式の文字列を返す。

    開始時刻（`strat_time`）を "YYYY/MM/DD HH:MM:SS" の形式で返し、
    終了時刻として当日の "23:59:59.999" を設定した文字列も返す。

    Parameters:
        strat_time (str): 開始時刻を表す文字列（例："13:00:00"）

    Returns:
        tuple:
            - str: "YYYY/MM/DD strat_time" の形式の開始日時
            - str: "YYYY/MM/DD 23:59:59.999" の形式の終了日時
    """

    # 日付部分をフォーマット
    formatted_date = datetime.now().strftime("%Y/%m/%d")

    # フォーマットして返す
    return formatted_date + f" {strat_time}", formatted_date + " 23:59:59.999"

def get_update_date(first_file,last_file):
    """
    指定された日時範囲内で update_flg=1 のログをデータベースから取得する。

    `log_datetime` が `first_file`（以上）かつ `last_file`（未満）の範囲に該当し、
    `update_flg=1` であるレコードを、カメラIDとログ日時の昇順で取得する。

    Parameters:
        first_file (str or datetime): 検索範囲の開始日時。
        last_file (str or datetime): 検索範囲の終了日時。

    Returns:
        list[dict]: 該当ログの辞書リスト（各レコードは辞書形式）。
            各レコードには、id, camera_id, chameleon_code,
            top_left_x, top_left_y, bottom_right_x, bottom_right_y,
            log_datetime, TID, update_camera_id が含まれる。
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor(dictionary=True)

    try:
        # query = "SELECT id, camera_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y, log_datetime, TID,update_camera_id FROM cclog_db.test_logs where log_datetime >= %s AND log_datetime < %s AND update_flg=1 ORDER BY camera_id ASC, log_datetime ASC;"
        query = "SELECT id, camera_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y, log_datetime, TID,update_camera_id FROM cclog_db.logs where log_datetime >= %s AND log_datetime < %s AND update_flg=1 ORDER BY camera_id ASC, log_datetime ASC;"
        params=(first_file, last_file)

        db.execute(query, params) # 有効な区分のカメラのみ取得
        # 結果を取得
        results = db.fetchall()
        return results

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def update_images(first_file, last_file, merge_dir, updated_list, log_last, frame_count):
    """
    指定された時間範囲に該当する画像とマージ済みJSONデータを更新し、必要に応じて動画を再生成する。

    処理概要:
        1. update_flg=1 のログ情報を元に該当画像ファイルを特定。
        2. chameleon_code がある場合は、cc_name.txt から名前を取得して画像にラベル描画。
        3. それ以外の場合は update_camera_id_TID の形式で描画。
        4. 更新されたフォルダ単位で `movie_create` 関数を呼び出して動画を再生成。
        5. マージ済みJSONファイル（mask_*.json）も `update_merged_json` 関数で上書き。
        6. フレーム不足の JSON ファイルについても補完更新を実行。

    Parameters:
        first_file (str or datetime): 対象期間の開始日時。
        last_file (str or datetime): 対象期間の終了日時（画像処理の対象範囲）。
        merge_dir (str): マージ済みJSONファイルが格納されたディレクトリパス。
        updated_list (list): ID紐付けペア情報のリスト。形式: [((cam_id, TID), (cam_id, cc_id)), ...]
        log_last (str or datetime): JSON更新対象範囲の終了日時。
        frame_count (int): フレーム不足チェックに使用するしきい値。

    Notes:
        - cc_name.txt により cc_id に対応する表示名を取得します。
        - 出力される画像には、人物IDや名前が直接描画されます。
        - 各MOVIE_FOLDER配下の画像が更新された場合、動画（output.mp4）も再生成されます。
    """
    #HACK 名前辞書読込 2024/11/15 torisato(削除予定)
    with open('cc_name.txt', 'r', encoding='utf-8') as file:
        cc_name_dict = json.load(file)

    #HACK　日本語フォント　2024/11/15 torisato(削除予定)
    font = ImageFont.truetype("NotoSansJP-VariableFont_wght.ttf", 60)
    results = get_update_date(first_file, last_file)
    #results = id, camera_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y, log_datetime, TID, update_camera_id
    last_folder_name = ""
    if results != None:
        for row in results:
            #画像に更新処理をかける
            filename = row['log_datetime'].strftime("%H%M%S%f")[:9]+".jpg"
            # print(filename)
            # root_folder = str(row[1])+"/MOVIE_FOLDER"+"/"+ datetime.now().strftime("%Y%m%d")
            root_folder = os.path.join(str(row['camera_id']), "MOVIE_FOLDER", datetime.now().strftime("%Y%m%d"))
            image_file, current_folder_name = find_file(root_folder, filename)
            merged_json_name = "mask_" + row['log_datetime'].strftime("%H%M%S%f")[:9] + ".json"
            # print(image_file)
            if image_file != None:
                image = cv2.imread(image_file)
                if row['chameleon_code'] != None:
                    ccid = int(str(row['chameleon_code']))
                    cc = next((item for item in cc_name_dict if item['ccid'] == str(ccid)), None)
                    text = cc['name']
                    #HACK cv2の画像をPillow形式に変換 2024/11/15 torisato(削除予定)
                    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

                    #HACK 描画用のDrawオブジェクトを作成 2024/11/15 torisato(削除予定)
                    draw = ImageDraw.Draw(image_pil)

                    # 画像にテキストを描画
                    draw.text((int(row['top_left_x']), int((int(row['top_left_y']) + int(row['bottom_right_y'])) / 2 - 40)), text, font=font, fill=(0, 255, 0))
                    # Pillow形式からcv2形式に戻す
                    image = cv2.cvtColor(np.array(image_pil), cv2.COLOR_BGR2RGB)
                    # image = cv2.putText(image, str(item[1]), (label['x1'], int((label['y1']+label['y2'])/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                else:
                    image = cv2.putText(image, str(row['update_camera_id'])+"_"+str(row['TID']), (int(row['top_left_x']),int((int(row['top_left_y'])+int(row['bottom_right_y']))/2-40)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
                cv2.imwrite(image_file,image)
                if last_folder_name != current_folder_name and last_folder_name != "":
                    print(last_folder_name)
                    movie_create(last_folder_name)
                last_folder_name=current_folder_name
        if last_folder_name != "":
                # print(last_folder_name)
                movie_create(last_folder_name)

    results = get_update_date(first_file, log_last)

    if results != None:
        for row in results:
            merged_json_name = "mask_" + row['log_datetime'].strftime("%H%M%S%f")[:9] + ".json"
            update_merged_json(merge_dir, merged_json_name, row['camera_id'], updated_list)

    for camera_id in camera_list:
        under_merged_json = get_under_merged_json(merge_dir, frame_count)
        for merged_json in under_merged_json:
            update_merged_json(merge_dir, merged_json, camera_id, updated_list)

def find_file(root_folder, target_file_name):
    """
    指定されたフォルダ以下のすべてのサブディレクトリから、指定したファイル名を再帰的に検索し、
    該当ファイルのパスとフォルダパスを返す。

    Parameters:
        root_folder (str): 検索を開始するルートフォルダのパス。
        target_file_name (str): 探したいファイル名（例: "123456789.jpg"）。

    Returns:
        tuple:
            - str: ファイルのフルパス（例: /path/to/file.jpg）
            - str: ファイルが見つかったディレクトリのパス
        ファイルが見つからなかった場合は `(None, None)` を返す。
    """
    # 指定したフォルダ内の全てのサブフォルダを再帰的に検索
    for root, dirs, files in os.walk(root_folder):
        if target_file_name in files:
            return root +"/"+target_file_name , root
    return None, None

def movie_create(root_folder):
    """
    指定フォルダ内の全てのJPEG画像を結合して、MP4形式の動画ファイル (output2.mp4) を生成する。

    処理概要:
        - すでに output2.mp4 が存在する場合は削除。
        - 指定フォルダ内のすべての `.jpg` ファイルを対象に、解像度1920x1080、フレームレート5fpsの動画を作成。

    Parameters:
        root_folder (str): 対象となる画像フォルダのパス。動画もこのフォルダ内に保存される。
    """
    # 同名のMP4ファイルが存在する場合は削除
    if os.path.exists(os.path.join(root_folder, "output2.mp4")):
        os.remove(os.path.join(root_folder, "output2.mp4"))  # 既存のファイルを削除

    # 動画作成のための VideoWriter オブジェクトを作成
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # mp4形式で保存
    video = cv2.VideoWriter(os.path.join(root_folder, "output2.mp4"), fourcc, 5.0, (1920, 1080))
    # 指定されたディレクトリ内のすべてのファイルを取得
    files = os.listdir(root_folder)

    # .jpg拡張子のファイルのみをリストアップ
    jpg_files = [file for file in files if file.lower().endswith('.jpg')]
    for file in jpg_files:
        image = cv2.imread(root_folder+"/"+file)
        video.write(image)  # 動画ファイルに書き込み

def convert_filename_to_time_format(filename):
    """
    指定されたファイル名に含まれる9桁の数値を、時刻形式の文字列に変換する。

    想定するファイル名例:
        "105030000.jpg" → 数値 "105030000" → "YYYY/MM/DD HH:MM:SS.mmm" 形式の時刻に変換

    Parameters:
        filename (str): 9桁の数値が含まれるファイル名。

    Returns:
        str: "YYYY/MM/DD HH:MM:SS.mmm" の形式に整形された文字列。
            （例: "2025/05/30 10:50:30.000"）
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

def update_merged_json(merge_folder, file, camera_id, updated_list):
    """
    指定されたマージ済みJSONファイル内のラベル情報（instance_id, update_camera_id）を更新する。

    この関数は、指定されたJSONファイルを読み込み、`updated_list` に基づいて
    対応する `labels` 内の各 `instance_id` および `update_camera_id` を更新します。
    すでに `update_camera_id` が設定されている場合と、未設定（0）の場合の両方に対応します。

    Parameters:
        merge_folder (str): マージ済みJSONファイルが格納されているディレクトリのパス。
        file (str): 更新対象のJSONファイル名（例: "mask_105030000.json"）。
        camera_id (int): 現在処理しているカメラのID。
        updated_list (list): IDマッピングリスト。要素は ((camera_id, TID), (update_camera_id, ccid)) の形式。

    ファイル構造例:
        JSONファイルの形式:
        {
            "labels": {
                "0": {
                    "instance_id": 3,
                    "update_camera_id": 0,
                    ...
                },
                ...
            }
        }

    処理内容:
        - update_camera_id が 0 の場合: camera_id + TID に一致するものを探して更新。
        - update_camera_id が 0 以外の場合: update_camera_id + TID に一致するものを探して更新。

    Returns:
        None: 処理後、ファイルは上書き保存される。
    """
    # with open('./'+str(camera_id)+'/'+merge_folder +'/' + file, 'r') as f:
    with open(os.path.join(merge_folder, file), 'r') as f:
        merge_data = json.load(f)
        labels = merge_data.get('labels', {})
        for key, label in labels.items():
            for item in updated_list:
                item_camera_id = item[0][0]
                item_TID = item[0][1]
                item_update_camera_id = item[1][0]
                item_ccid = item[1][1]
                if label['update_camera_id'] == 0:
                    if int(item_camera_id) == camera_id and int(item_TID) == label['instance_id']:
                        if "cc_id" not in str(item_ccid):
                            label['update_camera_id'] = int(item_update_camera_id)
                            label['instance_id'] = int(item_ccid)
                        else:
                            label['instance_id'] = item_ccid
                        break
                    # print("更新されたよ",'./'+str(camera_id)+'/'+merge_folder +'/' + file)
                else:
                    if int(item_camera_id) == label['update_camera_id'] and int(item_TID) == label['instance_id']:
                        if "cc_id" not in str(item_ccid):
                            label['update_camera_id'] = int(item_update_camera_id)
                            label['instance_id'] = int(item_ccid)
                        else:
                            label['instance_id'] = item_ccid
                            label['update_camera_id'] = 0
                        break

    # with open('./'+str(camera_id)+'/'+merge_folder +'/' + file, 'w') as f:
    with open(os.path.join(merge_folder, file), 'w') as f:
        json.dump(merge_data, f, ensure_ascii=False, indent=4)

def copy_merged_json(merged_json_folder, former_merged_json_folder, frame_count, camera_id):
    """
    指定されたマージ済みJSONフォルダから、最新のN件のJSONファイルを別フォルダにコピーする。

    この関数は、指定された `merged_json_folder` から最新の `frame_count` 件のJSONファイルを
    `former_merged_json_folder` にコピーします。コピー先のフォルダがすでに存在する場合は削除してから再作成します。

    Parameters:
        merged_json_folder (str): 現在のマージ済みJSONファイルが格納されているフォルダパス。
        former_merged_json_folder (str): コピー先となる過去フレーム用のフォルダパス。
        frame_count (int): コピーする最新フレーム数（最大件数）。
        camera_id (int): カメラID（現状では未使用だが、将来的にフォルダパスに利用される想定）。

    Notes:
        - コピー対象は拡張子に関わらず `merged_json_folder` にある全ファイルが対象となります。
        - `merged_json_folder` に `frame_count` 未満のファイルしかない場合は、全ファイルがコピーされます。
        - コピー先のフォルダは事前に削除され、再作成されます。
    """
    #2025.05.27 torisato
    # former_merged_json_folder='./'+str(camera_id)+'/'+former_merged_json_folder
    # merged_json_folder='./'+str(camera_id)+'/'+merged_json_folder

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

def get_under_merged_json(merged_json_folder, frame_count):
    """
    指定したフォルダから最新の指定件数分のJSONファイル名を取得する。

    この関数は、指定された `merged_json_folder` 内に存在するファイルの一覧をソートし、
    下（新しい順）から `frame_count` 件分のファイル名をリストで返します。

    Parameters:
        merged_json_folder (str): JSONファイルが格納されている対象フォルダのパス。
        frame_count (int): 取得する最大ファイル件数。

    Returns:
        List[str]: 取得対象の最新ファイル名リスト。ファイルが `frame_count` 未満の場合は全件を返します。

    Notes:
        - ファイルのソートは文字列ソートです（通常はファイル名が時系列順であることが前提）。
        - JSON拡張子などのフィルタリングは行っていないため、フォルダ内のすべてのファイルが対象になります。
    """
    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(merged_json_folder))

    # ファイルが5つ未満の場合、全てのファイルをコピー
    num_files_to_copy = min(frame_count, len(files))

    # 下から5つのファイルを取得
    files_to_copy = files[-num_files_to_copy:]

    return files_to_copy

def pairs_consistency(all_pairs, all_not_pairs):
    """
    IDペアの整合性を保ちながら、最新の更新リストを作成する関数。

    与えられた有効なペア（`all_pairs`）および無効なペア（`all_not_pairs`）の情報をもとに、
    以下のルールに従って一貫性のある更新ペアのリスト（`updated_list`）を構築します：

    - `"cc_id"` を含むID（例: "cc_id2"）は優先されます。
    - 両者が `"cc_id"` を含まない場合は、カメラIDが等しい中でTIDの小さい方を優先。
    - 同じキーに対して複数の候補がある場合、一つを残して他は削除対象とする（ルールに従って選別）。
    - `all_not_pairs` に存在する不正ペアは `delete_list` に格納され、更新対象から除外。

    Parameters:
        all_pairs (List[List[Tuple[Tuple[int, str], Tuple[int, str]]]]):
            有効なIDペアのリストのリスト。各要素は2要素のタプル（(camera_id, id)）のペア。
        all_not_pairs (List[List[Tuple[Tuple[int, str], Tuple[int, str]]]]):
            無効と判定されたペアのリストのリスト。

    Returns:
        List[Tuple[Tuple[int, str], Tuple[int, str]]]:
            整合性を保ったペアの更新リスト（updated_list）。
            各要素は (変更元ID, 変更先ID) の形式のタプル。

    Notes:
        - この関数はペア間の重複、循環参照、無効ペア除外などの複雑な処理を含みます。
        - IDは "cc_id" 付きのラベル文字列または整数値文字列であることが想定されています。
    """
    update_pairs_list = []
    all_not_pairs_list = []

    for pairs in all_pairs:
        for pair in pairs:
            if "cc_id" in pair[0][1] and "cc_id" not in pair[1][1]:
                update_pairs_list.append((pair[1], pair[0]))
            elif "cc_id" not in pair[0][1] and "cc_id" in pair[1][1]:
                update_pairs_list.append((pair[0], pair[1]))
            elif "cc_id" not in pair[0][1] and "cc_id" not in pair[1][1]:
                if pair[0][0] == pair[1][0] and int(pair[0][1]) > int(pair[1][1]):
                    update_pairs_list.append((pair[0],pair[1]))
                else:
                    update_pairs_list.append((pair[1],pair[0]))
    # print("up",update_pairs_list)

    for pairs in all_not_pairs:
        for pair in pairs:
            if "cc_id" in pair[0][1] and "cc_id" not in pair[1][1]:
                all_not_pairs_list.append((pair[1], pair[0]))
            elif "cc_id" not in pair[0][1] and "cc_id" in pair[1][1]:
                all_not_pairs_list.append((pair[0], pair[1]))
            elif "cc_id" not in pair[0][1] and "cc_id" not in pair[1][1]:
                if pair[0][0] == pair[1][0] and int(pair[0][1]) > int(pair[1][1]):
                    all_not_pairs_list.append((pair[0], pair[1]))
                else:
                    all_not_pairs_list.append((pair[1], pair[0]))
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
        print("test2:",pair)
        if pair[1] in update_dict:  # pair[1] に対応する新しい値があるか確認
            if (pair[0], update_dict[pair[1]]) in all_not_pairs_list:
                delete_list.append((pair[1],update_dict[pair[1]]))
                updated_list.append(pair)
            else:
                updated_list.append((pair[0], update_dict[pair[1]]))
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

    video_path = str(args.video).replace(str(args.camera_id)+"/","")

    if args.camera_id != args.last_camera_id:
        startflg = False
    else:
        while True:  # 無限ループ
            for camera_id in camera_list:
                videotxt_path = args.confirm_text

                #2025.05.27 torisato
                # ファイルを開いて1行目を取得
                # with open(videotxt_path, "r", encoding="utf-8") as f:
                #     # found = any(str(camera_id) + "/" + video_path in line for line in f)
                target = video_path.replace("\\", "/")  # バックスラッシュ→スラッシュに変換
                with open("confirm.txt", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    found = any(target in line.replace("\\", "/").strip() for line in lines)

                if found == False:
                    time.sleep(5)  # 5秒待機
                    break  # for を抜けて while の先頭からやり直し
            else:
                # for ループが break されずに最後まで実行された場合、while ループを抜ける
                break
    if startflg:
        # フォルダ内のファイル一覧を取得し、ソート
        files = sorted(os.listdir(args.video))
        #指定フォルダから最初と最後のファイル名を取得し、現在日付と組み合わせる
        #例)first_file:2025/05/28 13:48:50.000  last_file:2025/05/28 13:49:19.800
        first_file = convert_filename_to_time_format(files[0])
        last_file = convert_filename_to_time_format(files[-1])

        # strat_time="11:35:40.000"
        strat_time = "08:30:00.000"

        #上記のstrat_timeを基準に、現在日付 + strat_timeと　現在日付 + 23:59:59.999を返す
        #例)log_datetime_first = 2025/05/28 11:35:40.000    log_datetime_last = 2025/05/28 23:59:59.999
        log_datetime_first, log_datetime_last = time_format(strat_time)

        all_pairs=[]
        all_not_pairs=[]

        for camera_id1, camera_id2 in camera_pairs:
            x_range_start=CAMERA_AREA[f"{camera_id2}"][0]
            y_range_start=CAMERA_AREA[f"{camera_id2}"][1]
            x_range_end=CAMERA_AREA[f"{camera_id1}"][2]
            y_range_end=CAMERA_AREA[f"{camera_id1}"][3]
            # x_range_start=0
            # x_range_end=world_map[0]
            # y_range_start=0
            # y_range_end=world_map[1]

            results = get_data(first_file, last_file, x_range_start, x_range_end, y_range_start, y_range_end, camera_id1, camera_id2)
            pairs, not_pairs = id_handover(results)
            print(f"pairs:{pairs}, not_pairs:{not_pairs}")
            all_pairs.extend(pairs)
            all_not_pairs.extend(not_pairs)

        all_pairs = [all_pairs]
        all_not_pairs = [all_not_pairs]

        all_pairs = [[pair for pair in all_pairs[0] if pair[0] != pair[1]]]
        all_not_pairs = [[pair for pair in all_not_pairs[0] if pair[0] != pair[1]]]

        updated_list = pairs_consistency(all_pairs, all_not_pairs)

        pairs_processing(updated_list, log_datetime_first, log_datetime_last)
        update_images(log_datetime_first, first_file, args.merge_dir, updated_list, log_datetime_last, args.frame_count)

        for camera_id in camera_list:
            copy_merged_json(args.merge_dir, args.former_merge_dir, args.frame_count, camera_id)

        with open(args.id_text, "a") as file:
            file.write(video_path + "\n")