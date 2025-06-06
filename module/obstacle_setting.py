import cv2
from utils3.Camera_conf_utils import CAMERA_CONFIG
import tkinter as tk
from PIL import Image, ImageTk

class CameraApp:
    def __init__(self, window, window_title, camera_config, video_source=0):
        self.window = window
        self.camera_config = camera_config
        self.video_source = video_source
        self.input_size = (1920, 1080)
        self.reduction_ratio = (self.input_size[0] / 1080, self.input_size[1] / 720)
        self.coordinates = []  # 現在選択中の障害物座標
        self.obstacles = []    # 全障害物の座標リスト
        self.captured_frame = None
        self.orig_frame = None
        self.streaming = True
        self.vid = cv2.VideoCapture(video_source)
        self.window.title(window_title)

        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)

        self.window.geometry("1080x800")
        self.canvas = tk.Canvas(window, width=1080, height=720)
        self.canvas.grid(row=0, columnspan=6)

        # ボタンの作成
        self.btn_play = tk.Button(window, text="再生", width=15, height=2, command=self.play_stream)
        self.btn_play.config(state="disabled")
        self.btn_play.grid(row=1, column=0, padx=15, pady=15)

        self.btn_capture = tk.Button(window, text="停止", width=15, height=2, command=self.capture_frame)
        self.btn_capture.grid(row=1, column=1, padx=15, pady=15)

        self.btn_remove_last = tk.Button(self.window, text="最後の点を削除", width=15, height=2, command=self.remove_last_coordinate)
        self.btn_remove_last.grid(row=1, column=3, padx=15, pady=10)

        self.btn_output = tk.Button(window, text="座標出力", width=15, height=2, command=self.output_coordinates)
        self.btn_output.grid(row=1, column=4, padx=15, pady=15)

        self.btn_obstacle = tk.Button(window, text="障害物設定", width=15, height=2, command=self.set_obstacle)
        self.btn_obstacle.grid(row=1, column=5, padx=15, pady=15)

        # 初期設定
        self.canvas.bind("<Button-1>", self.select_point)
        self.btn_remove_last.config(state="normal")
        self.btn_output.config(state="normal")
        self.btn_obstacle.config(state="normal")

        self.update()
        self.window.mainloop()

    def select_point(self, event):
        if len(self.coordinates) < 4:
            self.coordinates.append((event.x, event.y))
            self.canvas.create_oval(event.x - 2, event.y - 2, event.x + 2, event.y + 2, fill='red')

    def set_obstacle(self):
        if len(self.coordinates) != 4:
            print("Error: 4点を選択してください。")
            return

        # 障害物の座標を保存
        self.obstacles.append(self.coordinates.copy())

        # 障害物を描画
        self.canvas.create_line(self.coordinates[0], self.coordinates[1], fill='blue')
        self.canvas.create_line(self.coordinates[1], self.coordinates[2], fill='blue')
        self.canvas.create_line(self.coordinates[2], self.coordinates[3], fill='blue')
        self.canvas.create_line(self.coordinates[3], self.coordinates[0], fill='blue')

        # 現在の座標リセット
        self.coordinates = []
        self.canvas.bind("<Button-1>", self.select_point)  # 点選択を再バインド

    def remove_last_coordinate(self):
        if self.coordinates:
            self.coordinates.pop()
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

            for obstacle in self.obstacles:
                self._draw_obstacle(obstacle)  # 既存障害物の再描画

            self.canvas.bind("<Button-1>", self.select_point)
            for coordinate in self.coordinates:
                x, y = coordinate
                self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill='red')

    def _draw_obstacle(self, coordinates):
        # 障害物を描画
        self.canvas.create_line(coordinates[0], coordinates[1], fill='blue')
        self.canvas.create_line(coordinates[1], coordinates[2], fill='blue')
        self.canvas.create_line(coordinates[2], coordinates[3], fill='blue')
        self.canvas.create_line(coordinates[3], coordinates[0], fill='blue')

    # def output_coordinates(self):
    #     if not self.obstacles:
    #         print("Error: 障害物が設定されていません。")
    #         return

    #     all_coordinates = []
    #     for obstacle in self.obstacles:
    #         # 左上と右下を特定
    #         xs = [coord[0] for coord in obstacle]
    #         ys = [coord[1] for coord in obstacle]
    #         top_left = (min(xs), min(ys))
    #         bottom_right = (max(xs), max(ys))

    #         # スケール変換
    #         converted_top_left = [int(top_left[0] * self.reduction_ratio[0]), int(top_left[1] * self.reduction_ratio[1])]
    #         converted_bottom_right = [int(bottom_right[0] * self.reduction_ratio[0]), int(bottom_right[1] * self.reduction_ratio[1])]

    #         all_coordinates.append(converted_top_left + converted_bottom_right)

    #     print(all_coordinates)

    def output_coordinates(self):
        if not self.obstacles:
            print("Error: 障害物が設定されていません。")
            return
        all_coordinates = []  # 全障害物の4点座標をリストとして格納
        for obstacle in self.obstacles:
            all_coordinates.append(obstacle)  # 障害物の4点座標をそのままリストに追加
        print(all_coordinates)  # 出力を確認

    def capture_frame(self):
        self.streaming = False
        self.btn_capture.config(state="disabled")
        self.btn_play.config(state="normal")


    def play_stream(self):
        self.coordinates = []
        self.obstacles = []
        self.streaming = True
        self.captured_frame = None

        self.btn_capture.config(state="normal")
        self.btn_play.config(state="disabled")
        self.btn_undistort.config(state="disabled")
        self.btn_remove_last.config(state="disabled")
        self.btn_output.config(state="disabled")
        self.btn_obstacle.config(state="disabled")

        self.update()

    def update(self):
        if self.streaming:
            ret, frame = self.vid.read()
            if ret:
                self.orig_frame = frame
                self.captured_frame = cv2.resize(frame, (1080, 720), interpolation=cv2.INTER_AREA)
                self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB)))
                self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        self.window.after(10, self.update)

    def __del__(self):
        if self.vid.isOpened():
            self.vid.release()

if __name__ == '__main__':
    camera_ip, camera_code  = '192.168.1.146', 'ZGY8586252'
    root = CameraApp(tk.Tk(), "座標取得", CAMERA_CONFIG[camera_code], video_source=f"rtsp://{camera_ip}:554/rtpstream/config1=r")