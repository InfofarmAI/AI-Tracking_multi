import os
import csv
import pytz
import aiomysql
import datetime

#CSV書き込み関数
def write_csv(filepath, csv_list):
    with open(filepath +'/log.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        for row in csv_list:
            writer.writerow(row)

def get_current_time():
    # タイムゾーンを日本に設定
    japan_timezone = pytz.timezone('Asia/Tokyo')
    #現在時刻取得
    current_time = datetime.datetime.now(japan_timezone)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")
    return formatted_time

def get_timestamp_conversion(time_stamp_number):
    # タイムゾーンを日本に設定
    japan_timezone = pytz.timezone('Asia/Tokyo')
    #現在時刻取得
    current_time = datetime.datetime.now(japan_timezone)
    formatted_time = current_time.strftime("%Y-%m-%d")
    number_str=str(time_stamp_number)

    # 各部分に分割
    hours = number_str[:2]
    minutes = number_str[2:4]
    seconds = number_str[4:6]
    milliseconds = number_str[6:]

    formatted_time=formatted_time + " " + hours + ":" + minutes + ":" + seconds + "." + milliseconds

    return formatted_time

async def createpool(config, loop):
    config['loop'] = loop
    pool = await aiomysql.create_pool(**config)
    return pool

# 一秒以上経過 → INSERT(一秒未満 → 処理なし)
# async def insert(pool, list_result, cc_detection_flg_list):
#     #INSERTする間隔の設定(1秒間隔)
#     async with pool.acquire() as conn:
#         async with conn.cursor() as cursor:
#             for row, cc_detection_flg in zip(list_result, cc_detection_flg_list):
#                 #SQL文
#                 SQL  = "INSERT INTO "
#                 SQL += "    test_logs "
#                 #カメレオンコードが検知されているかどうか
#                 if cc_detection_flg == False:
#                     if row[12]==0:
#                         SQL += "    (company_id,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,TID,camera_id) "
#                         SQL += "VALUES "
#                         SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
#                         params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11])
#                     else:
#                         SQL += "    (company_id,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,TID,camera_id,update_camera_id) "
#                         SQL += "VALUES "
#                         SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)"
#                         params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11],row[12])
#                 else:
#                     SQL += "    (company_id,chameleon_code,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,camera_id) "
#                     SQL += "VALUES "
#                     SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
#                     params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11])
#                 # クエリを実行
#                 # if cc_detection_flg == True:
#                 await conn.begin()
#                 await cursor.execute(SQL, params)
#                 # コミット処理
#                 await conn.commit()

async def insert(pool, list_result, cc_detection_flg_list):
    #INSERTする間隔の設定(1秒間隔)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            for row, cc_detection_flg in zip(list_result, cc_detection_flg_list):
                #SQL文
                SQL  = "INSERT INTO "
                SQL += "    logs "
                #カメレオンコードが検知されているかどうか
                if cc_detection_flg == False:
                    # SQL += "    (company_id,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,TID,camera_id) "
                    SQL += "    (company_id,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,TID,camera_id,transform_center_x,transform_center_y) "
                    SQL += "VALUES "
                    # SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    # params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11])
                    params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12], row[13])
                else:
                    # SQL += "    (company_id,chameleon_code,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,camera_id) "
                    SQL += "    (company_id,chameleon_code,top_left_x,top_left_y,bottom_right_x,bottom_right_y,center_x,center_y,log_datetime,created,modified,camera_id,transform_center_x,transform_center_y) "
                    SQL += "VALUES "
                    SQL += "    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    # params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11])
                    params = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12], row[13])
                # クエリを実行
                # if cc_detection_flg == True:
                await conn.begin()
                await cursor.execute(SQL, params)
                # コミット処理
                await conn.commit()


# #高速化したバルク対応 2025.05.07 torisato
# async def insert(pool, list_result, cc_detection_flg_list):
#     async with pool.acquire() as conn:
#         async with conn.cursor() as cursor:
#             await conn.begin()

#             # 3種類に振り分ける
#             group_normal = []
#             group_update = []
#             group_chameleon = []

#             for row, cc_detection_flg in zip(list_result, cc_detection_flg_list):
#                 if not cc_detection_flg:
#                     if row[12] == 0:
#                         group_normal.append(row[:12])  # 0〜11
#                     else:
#                         group_update.append(row[:13])  # 0〜12
#                 else:
#                     group_chameleon.append(row[:12])  # 0〜11（chameleon_code入り）

#             # 通常ログ INSERT
#             if group_normal:
#                 sql = """
#                     INSERT INTO test_logs (
#                         company_id, top_left_x, top_left_y, bottom_right_x, bottom_right_y,
#                         center_x, center_y, log_datetime, created, modified, TID, camera_id
#                     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                 """
#                 await cursor.executemany(sql, group_normal)

#             # update_camera_id 付き INSERT
#             if group_update:
#                 sql = """
#                     INSERT INTO test_logs (
#                         company_id, top_left_x, top_left_y, bottom_right_x, bottom_right_y,
#                         center_x, center_y, log_datetime, created, modified, TID, camera_id, update_camera_id
#                     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                 """
#                 await cursor.executemany(sql, group_update)

#             # chameleon_code あり INSERT
#             if group_chameleon:
#                 sql = """
#                     INSERT INTO test_logs (
#                         company_id, chameleon_code, top_left_x, top_left_y, bottom_right_x, bottom_right_y,
#                         center_x, center_y, log_datetime, created, modified, camera_id
#                     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                 """
#                 await cursor.executemany(sql, group_chameleon)

#             await conn.commit()

