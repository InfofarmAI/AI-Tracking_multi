import os
import mysql.connector
from utils3.DB_serch_camera_conf_utils import config
import csv
import tkinter as tk
from tkcalendar import Calendar
from datetime import date


def get_colums_name():
    """
    指定された日付に基づいてカラム情報を取得する
    :return: カラム名リスト
    """
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = f"""
        # SELECT COLUMN_COMMENT
        # FROM INFORMATION_SCHEMA.COLUMNS
        # WHERE TABLE_SCHEMA = 'cclog_db' AND TABLE_NAME = 'test_logs';
        # """
        query = f"""
        SELECT COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'cclog_db' AND TABLE_NAME = 'logs';
        """

        db.execute(query)
        results = db.fetchall()

        return results

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def get_data(first_date,last_date):
    connection = mysql.connector.connect(**config)
    db = connection.cursor()

    try:
        # query = "SELECT chameleon_code, log_datetime, center_x, center_y, TID, camera_id ,update_camera_id from cclog_db.test_logs where log_datetime BETWEEN %s AND %s order by log_datetime,camera_id;"
        query = "SELECT chameleon_code, log_datetime, center_x, center_y, TID, camera_id ,update_camera_id, transform_center_x, transform_center_y from cclog_db.logs where log_datetime BETWEEN %s AND %s order by log_datetime,camera_id;"
        params=(first_date,last_date)

        db.execute(query,params)
        # 結果を取得
        results = db.fetchall()

        return results

    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()


def on_ok():
    """
    カレンダーで選択された日付を取得して処理を実行する
    """
    # カレンダーで選択された日付を取得
    selected_date = calendar.get_date()

    # # 選択された日付を引数にしてカラム情報を取得
    # results = get_colums_name()

    # # カラム名をリスト形式に変換
    # columns = [col[0] for col in results]

    # ヘッダーが必要な場合、以下にカラム名をリストとして記述する
    columns = [
        # "カメレオンコード", "読取日時", "中心X座標", "中心Y座標", "TID", "カメラID", "カメラID（更新）". "中心X座標(俯瞰)", "中心Y座標(俯瞰)"
        "chameleon_code", "log_datetime", "center_x", "center_y", "TID","camera_id","update_camera_id", "transform_center_x", "transform_center_y"
    ]


    # CSVファイルに保存
    csv_file_path = "data.csv"
    if os.path.exists(csv_file_path):
        os.remove(csv_file_path)

    #2024-11-12 12:12:12.123
    first_date = f"{selected_date} 00:00:00.000"
    last_date = f"{selected_date} 23:59:59.999"
    selected_date
    results = get_data(first_date,last_date)

    # CSVに書き込み
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow(columns)  # ヘッダー行を書き込む

        # データ行を書き込む
        for row in results:
            writer.writerow(row)

    print(f"カラム名をCSVに保存しました: {csv_file_path}")
    root.destroy()  # ウィンドウを閉じる


if __name__ == "__main__":
    # Tkinterのウィンドウ作成
    root = tk.Tk()
    root.title("カレンダーアプリ")

    # カレンダーウィジェットを作成
    today = date.today()
    calendar = Calendar(root, selectmode="day", year=today.year, month=today.month, day=today.day)
    calendar.pack(pady=20)

    # OKボタンを作成
    ok_button = tk.Button(root, text="OK", command=on_ok)
    ok_button.pack(pady=10)

    # Tkinterのメインループを開始
    root.mainloop()
