import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import os
import shutil
import subprocess
import threading
from module.utils3.DB_serch_camera_conf_utils import fetch_camera_info

class CameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("カメラ選択")
        self.root.geometry("300x200")
        self.root.iconbitmap('cc1.ico')

        # ラベル
        tk.Label(root, text="カメラを選択:").pack(pady=5)

        # コンボボックスの作成
        self.camera_combobox = ttk.Combobox(root, state="readonly")
        self.camera_combobox.pack(pady=5)

        # カメラIP保持用
        self.camera_ips = []

        # データベースからカメラIPを取得してコンボボックスにセット
        self.records = fetch_camera_info()
        for record in self.records:
            # self.camera_ips.append(record[2])
            self.camera_ips.append(record['ip_address'])

        if self.records:
            self.camera_combobox["values"] = self.camera_ips
            self.camera_combobox.current(0)  # 初期値を設定

        # 選択ボタン
        self.select_button = tk.Button(root, text="選択", command=self.get_selected_camera)
        self.select_button.pack(pady=10)

    def get_selected_camera(self):
        """選択されたカメラIPを取得"""
        self.selected_ip = self.camera_combobox.get()
        self.index = self.camera_combobox.current()  # 選択されたインデックス番号
        # 画面遷移
        self.show()

    def show(self):
        self.root.destroy()
        print(f"選択されたカメラIP: {self.selected_ip}, インデックス: {self.records[self.index]}")
        self.main_window = tk.Tk()
        self.main_window.title("カメラ設定画面")
        self.main_window.geometry("400x300")
        self.main_window.iconbitmap('cc1.ico')

        tk.Label(self.main_window, text=f"カメラ設定画面", font=("Arial", 16)).pack(pady=20)

        # ボタンを追加（インスタンス変数に保存）
        self.btn_calibration = tk.Button(self.main_window, text="チェスボード撮影", command=self.ChessboardShooting)
        self.btn_calibration.pack(pady=5)

        self.btn_distortion_correction = tk.Button(self.main_window, text="歪み補正", command=self.camera_calibration)
        self.btn_distortion_correction.pack(pady=5)
        self.btn_distortion_correction.config(state=tk.DISABLED)

        self.btn_get_coordinates = tk.Button(self.main_window, text="ピストル値取得", command=self.get_coordinates)
        self.btn_get_coordinates.pack(pady=5)
        self.btn_get_coordinates.config(state=tk.NORMAL)

        self.btn_transform_size = tk.Button(self.main_window, text="実寸距離入力", command=self.set_transform_size)
        self.btn_transform_size.pack(pady=5)
        self.btn_transform_size.config(state=tk.NORMAL)

        self.btn_obstacle_setting = tk.Button(self.main_window, text="障害物設定", command=self.obstacle_setting)
        self.btn_obstacle_setting.pack(pady=5)
        self.btn_obstacle_setting.config(state=tk.NORMAL)

        tk.Button(self.main_window, text="カメラ選択画面", command=lambda: self.back_menu(self.main_window)).pack(pady=10)

        self.calibrtion_folder = "calbration_images"

        self.main_window.mainloop()

    """チェスボードの画像を撮像し、カメラのキャリブレーションを行う."""
    #TODO カメラキャリブレーション情報
    def ChessboardShooting(self):
        CHECKERBOARD = (7, 10)

        if os.path.exists(self.calibrtion_folder):
            shutil.rmtree(self.calibrtion_folder)  # フォルダを削除

        os.makedirs(self.calibrtion_folder, exist_ok=True)

        cap = cv2.VideoCapture(f"rtsp://{self.selected_ip}:554/rtpstream/config2=r")

        if not cap.isOpened():
            return

        img_counter = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            cv2.imshow('Camera', frame)

            if img_counter % 10 == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)

                # チェスボードが見つかった場合
                if ret:
                    # チェスボードが検出された場合に画像を保存
                    img_name = os.path.join(self.calibrtion_folder, f"image_{img_counter:03d}.jpg")
                    cv2.imwrite(img_name, frame)
                    print("img_name:",img_name)

            img_counter += 1

            # キー入力待ち（qを押すと終了）
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        #ボタン制御
        self.btn_calibration.config(state=tk.DISABLED)
        self.btn_distortion_correction.config(state=tk.NORMAL)

    def camera_calibration(self):
        """カメラの歪み補正を行う"""
        # 非同期でスクリプトを実行
        thread_calibration = threading.Thread(target=self.run_camera_calibration, args=())
        thread_calibration.start()

    def run_camera_calibration(self):
        """バックグラウンドで camera_calibration.py を実行"""
        try:
            self.btn_calibration.config(state=tk.DISABLED)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.DISABLED)
            subprocess.run(["python", "camera_calibration.py",self.selected_ip, self.calibrtion_folder], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("エラー", f"スクリプトの実行中にエラーが発生しました:\n{e}")
        finally:
            #ボタン制御
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.NORMAL)

    def get_coordinates(self):
        """ピクセル値の取得を行う"""
        # 非同期でスクリプトを実行
        thread_coordinates = threading.Thread(target=self.run_get_coordinates, args=())
        thread_coordinates.start()

    def run_get_coordinates(self):
        """バックグラウンドで get_coordinates.py を実行"""
        try:
            self.btn_calibration.config(state=tk.DISABLED)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.DISABLED)
            subprocess.run(["python", "get_coordinates.py",self.selected_ip, self.records[self.index][1]], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("エラー", f"スクリプトの実行中にエラーが発生しました:\n{e}")
        finally:
            #ボタン制御
            self.btn_calibration.config(state=tk.NORMAL)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.NORMAL)

    def set_transform_size(self):
        """実寸値の入力を行う"""
        # 非同期でスクリプトを実行
        thread_transform_size = threading.Thread(target=self.run_set_transform_size, args=())
        thread_transform_size.start()

    def run_set_transform_size(self):
        """バックグラウンドで set_transform_size.py を実行"""
        try:
            self.btn_calibration.config(state=tk.DISABLED)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.DISABLED)
            subprocess.run(["python", "set_transform_size.py",self.selected_ip], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("エラー", f"スクリプトの実行中にエラーが発生しました:\n{e}")
        finally:
            #ボタン制御
            self.btn_calibration.config(state=tk.NORMAL)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.NORMAL)

    def obstacle_setting(self):
        """障害物設定を行う"""
        # 非同期でスクリプトを実行
        thread_obstacle = threading.Thread(target=self.run_obstacle_setting, args=())
        thread_obstacle.start()

    def run_obstacle_setting(self):
        """バックグラウンドで create_person_map.py を実行"""
        try:
            self.btn_calibration.config(state=tk.DISABLED)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.DISABLED)
            subprocess.run(["python", "create_person_map.py",self.selected_ip, self.records[self.index][1]], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("エラー", f"スクリプトの実行中にエラーが発生しました:\n{e}")
        finally:
            #ボタン制御
            self.btn_calibration.config(state=tk.NORMAL)
            self.btn_distortion_correction.config(state=tk.DISABLED)
            self.btn_get_coordinates.config(state=tk.NORMAL)

    def back_menu(self, main_window):
        """カメラ選択画面に戻る"""
        main_window.destroy()
        root = tk.Tk()
        CameraApp(root)
        root.mainloop()

# Tkinterの実行
root = tk.Tk()
app = CameraApp(root)
root.mainloop()
