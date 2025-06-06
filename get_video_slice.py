#SK-VMSから動画を直接ダウンロード(エクスポート) -> APIを使用
import requests
import os
import urllib3
import sys
import threading
import shutil
import subprocess
from datetime import datetime, timedelta

import datetime
import cv2
import time

# SSL警告を無視する
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#ログインセッションの作成
def create_login_session():
    # URLと認証情報
    url = f"https://{ip}:{port}/rest/v3/login/sessions"
    username = "admin"
    password = "info1881"

    # === エンドポイントとパラメータ ===
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "username": username,
        "password": password,
        "setCookie": True
    }

    # === POST リクエスト実行 ===
    response = requests.post(url, headers=headers, json=payload, verify=False)

    # === レスポンス出力 ===
    # レスポンスが正常なら token を取り出す
    if response.ok:
        token = response.json().get("token")
        print("取得した token:", token)
        return token
    else:
        print("ログイン失敗:", response.status_code, response.text)
        return None

# #Device情報の取得API
def get_camera_conf(ip, port, camera_id):
    # URLと認証情報
    url = f"https://{ip}:{port}/rest/v3/devices"
    username = "admin"
    password = "info1881"

    # リクエストに認証情報を追加
    headers = {
        "accept": "application/json",
        "x-runtime-guid": TOKEN
    }
    response = requests.get(url, auth=(username, password), headers=headers, verify=False)

    # HTTPエラーをチェック
    if response.status_code == 200:
        devices = response.json()
        for device in devices:
            name = device.get("name")
            device_id = device.get("id")
            if name == camera_id :
                return name, device_id
    else:
        print(f"HTTPエラー: {response.status_code}")


def download_video_start(url, filename):
    """
    URLから動画をダウンロードして現在のディレクトリに保存する
    :param url: ダウンロード対象のURL
    :param filename: 保存する際のファイル名(時分秒ミリ秒-> 9桁)
    """
    # 現在のファイルが存在するディレクトリ
    # current_dir = os.path.dirname(os.path.abspath(__file__))

    # 保存先のファイルパス
    video_path = os.path.join(CURRNT_DIR, "videos")
    os.makedirs(video_path, exist_ok=True)

    save_path = os.path.join(video_path, filename)

    try:
        # ストリームモードでリクエストを送信
        headers = {
            "accept": "*/*",
            "x-runtime-guid": TOKEN
        }
        response = requests.get(url, stream=True, headers=headers, verify=False)

        # ファイルを保存
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # 空のチャンクを無視
                    file.write(chunk)

        #動画名をテキストに保存
        with open(os.path.join(CURRNT_DIR,"video_list.txt"), "a") as file:
            file.write(save_path + "\n")

        # 動画名から撮影時刻を取得 (仮に動画名が「時分秒ミリ秒」の形式であると仮定)
        # 例: "174821419.mp4" -> 時間: 17:48:21.419
        video_filename = os.path.basename(filename)
        video_time_str = video_filename.split('.')[0]  # "174821419"

        #module/split.py読み込み用 2024.10.21 torisato
        # with open(os.path.join(CURRNT_DIR,"video.txt"), "a") as file:
        #     file.write(os.path.join(CURRNT_DIR, video_time_str) + "\n")
    except requests.exceptions.RequestException as e:
        print(f"ダウンロード中にエラーが発生しました: {e}")

def download_video(camera_name, camera_id, current_time):
    url = f"https://{ip}:{port}/media/{camera_id}.mp4?pos={date}T{current_time}&duration=30"
    # "-" を "_" に置き換える
    time_stanp = current_time.replace(":","")

    # 移動先の新しいファイル名
    new_file_name = str(time_stanp) + "000.mp4"

    # ダウンロード実行
    download_video_start(url, new_file_name)

def main(current_time, end_time):
    # 無限ループで時間を表示
    while True:
        print("現在の時刻:", current_time.strftime("%H:%M:%S"))
        #動画のダウンロード
        download_video(camera_name, camera_id, current_time.strftime("%H:%M:%S"))
        # 30秒加算
        current_time += datetime.timedelta(seconds=30)
        if current_time == end_time:
            break
        time.sleep(30) #加算分のsleep処理(30)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# 動画を0.2秒ごとにフレームごとに処理する関数
