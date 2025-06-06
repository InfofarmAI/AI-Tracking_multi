import cv2
import time
import os
from datetime import datetime, timedelta
import shutil
import subprocess

cap = cv2.VideoCapture("rtsp://192.168.1.146:554/rtpstream/config1")

# フレームの幅と高さを取得
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# フレームレートを設定
fps = 30.0

# 動画録画時間設定
REC_TIME = 30  # (秒)
REC_FRAME_LIMIT = int(fps * REC_TIME)

# 動画保存フォルダとテキストファイルのパス
VIDEO_DIR = "videos"
TEXT_FILE = "video_list.txt"
os.makedirs(VIDEO_DIR, exist_ok=True)

def get_video_filename():
    """現在時刻を使って動画ファイル名を生成"""
    current_time = datetime.now()
    return current_time.strftime("%H%M%S%f")[:-3]  # 時分秒ミリ秒を取得（9桁）

def start_new_video_writer():
    """新しい動画ファイルを作成"""
    video_filename = os.path.join(VIDEO_DIR, get_video_filename() + ".mp4")
    out = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))
    print(f"新しい動画を作成: {video_filename}")
    return out, video_filename

def record_and_process_video():
    frame_count = 0
    out, video_filename = start_new_video_writer()
    start_time = time.time()

    # 30秒間の録画
    while frame_count < REC_FRAME_LIMIT:
        ret, frame = cap.read()
        if not ret:
            break

        cv2.imshow("Camera", frame)
        out.write(frame)
        frame_count += 1

        # 'q' キーを押すと録画終了
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    out.release()

    cap.release()

    # 録画が完了したら画像に変換
    slice_video_to_images(video_filename)

def slice_video_to_images(video_filename):
    """動画を0.2秒ごとにスライスして画像を保存する処理"""
    # 動画を読み込む
    cap_video = cv2.VideoCapture(video_filename)
    video_filename = os.path.basename(video_filename)
    video_time_str = video_filename.split('.')[0]  # "174821419"
    video_time = datetime.strptime(video_time_str, '%H%M%S%f')

    # フォルダが存在しない場合は作成
    output_dir = video_time_str
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 動画が開けない場合のエラーチェック
    if not cap_video.isOpened():
        print("動画を開くことができませんでした")
        return

    frame_count = 0
    fps = cap_video.get(cv2.CAP_PROP_FPS)  # フレームレートを取得
    interval = 0.2  # 0.2秒ごとに画像を保存する間隔

    # 開始時間を設定 (動画内のタイムスタンプの基準となる時間)
    current_video_time = video_time

    while True:
        # フレームを0.2秒ごとにスキップ
        cap_video.set(cv2.CAP_PROP_POS_MSEC, frame_count * interval * 1000)
        image_ret, image = cap_video.read()

        if not image_ret:
            break  # 動画の最後に達した場合は終了

        # 動画内の現在のフレームに対応する時刻を設定
        output_time = current_video_time + timedelta(seconds=frame_count * interval)

        # 時刻をファイル名にしてフレームを保存
        timestamp_str = output_time.strftime("%H%M%S%f")[:-3]  # ミリ秒までフォーマット
        output_file = os.path.join(output_dir, f"{timestamp_str}.jpg")

        # フレームをJPGとして保存
        cv2.imwrite(output_file, image)
        frame_count += 1

    cap_video.release()
    print(f"動画 {video_filename} のスライスが完了しました")

    # 画像をコピーして別の場所で処理する
    copy_jpg_files(output_dir)

def copy_jpg_files(video_filename):
    """スライスした画像を指定のフォルダに移動させる処理"""
    cc_images_path = "CCImageReader/images"
    if not os.path.exists(cc_images_path):
        os.makedirs(cc_images_path)

    for filename in os.listdir(video_filename):
        if filename.lower().endswith('.jpg'):
            source_file = os.path.join(video_filename, filename)
            cc_destination_file = os.path.join(cc_images_path, filename)
            shutil.copy2(source_file, cc_destination_file)
            print(f"コピーしました: {filename}")

def run_executable():
    """EXEファイルを実行する"""
    exe_path = "CCImageReader/CCImageReader.exe"
    process = subprocess.Popen(exe_path)
    process.wait()
    print("CC解析完了しました。")

# メイン処理：動画を録画し、処理する
record_and_process_video()
