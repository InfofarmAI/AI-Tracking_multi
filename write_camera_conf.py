from tkinter import messagebox
import mysql.connector
import ast
from module.utils3.DB_serch_camera_conf_utils import config

def fetch_camera_info():
    connection = mysql.connector.connect(**config)
    db = connection.cursor(dictionary=True)
    try:
        query = "SELECT id, code, ip_address FROM cameras WHERE status = %s;"
        db.execute(query, ['1']) # 有効な区分のカメラのみ取得
        records = db.fetchall()

        return records
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

#カメラ情報の取得
def select_camera_data(camera_ip):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT * FROM cclog_db.camera_data WHERE camera_id = %s;"
        db.execute(query, [camera_ip]) # 有効な区分のカメラのみ取得
        records = db.fetchall()

        return records
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def write_camera_settings_to_file():
    # 有効なカメラ情報を取得
    records = fetch_camera_info()

    # データを格納する辞書
    camera_settings = {}

    for record in records:
        # code = record[1]
        # camera_id = record[2]
        code = record['code']
        camera_id = record['ip_address']

        # カメラデータを取得
        camera_datas = select_camera_data(camera_id)
        # print("rec",camera_datas)

        for camera_data in camera_datas:
            # print("camera_data:",camera_data)
            # 各カメラの情報を取得
            id = camera_data[0]
            mtx = camera_data[2]
            dist = camera_data[3]
            new_mtx = camera_data[4]
            area_size = ast.literal_eval(str(camera_data[5]))
            transform_size = ast.literal_eval(str(camera_data[6]))
            total_width = ast.literal_eval(str(camera_data[7]))
            total_height = ast.literal_eval(str(camera_data[8]))

            print("id:",id)
            print("mtx:",mtx)
            print("dist:",dist)
            print("new_mtx:",new_mtx)
            print("area_size:",area_size)
            print("transform_size:",transform_size)

            # 指定されたフォーマットにデータを整形
            camera_settings[code] = {
                # 'transform_size': f"TRANSFORM_SIZE",
                'id': id,
                'transform_size': transform_size,
                'area_size': area_size,
                'mtx': mtx,
                'dist': dist,
                'new_mtx': new_mtx,
                'total_width': total_width,
                'total_height': total_height,
            }

    # データをPythonファイルに書き込む
    with open("module/utils3/camera_settings.py", "w") as file:  #新規記入
    # with open("module/utils3/Camera_conf_utils.py", "w") as file:  #TODO 置き換え予定
        file.write("CAMERA_CONFIG = {\n")
        for code, data in camera_settings.items():
            file.write(f"    '{code}': {'{'}\n")
            file.write(f"        'transform_size': {data['transform_size']},\n")
            file.write(f"        'area_size': {data['area_size']},\n")
            file.write(f"        'mtx': {data['mtx']},\n")
            file.write(f"        'dist': {data['dist']},\n")
            file.write(f"        'new_mtx': {data['new_mtx']}\n")
            file.write(f"    {'}'},\n")
        file.write("}\n")

        #エリアの縮尺書き込み
        for code, data in camera_settings.items():
            file.write(f"WIDTH{data['id']}= {data['total_width']}\n")
            file.write(f"HEIGHT{data['id']}= {data['total_height']}\n")
            file.write("\n")


def main():
    try:
        #カメラキャリブレーション情報の読込＆書込
        write_camera_settings_to_file()
        messagebox.showinfo("保存完了", "設定が正常に保存されました！")
    except Exception as e:
        messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

main()
