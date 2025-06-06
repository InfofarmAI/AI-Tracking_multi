import cv2
import threading
from utils3.Camera_conf_utils import CAMERA_CONFIG
import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

class CameraApp:
    def __init__(self, window, window_title, camera_config, video_source=0):
        self.window          = window
        self.camera_config   = camera_config
        self.video_source    = video_source
        self.input_size      = (1920, 1080)
        self.reduction_ratio = (self.input_size[0] / 1080, self.input_size[1] / 720)
        self.coordinates     = []
        self.captured_frame  = None
        self.orig_frame      = None
        self.streaming       = True
        self.vid = cv2.VideoCapture(video_source)
        self.window.title(window_title)

        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)

        self.window.geometry("1080x800")
        self.canvas = tk.Canvas(window, width=1080, height=720)
        self.canvas.grid(row=0, columnspan=5)

        self.btn_play = tk.Button(window, text="再生", width=15, height=2, command=self.play_stream)
        self.btn_play.config(state="disabled")
        self.btn_play.grid(row=1, column=0, padx=15, pady=15)

        self.btn_capture = tk.Button(window, text="停止", width=15, height=2, command=self.capture_frame)
        self.btn_capture.grid(row=1, column=1, padx=15, pady=15)

        self.btn_undistort = tk.Button(window, text="歪み補正", width=15, height=2, command=self.undistort_frame)
        self.btn_undistort.config(state="disabled")
        self.btn_undistort.grid(row=1, column=2, padx=15, pady=15)

        self.btn_remove_last = tk.Button(self.window, text="最後の点を削除", width=15, height=2, command=self.remove_last_coordinate)
        self.btn_remove_last.config(state="disabled")
        self.btn_remove_last.grid(row=1, column=3, padx=15, pady=10)

        self.btn_output = tk.Button(window, text="座標出力", width=15, height=2, command=self.output_coordinates)
        self.btn_output.config(state="disabled")
        self.btn_output.grid(row=1, column=4, padx=15, pady=15)

        self.update()
        self.window.mainloop()

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
        camera_matrix = np.array(self.camera_config['mtx'])
        distortion_coefficients = np.array(self.camera_config['dist'])
        new_camera_matrix = np.array(self.camera_config['new_mtx'])

        # 歪み補正を行う
        corrected_frame = cv2.undistort(self.orig_frame, camera_matrix, distortion_coefficients, None, new_camera_matrix)
        self.captured_frame = cv2.resize(corrected_frame, (1080, 720), interpolation=cv2.INTER_AREA)

        # 補正された画像をPIL形式に変換してキャンバスに表示
        corrected_image = Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB))
        self.photo = ImageTk.PhotoImage(image=corrected_image)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        self.canvas.bind("<Button-1>", self.select_point)

        self.btn_output.config(state="normal")
        self.btn_remove_last.config(state="normal")

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

        print("Selected coordinates: ", ", ".join(f"({x}, {y})" for x, y in coordinates))

if __name__ == '__main__':
    camera_ip, camera_code  = '192.168.1.146', 'ZGY8586252'
    root = CameraApp(tk.Tk(), "座標取得", CAMERA_CONFIG[camera_code], video_source=f"rtsp://{camera_ip}:554/rtpstream/config1=r")