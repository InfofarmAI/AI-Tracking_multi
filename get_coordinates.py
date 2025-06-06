"""
get_ccordinates.py

このスクリプトは、指定されたIPカメラ（RTSPストリーム）から映像を取得し、Tkinter GUIを用いて
任意の4点座標を取得・保存するツールです。主にカメラ視野内の関心領域（area_size）の設定を
データベースに登録する目的で使用されます。

主な機能:
- RTSP 映像ストリーミングと停止
- 歪み補正済み画像の表示
- ズーム機能で画像の一部を拡大して正確な点を指定可能
- クリックによる点の選択と削除
- 選択した4点座標のデータベース登録（MySQL）
"""

import cv2
from module.utils3.DB_serch_camera_conf_utils import config, select_camera_data
import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import json
import mysql.connector
import ast
import sys


class CameraApp:
    def __init__(self, window, window_title, video_source=0):
        self.window          = window
        self.video_source    = video_source
        self.input_size      = (1920, 1080)
        self.reduction_ratio = (self.input_size[0] / 1080, self.input_size[1] / 720)
        self.coordinates     = []
        self.captured_frame  = None
        self.orig_frame      = None
        self.streaming       = True
        #ズーム機能の追加
        self.zoom_mode = False
        self.zoom_start = None
        self.zoom_rect = None
        self.corrected_frame = None
        self.vid = cv2.VideoCapture(video_source)
        self.window.title(window_title)

        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)

        self.window.geometry("1080x800")
        self.canvas = tk.Canvas(window, width=1080, height=720)
        self.canvas.grid(row=0, columnspan=6)

        self.btn_play = tk.Button(window, text="再生", width=15, height=2, command=self.play_stream)
        self.btn_play.config(state="disabled")
        self.btn_play.grid(row=1, column=0, padx=15, pady=15)

        self.btn_capture = tk.Button(window, text="停止", width=15, height=2, command=self.capture_frame)
        self.btn_capture.grid(row=1, column=1, padx=15, pady=15)

        self.btn_undistort = tk.Button(window, text="歪み補正", width=15, height=2, command=self.undistort_frame)
        self.btn_undistort.config(state="disabled")
        self.btn_undistort.grid(row=1, column=2, padx=15, pady=15)

        self.btn_zoom = tk.Button(window, text="ズーム", width=15, height=2, command=self.enable_zoom_mode)
        self.btn_zoom.config(state="disabled")
        self.btn_zoom.grid(row=1, column=3, padx=15, pady=15)

        self.btn_remove_last = tk.Button(self.window, text="最後の点を削除", width=15, height=2, command=self.remove_last_coordinate)
        self.btn_remove_last.config(state="disabled")
        self.btn_remove_last.grid(row=1, column=4, padx=15, pady=10)

        self.btn_output = tk.Button(window, text="座標出力", width=15, height=2, command=self.output_coordinates)
        self.btn_output.config(state="disabled")
        self.btn_output.grid(row=1, column=5, padx=15, pady=15)
        self.update()
        self.window.mainloop()


    """ズーム機能"""
    def enable_zoom_mode(self):
        self.zoom_mode = True
        self.canvas.bind("<ButtonPress-1>", self.on_zoom_start)
        self.canvas.bind("<B1-Motion>", self.on_zoom_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_zoom_end)
        messagebox.showinfo("ズーム範囲選択", "ズームしたい領域をドラッグしてください。")

    def on_zoom_start(self, event):
        self.zoom_start = (event.x, event.y)
        self.zoom_rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="blue")

    def on_zoom_drag(self, event):
        if self.zoom_rect:
            self.canvas.coords(self.zoom_rect, self.zoom_start[0], self.zoom_start[1], event.x, event.y)

    def on_zoom_end(self, event):
        if not self.zoom_start:
            return

        x0, y0 = self.zoom_start
        x1, y1 = event.x, event.y
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.zoom_mode = False

        self.canvas.delete(self.zoom_rect)
        self.zoom_rect = None

        # 正規化（左上 → 右下）
        x1, x2 = sorted([x0, x1])
        y1, y2 = sorted([y0, y1])

        # キャンバス（1080x720） → 元画像（1920x1080）に変換
        scale_x = self.input_size[0] / 1080
        scale_y = self.input_size[1] / 720
        gx1 = int(x1 * scale_x)
        gy1 = int(y1 * scale_y)
        gx2 = int(x2 * scale_x)
        gy2 = int(y2 * scale_y)

        self.show_zoomed_area(gx1, gy1, gx2, gy2)

    def show_zoomed_area(self, x1, y1, x2, y2):
        # 歪み補正後の元画像からズーム
        if not hasattr(self, 'corrected_frame'):
            messagebox.showerror("エラー", "まず『歪み補正』を実行してください。")
            return

        cropped = self.corrected_frame[y1:y2, x1:x2]  # ← 歪み補正済み画像を使用
        if cropped.size == 0:
            messagebox.showerror("エラー", "ズーム範囲が不正です。")
            return

        zoomed = cv2.resize(cropped, (400, 400), interpolation=cv2.INTER_LINEAR)
        zoomed_image = Image.fromarray(cv2.cvtColor(zoomed, cv2.COLOR_BGR2RGB))
        self.zoomed_photo = ImageTk.PhotoImage(image=zoomed_image)

        if hasattr(self, "zoom_window") and self.zoom_window and self.zoom_window.winfo_exists():
            self.zoom_window.destroy()

        self.zoom_window = tk.Toplevel(self.window)
        self.zoom_window.title("ズーム表示")

        label = tk.Label(self.zoom_window, image=self.zoomed_photo)
        label.pack()

        self.zoom_coords = (x1, y1, x2, y2)
        label.bind("<Button-1>", self.on_zoom_click)

    def on_zoom_click(self, event):
        if not hasattr(self, 'zoom_coords'):
            return

        x1, y1, x2, y2 = self.zoom_coords
        zoom_width, zoom_height = 400, 400

        # ズーム画面内でのクリック座標を取得して元画像に変換
        zoom_x_ratio = (x2 - x1) / zoom_width
        zoom_y_ratio = (y2 - y1) / zoom_height

        gx = int(x1 + event.x * zoom_x_ratio)
        gy = int(y1 + event.y * zoom_y_ratio)

        # リサイズ後キャンバス座標に変換
        canvas_x = int(gx * (1080 / self.input_size[0]))
        canvas_y = int(gy * (720 / self.input_size[1]))

        # 点を追加
        if len(self.coordinates) < 4:
            self.coordinates.append((canvas_x, canvas_y))
            self.canvas.create_oval(canvas_x - 2, canvas_y - 2, canvas_x + 2, canvas_y + 2, fill='red')

        if len(self.coordinates) == 4:
            self.canvas.unbind("<Button-1>")
            self.btn_zoom.config(state="normal")

    def __del__(self):
        if self.vid.isOpened():
            self.vid.release()

    def capture_frame(self):
        self.streaming = False
        # Captureボタンを無効にする
        self.btn_capture.config(state="disabled")
        self.btn_play.config(state="normal")
        self.btn_undistort.config(state="normal")
    
    # HACK ウィンドウをドラッグしないと再生されない不具合修正
    def play_stream(self):
        self.coordinates    = []
        self.streaming      = True
        self.captured_frame = None
        
        # Captureボタンを再度有効にする
        self.btn_capture.config(state="normal")
        self.btn_play.config(state="disabled")
        self.btn_undistort.config(state="disabled")
        self.btn_remove_last.config(state="disabled")
        self.btn_output.config(state="disabled")
        self.btn_zoom.config(state="disabled")
        
        self.update()  # ストリーム再生

    def update(self):
        if self.streaming:
            ret, frame = self.vid.read()
            if ret:
                self.orig_frame = frame
                # Resize frame to fit the canvas size
                self.captured_frame = cv2.resize(frame, (1080, 720), interpolation=cv2.INTER_AREA)
                self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB)))
                self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
            self.window.update_idletasks()
        self.window.after(10, self.update)

    def undistort_frame(self):
        # camera_configから必要なデータを取得
        # camera_matrix = np.array(self.camera_config['mtx'])
        # distortion_coefficients = np.array(self.camera_config['dist'])
        # new_camera_matrix = np.array(self.camera_config['new_mtx'])

        camera_matrix = np.array(mtx, dtype=np.float32)
        distortion_coefficients = np.array(dist, dtype=np.float32)
        new_camera_matrix = np.array(new_mtx, dtype=np.float32)

        # 歪み補正を行う
        corrected_frame = cv2.undistort(self.orig_frame, camera_matrix, distortion_coefficients, None, new_camera_matrix)
        self.corrected_frame = corrected_frame  # ←★追加
        self.captured_frame = cv2.resize(corrected_frame, (1080, 720), interpolation=cv2.INTER_AREA)

        # 補正された画像をPIL形式に変換してキャンバスに表示
        corrected_image = Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB))
        self.photo = ImageTk.PhotoImage(image=corrected_image)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        self.canvas.bind("<Button-1>", self.select_point)

        self.btn_output.config(state="normal")
        self.btn_remove_last.config(state="normal")
        self.btn_zoom.config(state="normal")  # ✅ ズームボタンを有効化

    def select_point(self, event):
        if len(self.coordinates) < 4:
            self.coordinates.append((event.x, event.y))
            self.canvas.create_oval(event.x - 2, event.y - 2, event.x + 2, event.y + 2, fill='red')
        if len(self.coordinates) == 4:
            self.canvas.unbind("<Button-1>")
    
    def remove_last_coordinate(self):
        if self.coordinates:
            self.coordinates.pop()  # 最後の座標を削除
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
            self.canvas.bind("<Button-1>", self.select_point)
            
            # キャンバスクリア後、更新されたself.coordinatesに基づいて赤点を再描画
            for coordinate in self.coordinates:
                x, y = coordinate
                self.canvas.create_oval(x-2, y-2, x+2, y+2, fill='red')

    def output_coordinates(self):
        if len(self.coordinates) != 4:
            messagebox.showerror("Error", "4点を選択してください。")
            return

        coordinates = []
        for x, y in self.coordinates:
            converted_x = int(x * self.reduction_ratio[0])
            converted_y = int(y * self.reduction_ratio[1])
            coordinates.append((converted_x, converted_y))

        # print("Selected coordinates: ", ", ".join(f"({x}, {y})" for x, y in coordinates))

        area_size = "[" + ", ".join(f"({x}, {y})" for x, y in coordinates) + "]"
        print("area_size:",area_size)

        #データベース登録
        message = (
        f"area_size:\n{area_size}\n\n"
        "登録しますか？"
        )

        result = messagebox.askyesno("Update area_size", message)
        if result:
            self.update_area_size(json.dumps(area_size))

    def update_area_size(self, area_size):
        """カメラ情報を更新登録"""
        connection = mysql.connector.connect(**config)
        db = connection.cursor()
        try:
            SQL = "UPDATE camera_data SET area_size = %s WHERE camera_id = %s"
            params = (area_size, camera_ip)
            db.execute(SQL, params)
            connection.commit()
            messagebox.showinfo("更新登録", "登録が完了しました！")
        except mysql.connector.Error as e:
            print(e)
        finally:
            db.close()
            connection.close()

if __name__ == '__main__':
    # camera_ip, camera_code  = '192.168.1.147', 'YTS9260905'
    # root = CameraApp(tk.Tk(), "座標取得", CAMERA_CONFIG[camera_code], video_source=f"rtsp://{camera_ip}:554/rtpstream/config2=r")
    camera_ip, camera_code  = sys.argv[1], sys.argv[2]

    """カメラのキャリブレーションを取得"""
    records = select_camera_data(camera_ip)
    if all(not item[0] for item in records):
        messagebox.showerror("エラー","カメラのキャリブレーションを行ってください!")
    else:
        for record in records:
            mtx = ast.literal_eval(record[0])
            dist = ast.literal_eval(record[1])
            new_mtx = ast.literal_eval(record[2])
        root = CameraApp(tk.Tk(), "座標取得", video_source=f"rtsp://{camera_ip}:554/rtpstream/config2=r")