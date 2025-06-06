import cv2
import threading
import time
import os
from datetime import datetime, timedelta
import subprocess
import shutil
import sys

camera_id=sys.argv[1]
camera_ip=sys.argv[2]

cap = cv2.VideoCapture(camera_ip)

# フレームの幅と高さを取得
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# フレームレートを設定
# fps = cap.get(cv2.CAP_PROP_FPS)
fps = 30.0
# fps = 5.0

#動画録画時間設定
REC_TIME = 30#(秒)
REC_FRAME_LIMIT = int(fps * REC_TIME)
# print("REC_FRAME_LIMIT",REC_FRAME_LIMIT)

# 動画保存フォルダとテキストファイルのパス
VIDEO_DIR = os.path.join(camera_id,"videos")
TEXT_FILE = os.path.join(camera_id,"video_list.txt")
os.makedirs(VIDEO_DIR, exist_ok=True)

video_filename_txt = ""

def get_video_filename():
    """現在時刻を使って動画ファイル名を生成"""
    current_time = datetime.now()
    return current_time.strftime("%H%M%S%f")[:-3]  # 時分秒ミリ秒を取得（9桁）

def start_new_video_writer():
    """新しい動画ファイルを作成"""
    video_filename = os.path.join(VIDEO_DIR, get_video_filename() + ".mp4")
    out = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))
    # out = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), 30, (frame_width, frame_height))
    #動画名をテキストに保存
    with open(TEXT_FILE, "a") as file:
        file.write(video_filename + "\n")
    global video_filename_txt
    video_filename_txt=video_filename

    # #module/split.py読み込み用 2024.10.21 torisato
    # with open("video.txt", "a") as file:
    #     #2024.10.21 torisato
    #     # 動画名から撮影時刻を取得 (仮に動画名が「時分秒ミリ秒」の形式であると仮定)
    #     # 例: "174821419.mp4" -> 時間: 17:48:21.419
    #     video_filename = os.path.basename(video_filename)
    #     video_time_str = video_filename.split('.')[0]  # "174821419"
    #     file.write(video_time_str + "\n")

    print(f"新しい動画を作成: {video_filename}")
    return out, video_filename

# Webカメラのストリーミング映像を10秒単位で録画する関数
def record_video():
    while True:
        frame_count = 0
        out, video_filename = start_new_video_writer()
        start_time = time.time()

        # 10秒間の録画
        # while time.time() - start_time < REC_TIME:
        # print(REC_FRAME_LIMIT)
        while frame_count < REC_FRAME_LIMIT:
            ret, frame = cap.read()
            if not ret:
                break

            cv2.imshow("Camera",frame)

            out.write(frame)

            frame_count += 1

            # 'q' キーを押すと録画終了
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        out.release()

    cap.release()
    out.release()