def slice_video_to_images():
    video_list = os.path.join(CURRNT_DIR,"video_list.txt")
    while True:
        if os.path.exists(video_list):
            with open(video_list, 'r') as f:
                lines = f.readlines()
            if len(lines) >= 1:
                video_filename = lines[0].strip()
                # テキストファイルの最初の行を削除
                with open(video_list, 'w') as f:
                    f.writelines(lines[1:])

                """作成された動画を0.2秒ごとにスライスして画像に保存"""
                cap_video = cv2.VideoCapture(video_filename)
                # 動画名から撮影時刻を取得 (仮に動画名が「時分秒ミリ秒」の形式であると仮定)
                # 例: "174821419.mp4" -> 時間: 17:48:21.419
                video_filename = os.path.basename(video_filename)
                video_time_str = video_filename.split('.')[0]  # "174821419"
                # video_time = datetime.strptime(video_time_str, '%H%M%S%f')
                video_time = datetime.datetime.strptime(video_time_str, '%H%M%S%f')

                # フォルダが存在しない場合は作成
                output_dir = os.path.join(CURRNT_DIR, video_time_str)
                # if not os.path.exists(output_dir):
                #     os.makedirs(output_dir)
                os.makedirs(output_dir,exist_ok=True)

                # 動画が開けない場合のエラーチェック
                if not cap_video.isOpened():
                    print("動画を開くことができませんでした")
                    exit()

                # フレームごとの処理
                frame_count = 0
                fps = cap_video.get(cv2.CAP_PROP_FPS)  # フレームレートを取得
                interval = 0.2  # 5FPS(0.2秒ごとに画像を保存する間隔)
                # interval = 0.1  #10FPS(0.2秒ごとに画像を保存する間隔)

                # 開始時間を設定 (動画内のタイムスタンプの基準となる時間)
                current_video_time = video_time
                while True:
                    # フレームを0.2秒ごとにスキップ
                    cap_video.set(cv2.CAP_PROP_POS_MSEC, frame_count * interval * 1000)
                    image_ret, image = cap_video.read()

                    if not image_ret:
                        break  # 動画の最後に達した場合は終了

                    if frame_count == 150:
                        break

                    # 動画内の現在のフレームに対応する時刻を設定
                    output_time = current_video_time + timedelta(seconds=frame_count * interval)

                    # 時刻をファイル名にしてフレームを保存
                    timestamp_str = output_time.strftime("%H%M%S%f")[:-3]  # ミリ秒までフォーマット
                    output_file = os.path.join(output_dir, f"{timestamp_str}.jpg")

                    # フレームをJPGとして保存
                    cv2.imwrite(output_file, image)
                    frame_count += 1

                cap_video.release()

                #2024.10.21 torisato
                # 拡張子を除いた形式　
                origin_forder_path = os.path.splitext(video_filename)
                copy_jpg_files(os.path.join(CURRNT_DIR,origin_forder_path[0]))
                with open(os.path.join(CURRNT_DIR,"video.txt"), "a") as file:
                    file.write(os.path.join(CURRNT_DIR, video_time_str) + "\n")
                #いろあと静止画解析exe実行
                run_executable()


def copy_jpg_files(video_filename):
    """スライスした画像を指定のフォルダに移動させる処理"""
    cc_images_path = os.path.join(CURRNT_DIR,"CCImageReader/images")
    # # CCImageReaderに「images」フォルダが存在しない場合は作成
    # if os.path.exists(cc_images_path):
    #     shutil.rmtree(cc_images_path) #中身を再帰削除
    # os.makedirs(cc_images_path, exist_ok=True)

    if os.path.exists(cc_images_path):  # フォルダが存在するかチェック
        try:
            shutil.rmtree(cc_images_path)
        except FileNotFoundError:
            print(f"❌ 削除しようとしたフォルダ {cc_images_path} はすでに存在しません。処理をスキップします。")
    os.makedirs(cc_images_path, exist_ok=True)

    # 指定されたフォルダ内のすべてのファイルを取得
    for filename in os.listdir(video_filename):
        # .jpgファイルかどうかをチェック
        if filename.lower().endswith('.jpg'):
            # ソースファイルのパス
            source_file = os.path.join(video_filename, filename)
            # デスティネーションファイルのパス(CC)
            cc_destination_file = os.path.join(cc_images_path, filename)
            # ファイルをコピー
            shutil.copy2(source_file, cc_destination_file)

def run_executable():
    """EXEファイルを実行する"""
    # 実行したいexeファイルのパスを指定
    exe_path = os.path.join(CURRNT_DIR,"CCImageReader/CCImageReader.exe")
    # # exeファイルを起動
    process = subprocess.Popen(exe_path)
    process.wait()
    print("CC解析完了しました。")

CURRNT_DIR =  sys.argv[1]
camera_id =  sys.argv[2]

# URLとパラメータを設定
ip = "192.168.1.101"
port = "7001"
#TODO 現在日時の取得
date = "2025-01-28"
#TODO 始業時間の設定
start_time = "16:30:00"
# end_time = "16:31:00"
end_time = "16:31:00"

#ログインセッションの作成
TOKEN = create_login_session()

camera_name, camera_id = get_camera_conf(ip, port, camera_id)

# 初期時刻を設定
current_time = datetime.datetime.strptime(start_time, "%H:%M:%S")
end_time = datetime.datetime.strptime(end_time, "%H:%M:%S")

# メインスレッド：Webカメラからの録画を開始
main_thread = threading.Thread(target=main, args=(current_time,end_time,))
main_thread.start()

# サブスレッド：動画リストを読み込み、動画ファイルを処理
def run_processing_thread():
    processing_thread = threading.Thread(target=slice_video_to_images)
    processing_thread.start()
    processing_thread.join()  # 処理が終わったらスレッド終了
    run_processing_thread()   # 処理が終わったらスレッドを再起動

run_processing_thread()