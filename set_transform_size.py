import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
import json
import sys
from module.utils3.DB_serch_camera_conf_utils import config

# 用紙サイズの寸法 (mm)
PAPER_SIZES = {
    "A4": (210, 297),
    "A3": (297, 420),
    "B4": (250, 353),
    "B3": (353, 500),
}

def on_size_or_count_changed(event=None):
    """用紙サイズまたは個数変更時の処理"""
    size = combo_size.get()
    if size in PAPER_SIZES:
        try:
            horizontal_count = int(entry_horizontal_count.get())
            vertical_count = int(entry_vertical_count.get())
        except ValueError:
            # 数値が無効の場合はゼロに設定
            horizontal_count = 0
            vertical_count = 0

        # 用紙サイズから全体サイズを計算
        width_per_sheet, height_per_sheet = PAPER_SIZES[size]
        total_width = width_per_sheet * horizontal_count
        total_height = height_per_sheet * vertical_count

        # 計算結果を表示
        total_size_label.config(
            text=f"全体の幅: {total_width} mm, 全体の高さ: {total_height} mm"
        )
    else:
        total_size_label.config(text="サイズが不明です")


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

def on_ok_button():
    """OKボタン押下時の処理"""
    # 各項目の値を取得
    WIDTH_FROM_ORIGIN = int(entry_distance_x.get())
    HEIGHT_FROM_ORIGIN = int(entry_distance_y.get())
    WIDTH = entry_scale_x.get()
    HEIGHT = entry_scale_y.get()
    size = combo_size.get()
    # 用紙サイズから全体サイズを計算
    horizontal_count = int(entry_horizontal_count.get())
    vertical_count = int(entry_vertical_count.get())
    width_per_sheet, height_per_sheet = PAPER_SIZES[size]
    total_width = width_per_sheet * horizontal_count
    total_height = height_per_sheet * vertical_count
    TRANSFORM_WIDTH = total_width
    TRANSFORM_HEIGHT = total_height

    TRANSFORM_SIZE  = [
    (WIDTH_FROM_ORIGIN, HEIGHT_FROM_ORIGIN),
    (WIDTH_FROM_ORIGIN + TRANSFORM_WIDTH, HEIGHT_FROM_ORIGIN),
    (WIDTH_FROM_ORIGIN + TRANSFORM_WIDTH, HEIGHT_FROM_ORIGIN + TRANSFORM_HEIGHT),
    (WIDTH_FROM_ORIGIN, HEIGHT_FROM_ORIGIN + TRANSFORM_HEIGHT)
    ]

    print("TRANSFORM_SIZE:",TRANSFORM_SIZE)

    try:
        # データをDBに書き込む
        update_camera_data(json.dumps(TRANSFORM_SIZE), json.dumps(WIDTH), json.dumps(HEIGHT))

        messagebox.showinfo("更新登録", f"{camera_ip}のデータを更新しました。")
    except Exception as e:
        messagebox.showerror("エラー", f"{camera_ip}のデータを更新に失敗しました: {e}")


def update_camera_data(TRANSFORM_SIZE, WIDTH, HEIGHT):
    """カメラ情報(transform_size, total_width, total_height)を更新登録"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        SQL = "UPDATE camera_data SET transform_size = %s, total_width = %s, total_height = %s WHERE camera_id = %s"
        params = (TRANSFORM_SIZE, WIDTH, HEIGHT, camera_ip)
        db.execute(SQL, params)
        connection.commit()
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

# Tkinterウィンドウ作成
root = tk.Tk()
root.title("入力フォーム")
root.geometry("400x600")

camera_ip = sys.argv[1]
# camera_ip = "192.168.1.142"

# ラベルとテキストボックスの作成
labels_and_entries = [
    ("原点からの距離(横)", None),
    ("原点からの距離(縦)", None),
    ("縮尺(横)", None),
    ("縮尺(縦)", None),
]

entries = []
for label_text, _ in labels_and_entries:
    # ラベル
    label = tk.Label(root, text=label_text)
    label.pack(pady=5)
    # テキストボックス
    entry = tk.Entry(root)
    entry.pack(pady=5)
    entries.append(entry)

# エントリを個別の変数に割り当て
entry_distance_x, entry_distance_y, entry_scale_y, entry_scale_x = entries

# サイズラベルとコンボボックス
size_label = tk.Label(root, text="サイズ")
size_label.pack(pady=10)
combo_size = ttk.Combobox(root, values=list(PAPER_SIZES.keys()), state="readonly")
combo_size.set("A4")  # 初期値
combo_size.pack(pady=5)
combo_size.bind("<<ComboboxSelected>>", on_size_or_count_changed)

# 横の個数と縦の個数
horizontal_count_label = tk.Label(root, text="横の個数")
horizontal_count_label.pack(pady=5)
entry_horizontal_count = tk.Entry(root)
entry_horizontal_count.insert(0, "1")  # 初期値
entry_horizontal_count.pack(pady=5)
entry_horizontal_count.bind("<KeyRelease>", on_size_or_count_changed)

vertical_count_label = tk.Label(root, text="縦の個数")
vertical_count_label.pack(pady=5)
entry_vertical_count = tk.Entry(root)
entry_vertical_count.insert(0, "1")  # 初期値
entry_vertical_count.pack(pady=5)
entry_vertical_count.bind("<KeyRelease>", on_size_or_count_changed)

# 全体サイズを表示するラベル
total_size_label = tk.Label(root, text="")
total_size_label.pack(pady=10)

# 初期状態でサイズを表示
on_size_or_count_changed()

# OKボタン
ok_button = tk.Button(root, text="OK", command=on_ok_button)
ok_button.pack(pady=20)

# メインループ開始
root.mainloop()