# 動画を0.2秒ごとにフレームごとに処理する関数
def slice_video_to_images():
    while True:
        if os.path.exists(TEXT_FILE):
            with open(TEXT_FILE, 'r') as f:
                lines = f.readlines()

            if len(lines) >= 2:
                video_filename = lines[0].strip()
                # print("video_filename",video_filename)

                # テキストファイルの最初の行を削除
                with open(TEXT_FILE, 'w') as f:
                    f.writelines(lines[1:])

                """作成された動画を0.2秒ごとにスライスして画像に保存"""
                cap_video = cv2.VideoCapture(video_filename)
                # 動画名から撮影時刻を取得 (仮に動画名が「時分秒ミリ秒」の形式であると仮定)
                # 例: "174821419.mp4" -> 時間: 17:48:21.419
                video_filename = os.path.basename(video_filename)
                video_time_str = video_filename.split('.')[0]  # "174821419"
                video_time = datetime.strptime(video_time_str, '%H%M%S%f')

                # フォルダが存在しない場合は作成
                output_dir = os.path.join(camera_id,video_time_str)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                # print("A")
                # 動画が開けない場合のエラーチェック
                if not cap_video.isOpened():
                    print("動画を開くことができませんでした")
                    exit()

                # フレームごとの処理
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

                    # print(f"フレーム {frame_count} を保存しました: {output_file}")
                    frame_count += 1

                cap_video.release()
                print(f"動画 {video_filename} のスライスが完了しました")

                #2024.10.21 torisato
                # 拡張子を除いた形式　
                origin_forder_path = os.path.splitext(video_filename)
                copy_jpg_files(os.path.join(camera_id,origin_forder_path[0]))
                with open(os.path.join(camera_id,"video.txt"), "a") as file:
                    #2024.10.21 torisato
                    # 動画名から撮影時刻を取得 (仮に動画名が「時分秒ミリ秒」の形式であると仮定)
                    # 例: "174821419.mp4" -> 時間: 17:48:21.419
                    print("test",video_filename)
                    video_time_str = video_filename.split('.')[0]  # "174821419"
                    file.write(camera_id+"/"+video_time_str + "\n")
                #いろあと静止画解析exe実行
                run_executable()

                path = os.path.join(camera_id,os.path.join( "CCImageReader","result_" + str(origin_forder_path[0])))
                # コピー元のファイルパス（result_123456789フォルダ内のresult.csv）
                source_file = os.path.join(path, "result.csv")
                # コピー先のパス
                destination_folder = os.path.join(camera_id,"data/")
                destination_file = os.path.join(destination_folder, "result.csv")

                # コピー処理
                if os.path.exists(source_file):
                    shutil.copy(source_file, destination_file)
                    # print(f"ファイルを {destination_file} にコピーしました。")
                else:
                    print("CCが解析できませんでした。")


def copy_jpg_files(video_filename):
    """スライスした画像を指定のフォルダに移動させる処理"""
    cc_images_path = os.path.join(camera_id,"CCImageReader/images")
    # CCImageReaderに「images」フォルダが存在しない場合は作成
    shutil.rmtree(cc_images_path) #中身を再帰削除
    os.makedirs(cc_images_path, exist_ok=True)
    # gsam2_images_path = "gsam2/notebooks/videos/images"
    # # gsam2/notebooks/videosに「images」フォルダが存在しない場合は作成
    # shutil.rmtree(gsam2_images_path) #中身を再帰削除
    # os.makedirs(gsam2_images_path, exist_ok=True)
    # 指定されたフォルダ内のすべてのファイルを取得
    for filename in os.listdir(video_filename):
        # .jpgファイルかどうかをチェック
        if filename.lower().endswith('.jpg'):
            # ソースファイルのパス
            source_file = os.path.join(video_filename, filename)
            # デスティネーションファイルのパス(CC)
            cc_destination_file = os.path.join(cc_images_path, filename)
            # デスティネーションファイルのパス(gsam2)
            # gsam2_destination_file = os.path.join(gsam2_images_path, filename)
            # ファイルをコピー
            shutil.copy2(source_file, cc_destination_file)
            # shutil.copy2(source_file, gsam2_destination_file)
            # print(f"コピーしました: {filename}")

def run_executable():
    """EXEファイルを実行する"""
    # 実行したいexeファイルのパスを指定
    exe_path = os.path.join(camera_id,"CCImageReader/CCImageReader.exe")
    # exeファイルを起動
    process = subprocess.Popen(exe_path)
    process.wait()
    print("CC解析完了しました。")
     #module/split.py読み込み用 2024.10.21 torisato
    


# メインスレッド：Webカメラからの録画を開始
main_thread = threading.Thread(target=record_video)
main_thread.start()

# サブスレッド：動画リストを読み込み、動画ファイルを処理
def run_processing_thread():
    processing_thread = threading.Thread(target=slice_video_to_images)
    processing_thread.start()
    processing_thread.join()  # 処理が終わったらスレッド終了
    run_processing_thread()   # 処理が終わったらスレッドを再起動

run_processing_thread()
