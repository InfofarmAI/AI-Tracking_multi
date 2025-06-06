import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import os
import glob
import sys
import mysql.connector
import time
import threading
from module.utils3.DB_serch_camera_conf_utils import config

def start_loading():
    """処理を開始"""
    loading_label.config(text="処理中...")
    progress_bar.start(10)  # プログレスバーを動かす
    threading.Thread(target=long_task, daemon=True).start()  # 時間のかかるタスクを別スレッドで実行

def long_task():
    """時間のかかるタスクを実行"""
    global camera_root

    # カメラキャリブレーション処理
    CHECKERBOARD = (7, 10)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objpoints, imgpoints = [], []

    objp = np.zeros((1, CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[0, :, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)

    images = glob.glob(f'{img_folder}/*.jpg')

    for frame in images:
        img = cv2.imread(frame)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, cv2.CALIB_CB_ADAPTIVE_THRESH +
                                                cv2.CALIB_CB_FAST_CHECK + cv2.CALIB_CB_NORMALIZE_IMAGE)

        if ret:
            objpoints.append(objp)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)

    cv2.destroyAllWindows()

    h, w = img.shape[:2]
    start_time = time.time()

    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"処理時間: {elapsed_time:.2f}秒")

    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))

    np.savez('Points.npz', objpoints=objpoints, imgpoints=imgpoints)
    np.savez('B.npz', mtx=mtx, dist=dist, rvecs=rvecs, tvecs=tvecs)

    # Load previously saved data
    with np.load('B.npz') as X:
        mtx, dist, rvecs, tvecs = [X[i] for i in ('mtx','dist','rvecs','tvecs')]

    with np.load('Points.npz') as X:
        objpoints, imgpoints = [X[i] for i in ('objpoints','imgpoints')]

    ###################

    mean_error = 0
    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        error = cv2.norm(imgpoints[i],imgpoints2, cv2.NORM_L2)/len(imgpoints2)
        mean_error += error

    total_error = mean_error/len(objpoints)

    progress_bar.stop()
    loading_label.config(text="完了しました！")

    #登録確認
    show_result_message(mtx, dist, new_mtx, total_error)

    time.sleep(1)
    camera_root.destroy()

def show_result_message(mtx, dist, new_mtx, total_error):
    """メインスレッドでメッセージボックスを表示"""

    message = (
        f"精度:\n{total_error}\n\n"
        f"Camera matrix:\n{mtx.tolist()}\n\n"
        f"dist:\n{dist.tolist()}\n\n"
        f"New camera matrix:\n{new_mtx.tolist()}\n\n"
        "登録しますか？"
    )

    #TODO total_errorの値に応じて再撮影を促すようにする
    # if total_error > 0.7:
    #     message = (
    #         f"精度が低いです:\n{total_error}\n\n"
    #         "登録しますか？"
    #     )
    # else:
    #     message = (
    #         f"精度が高いです:\n{total_error}\n\n"
    #         "登録しますか？"
    #     )

    result = messagebox.askyesno("Camera Calibration", message)

    if result:
        records = select_camera_data()
        if len(records) == 0:
            insert_camera_data(mtx, dist, new_mtx)  # 新規登録
        else:
            update_camera_data(mtx, dist, new_mtx)  # 更新登録

def select_camera_data():
    """カメラ情報を取得"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT * FROM cclog_db.camera_data WHERE camera_id = %s;"
        db.execute(query, [camera_ip])
        return db.fetchall()
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def insert_camera_data(mtx, dist, new_mtx):
    """カメラ情報を新規登録"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        SQL = "INSERT INTO camera_data (camera_id, camera_matrix, dist, new_camera_matrix) VALUES (%s, %s, %s, %s)"
        params = (camera_ip, str(mtx.tolist()), str(dist.tolist()), str(new_mtx.tolist()))
        db.execute(SQL, params)
        connection.commit()
        messagebox.showinfo("新規登録", "登録が完了しました！")
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def update_camera_data(mtx, dist, new_mtx):
    """カメラ情報を更新登録"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        SQL = "UPDATE camera_data SET camera_matrix = %s, dist = %s, new_camera_matrix = %s WHERE camera_id = %s"
        params = (str(mtx.tolist()), str(dist.tolist()), str(new_mtx.tolist()), camera_ip)
        db.execute(SQL, params)
        connection.commit()
        messagebox.showinfo("更新登録", "登録が完了しました！")
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("エラー: camera_ip と img_folder の引数が必要です。")
        sys.exit(1)

    camera_ip = sys.argv[1]
    img_folder = sys.argv[2]

    camera_root = tk.Tk()
    camera_root.title("処理中")
    camera_root.geometry("300x150")
    camera_root.iconbitmap('cc1.ico')
    progress_bar = ttk.Progressbar(camera_root, orient="horizontal", mode="indeterminate", length=200)
    progress_bar.pack(pady=20)
    loading_label = tk.Label(camera_root, text="待機中...")
    loading_label.pack()

    start_loading()
    camera_root.mainloop()
