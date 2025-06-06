import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog
from utils3.get_transform_pt import transform_pt, REDUCTION_RATIO, to_two_dimension, CAMERA_CONFIG
from PIL import ImageGrab

class CameraApp:
    def __init__(self, window, window_title, camera_config,mtx, dist, new_mtx, video_source=0):
        self.window = window
        self.camera_config = camera_config
        self.video_source = video_source
        self.input_size = (1920, 1080)
        self.reduction_ratio = (self.input_size[0] / 960, self.input_size[1] / 540)
        self.coordinates = []  # 現在選択中の障害物座標
        self.obstacles = []    # 全障害物の座標リスト
        self.captured_frame = None
        self.orig_frame = None
        self.streaming = True
        self.vid = cv2.VideoCapture(video_source)
        self.window.title(window_title)
        self.is_first_frame = True
        self.all=[]
        
        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)

        # ウィンドウサイズを調整
        self.window.geometry("1920x800")

        # 左側のキャンバス（画像表示用）
        self.canvas_left = tk.Canvas(window, width=960, height=540)
        self.canvas_left.grid(row=0, column=0, padx=0, pady=0)

        # 右側のキャンバス（画像表示用）
        self.canvas_right = tk.Canvas(window, width=960, height=540)
        self.canvas_right.grid(row=0, column=1, padx=0, pady=0)

        # ボタンの作成
        # self.btn_play = tk.Button(window, text="再生", width=15, height=2, command=self.play_stream)
        # self.btn_play.config(state="disabled")
        # self.btn_play.grid(row=1, column=0, padx=5, pady=5)

        self.btn_capture = tk.Button(window, text="停止", width=15, height=2, command=self.capture_frame)
        self.btn_capture.grid(row=1, column=1, padx=5, pady=5)

        self.btn_remove_last = tk.Button(self.window, text="最後の点を削除", width=15, height=2, command=self.remove_last_coordinate)
        self.btn_remove_last.grid(row=2, column=0, padx=5, pady=5)

        self.btn_output = tk.Button(window, text="座標出力", width=15, height=2, command=self.output_coordinates)
        self.btn_output.grid(row=2, column=1, padx=5, pady=5)

        self.btn_obstacle = tk.Button(window, text="障害物設定", width=15, height=2, command=self.set_obstacle)
        self.btn_obstacle.grid(row=3, column=0, padx=5, pady=5)

        self.btn_exit = tk.Button(window, text="終了", width=15, height=2, command=self.exit_app)
        self.btn_exit.grid(row=3, column=1, padx=5, pady=5)

        # ボタンの追加
        self.btn_load_image = tk.Button(window, text="画像読み込み", width=15, height=2, command=self.load_image)
        self.btn_load_image.grid(row=4, column=1, padx=5, pady=5)

        # テキストボックスの追加
        self.entry_label = tk.Entry(window, width=20)
        self.entry_label.grid(row=4, column=0, padx=5, pady=5)

        # 初期設定
        self.canvas_left.bind("<Button-1>", self.select_point)
        self.btn_remove_last.config(state="normal")
        self.btn_output.config(state="normal")
        self.btn_obstacle.config(state="normal")

        self.update()
        self.window.mainloop()

    def select_point(self, event):
        if len(self.coordinates) < 4:
            self.coordinates.append((event.x, event.y))
            self.canvas_left.create_oval(event.x - 2, event.y - 2, event.x + 2, event.y + 2, fill='red')

    def set_obstacle(self):
        if len(self.coordinates) != 4:
            print("Error: 4点を選択してください。")
            return

        # 障害物の座標を保存
        self.obstacles.append(self.coordinates.copy())

        # 障害物を描画
        self.canvas_left.create_line(self.coordinates[0], self.coordinates[1], fill='blue')
        self.canvas_left.create_line(self.coordinates[1], self.coordinates[2], fill='blue')
        self.canvas_left.create_line(self.coordinates[2], self.coordinates[3], fill='blue')
        self.canvas_left.create_line(self.coordinates[3], self.coordinates[0], fill='blue')

        # 現在の座標リセット
        self.coordinates = []
        self.canvas_left.bind("<Button-1>", self.select_point)  # 点選択を再バインド

    def remove_last_coordinate(self):
        if self.coordinates:
            self.coordinates.pop()
            self.canvas_left.delete("all")
            self.canvas_left.create_image(0, 0, image=self.photo, anchor=tk.NW)

            for obstacle in self.obstacles:
                self._draw_obstacle(obstacle)  # 既存障害物の再描画

            self.canvas_left.bind("<Button-1>", self.select_point)
            for coordinate in self.coordinates:
                x, y = coordinate
                self.canvas_left.create_oval(x - 2, y - 2, x + 2, y + 2, fill='red')

    def _draw_obstacle(self, coordinates):
        # 障害物を描画
        self.canvas_left.create_line(coordinates[0], coordinates[1], fill='blue')
        self.canvas_left.create_line(coordinates[1], coordinates[2], fill='blue')
        self.canvas_left.create_line(coordinates[2], coordinates[3], fill='blue')
        self.canvas_left.create_line(coordinates[3], coordinates[0], fill='blue')
    
    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg;*.png;*.jpeg")])
        if not file_path:
            return  # キャンセルされた場合

        self.streaming = False  # カメラストリームを停止
        self.captured_frame = cv2.imread(file_path)  # 画像を読み込む
        if self.captured_frame is None:
            print("Error: 画像の読み込みに失敗しました。")
            return

        # 画像をリサイズして表示
        self.captured_frame = cv2.resize(self.captured_frame, (960, 540), interpolation=cv2.INTER_AREA)
        self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB)))
        self.canvas_left.create_image(0, 0, image=self.photo, anchor=tk.NW)

        # 画像表示中は「再生」ボタンを有効にする
        # self.btn_play.config(state="normal")

    def output_coordinates(self):
        if not self.obstacles:
            print("Error: 障害物が設定されていません。")
            return
        all_coordinates = []  # 全障害物の4点座標をリストとして格納
        for obstacle in self.obstacles:
            for item in obstacle:
                # 俯瞰座標変換
                print(item)
                # item=(item[0],item[1])
                item=(item[0]*self.reduction_ratio[0],item[1]*self.reduction_ratio[1])
                print(item)
                converted_obstacle = cv2.undistortPoints(item, mtx, dist, None, new_mtx)
                # 平面座標に変換
                dst_pt = transform_pt(converted_obstacle.reshape(-1), M)
                # converted_obstacle = (dst_pt[0]*REDUCTION_RATIO[0],dst_pt[1]*REDUCTION_RATIO[1])
                converted_obstacle = (dst_pt[0]*REDUCTION_RATIO["1"][0]/self.reduction_ratio[0]*(1920/1080),dst_pt[1]*REDUCTION_RATIO["1"][1]/self.reduction_ratio[1]*(1080/1920))
                # converted_obstacle = self.convert_to_overhead(obstacle)
                all_coordinates.append(converted_obstacle)
        # テキストボックスの値を取得
        label_text = self.entry_label.get().strip()
        if not label_text:
            label_text = "障害物"
        all_coordinates.append(label_text)
        self.draw_obstacle_on_right(all_coordinates)
        # self.draw_obstacle_on_right(all_coordinates)
        self.all.append(all_coordinates)
        self.obstacles=[]
        print(all_coordinates)  # 出力を確認

    def draw_obstacle_on_right(self, coordinates):
        # print("座標リスト:", coordinates)
        # print("要素数:", len(coordinates))
        if len(coordinates) != 5:
            print("Error: 4点の座標が必要です。")
            return

        # 4点の座標を取得
        p1, p2, p3, p4,label = coordinates

        # 右側のキャンバスに四角形を描画
        self.canvas_right.create_line(p1, p2, fill="red", width=2)
        self.canvas_right.create_line(p2, p3, fill="red", width=2)
        self.canvas_right.create_line(p3, p4, fill="red", width=2)
        self.canvas_right.create_line(p4, p1, fill="red", width=2)

        # 中心座標を計算
        center_x = (p1[0] + p2[0] + p3[0] + p4[0]) // 4
        center_y = (p1[1] + p2[1] + p3[1] + p4[1]) // 4

        # 中心に文字を表示
        self.canvas_right.create_text(center_x, center_y, text=label, fill="black", font=('Helvetica', 12, 'bold'))

        # print("障害物が描画されました。")

    def capture_frame(self):
        self.streaming = False
        self.btn_capture.config(state="disabled")
        # self.btn_play.config(state="normal")

    def play_stream(self):
        self.coordinates = []
        self.obstacles = []
        self.streaming = True
        self.captured_frame = None

        self.btn_capture.config(state="normal")
        self.btn_play.config(state="disabled")
        self.update()

    def update(self):
        if self.streaming:
            ret, frame = self.vid.read()
            if ret:
                self.orig_frame = frame
                self.captured_frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
                self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB)))
                self.canvas_left.create_image(0, 0, image=self.photo, anchor=tk.NW)

        # # 最初のフレームでのみ白い画像を表示
        # if self.is_first_frame:
        #     white_image = np.ones((540, 960, 3), dtype=np.uint8) * 255
        #     self.photo_right = ImageTk.PhotoImage(image=Image.fromarray(white_image))
        #     self.canvas_right.create_image(0, 0, image=self.photo_right, anchor=tk.NW)
        #     self.is_first_frame = False  # 最初のフレームが終わったらフラグを更新
        if self.is_first_frame:
            # 背景画像の読み込み
            bg_image = cv2.imread("person_map.jpg")  # ★ 好きな画像ファイルを読み込む
            if bg_image is None:
                print("背景画像の読み込みに失敗しました。白画像を使用します。")
                bg_image = np.ones((540, 960, 3), dtype=np.uint8) * 255  # 白画像
            else:
                # 必要に応じてリサイズ
                bg_image = cv2.resize(bg_image, (960, 540), interpolation=cv2.INTER_AREA)

            # 右側のキャンバスに画像を貼る
            self.photo_right = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(bg_image, cv2.COLOR_BGR2RGB)))
            self.canvas_right.create_image(0, 0, image=self.photo_right, anchor=tk.NW)

            self.is_first_frame = False
        
        # print(self.all)

        # 右側に障害物を描画
        for obstacle in self.all:
            self.draw_obstacle_on_right(obstacle)

        self.window.after(10, self.update)

    def exit_app(self):
        # 右側のキャンバスの内容を画像として保存
        self.save_canvas_as_image()

        # print(f"画像を保存しました: output_image.png")
        self.window.quit()

    def save_canvas_as_image(self):
        # 右側のキャンバスの描画内容を保存するためにImageGrabを使用
        x1 = self.canvas_right.winfo_rootx()
        y1 = self.canvas_right.winfo_rooty()
        x2 = x1 + self.canvas_right.winfo_width()
        y2 = y1 + self.canvas_right.winfo_height()

        # 指定した領域をキャプチャ
        image = ImageGrab.grab(bbox=(x1-2, y1+2, x2-6, y2-2))
        image = image.resize((1080, 1920), Image.Resampling.LANCZOS)
        image.save("person_map2.jpg")  # 保存


    def __del__(self):
        if self.vid.isOpened():
            self.vid.release()
            

if __name__ == '__main__':
    camera_ip, camera_code  = '192.168.1.142', 'ZGY8586252'
    M = to_two_dimension(CAMERA_CONFIG[camera_code])
    mtx, dist, new_mtx = np.array(CAMERA_CONFIG[camera_code]['mtx']), np.array(CAMERA_CONFIG[camera_code]['dist']), np.array(CAMERA_CONFIG[camera_code]['new_mtx'])
    # print(mtx, dist, new_mtx)
    root = CameraApp(tk.Tk(), "座標取得", CAMERA_CONFIG[camera_code],mtx, dist, new_mtx, video_source=f"rtsp://{camera_ip}:554/rtpstream/config1=r")
