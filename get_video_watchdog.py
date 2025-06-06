"""
SK-VMSから動画をダウンロードし、解析用にフレーム分割・処理を行うツール

このスクリプトは以下の処理を自動化します：

1. SK-VMS（監視カメラシステム）へログインし、指定したカメラから指定時間の動画をダウンロード
2. 動画をフレームごとに画像にスライス（指定間隔で最大150フレーム）
3. フレームを指定のフォルダ（CCImageReader/images）に移動
4. 外部実行ファイル（CCImageReader.exe）を呼び出して解析を開始
5. ファイル監視により `video_list.txt` の更新をトリガーとして動画解析を開始
6. 終了後にログファイル（video.txt）に `stop` を記録

使用方法:
    python script.py <作業ディレクトリ> <カメラID>

例:
    python skvms_video_processor.py C:/export_dir 192.168.1.100

依存モジュール:
    - requests
    - urllib3
    - opencv-python
    - watchdog
    - GPUtil
    - psutil
    - xml.etree.ElementTree
    - threading, shutil, subprocess, datetime, os, time, sys

注意点:
    - `application.xml` に必要な設定（SK-VMS接続情報、録画時間など）を定義
    - CCImageReader.exe と画像処理の関連フォルダ構成が事前に整っている必要あり
    - 動画が30秒未満の場合は再試行（最大2回）

作成日：2025年5月
作成者：インフォファーム
"""



#SK-VMSから動画を直接ダウンロード(エクスポート) -> APIを使用
import requests
import os
import urllib3
import threading
import shutil
import subprocess
from datetime import datetime, timedelta
import sys

import datetime
import cv2
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging


#CPUとGPUの処理可視化用
import psutil
import GPUtil
import time
import threading

#Application.xml
import xml.etree.ElementTree as ET

# SSL警告を無視する
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


#ログインセッションの作成
def create_login_session():
    """
    SK-VMSにログインしてセッション用のトークンを取得します。

    Returns:
        str: 認証トークン（成功時）
        None: ログイン失敗時
    """

    # URLと認証情報
    url = f"https://{ip}:{port}/rest/v3/login/sessions"

    # === エンドポイントとパラメータ ===
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "username": USER,
        "password": PASSWD,
        "setCookie": True
    }

    # === POST リクエスト実行 ===
    response = requests.post(url, headers=headers, json=payload, verify=False)

    # === レスポンス出力 ===
    # レスポンスが正常なら token を取り出す
    if response.ok:
        token = response.json().get("token")
        return token
    else:
        print("ログイン失敗:", response.status_code, response.text)
        logging.error("ログイン失敗: %s %s", response.status_code, response.text)
        return None

#Device情報の取得API
def get_camera_conf(ip, port, camera_id):
    """
    SK-VMSに接続し、指定したカメラ名に一致するデバイス情報を取得する。

    指定されたIPアドレスとポート番号を使用して、SK-VMSのデバイス情報エンドポイントにアクセスします。
    レスポンスに含まれるデバイスリストから、指定されたカメラ名（camera_id）と一致するデバイスを検索し、
    該当するデバイスの名前とデバイスIDを返します。

    Args:
        ip (str): SK-VMSサーバのIPアドレス。
        port (str or int): SK-VMSサーバのポート番号。
        camera_id (str): 照合するカメラの名称（SK-VMS上のカメラ名）。

    Returns:
        tuple: 一致したカメラ名とそのデバイスIDのタプル (name, device_id)。
        None: 一致するカメラが見つからない場合、またはHTTPエラーが発生した場合。
    """

    # URLと認証情報
    url = f"https://{ip}:{port}/rest/v3/devices"

    # リクエストに認証情報を追加
    headers = {
        "accept": "application/json",
        "x-runtime-guid": TOKEN
    }
    response = requests.get(url, auth=(USER, PASSWD), headers=headers, verify=False)

    # HTTPエラーをチェック
    if response.status_code == 200:
        devices = response.json()
        for device in devices:
            name = device.get("name")
            device_id = device.get("id")
            # print(f"Name: {name}, ID: {device_id}")
            if name == camera_id :
                return name, device_id
    else:
        print(f"HTTPエラー: {response.status_code}")
        logging.warning(f"HTTPエラー: {response.status_code}")


def download_video_start(url, filename):
    """
    指定されたURLから動画ファイルをダウンロードし、保存する。

    動画は最大2回までダウンロードを試行し、取得した動画の長さが30秒未満であれば再試行する。
    正常に30秒以上の動画を取得できた場合は指定フォルダに保存し、動画パスを video_list.txt に追記する。

    Args:
        url (str): ダウンロード対象の動画ファイルのURL。
        filename (str): 保存時のファイル名（.mp4 拡張子が自動で付与される）。

    Returns:
        bool:
            - True: ダウンロード成功かつ動画が30秒以上。
            - False: 動画が取得できなかった、または30秒未満だった場合。

    Notes:
        - 動画ファイルは CURRNT_DIR/videos フォルダに保存される。
        - ダウンロード時のリクエストヘッダには `x-runtime-guid`（TOKEN）が必要。
        - 取得した動画の再生時間は OpenCV で検証される。
    """
    if not filename.endswith(".mp4"):
        filename += ".mp4"

    # video_path = "videos"
    video_path = os.path.join(CURRNT_DIR, "videos")
    os.makedirs(video_path, exist_ok=True)
    save_path = os.path.join(video_path, filename)

    #動画ダウンロードの試行回数
    try_count = 2

    headers = {
        "accept": "*/*",
        "x-runtime-guid": TOKEN
    }

    #動画の長さを確認する
    def get_video_duration(filepath):
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return None

        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()

        if fps == 0:
            return None
        return frames / fps

    try:
        for i in range(try_count):
            #ダウンロード処理
            response = requests.get(url, stream=True, headers=headers, verify=False)

            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)

            #動画の長さをチェックし、30秒以下の動画を取得した場合は、エラーとする
            duration = get_video_duration(save_path)
            if duration:
                if duration <= 30:
                    print(f"❌{i}回目 動画指定時間以下です！")
                    #30秒以下の動画を削除し、30秒後に再度ダウンロード処理を実施
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    if i == (try_count - 1):
                        return False
                    time.sleep(30)
                    continue
                else:
                    print("✅指定時間を満たしています！")
                    break
            else:
                print("❌ 動画を取得できませんでした！")
                logging.warning("動画を取得できませんでした。")
                return False

        print(f"✅ 動画を保存しました: {save_path}")

        # with open("video_list.txt", "a") as file:
        with open(os.path.join(CURRNT_DIR,"video_list.txt"), "a") as file:
            file.write(save_path + "\n")

        return True
    except requests.exceptions.RequestException as e:
        print(f"⚠ ダウンロード中に例外が発生しました: {e}")
        logging.warning(f"ダウンロード中に例外が発生しました: {e}")
        return False

def download_video(camera_name, camera_id, current_time, video_time_seconds):
    url = f"https://{ip}:{port}/media/{camera_id}.mp4?pos={date}T{current_time}&duration={video_time_seconds}"
    # url = f"https://{ip}:{port}/media/{camera_id}.mp4?pos={date}T{current_time}&duration={video_time_seconds}&accurate_seek=true&resolution=1920x1080"
    # ":" を空白に置き換える
    time_stanp = current_time.replace(":","")

    # 移動先の新しいファイル名
    new_file_name = str(time_stanp) + "000.mp4"

    # ダウンロード実行
    """return-> 成功:True 失敗:False"""
    result = download_video_start(url, new_file_name)

    return result

def main_process(current_time, end_time, video_time_seconds):
    """
    指定された開始時刻から終了時刻まで、一定間隔で動画をダウンロードするメイン処理。

    Args:
        current_time (datetime.datetime): 処理開始時刻（例: 13:00:00）。
        end_time (datetime.datetime): 処理終了時刻（例: 14:00:00）。
        video_time_seconds (int): 1回のダウンロードで対象とする動画時間（秒数、通常30秒など）。

    処理内容:
        - `download_video` 関数を用いて、一定間隔で動画をダウンロード。
        - 動画の取得が失敗した場合は、スレッド終了用のイベントフラグ `stop_event` および `trigger_event` をセットし処理を中断。
        - 終了時刻に達するまで `video_time_seconds` 秒ずつ加算してループを継続。
        - OpenCV による 'q' キー検出で中断も可能。

    グローバル変数:
        - `camera_name`, `camera_id`: ダウンロード対象のカメラ情報。
        - `stop_event`: 処理終了を通知するためのスレッドイベント。
        - `trigger_event`: joinを許可するための同期イベント。
    """

    while True:
        print("現在の時刻:", current_time.strftime("%H:%M:%S"))

        #動画のダウンロード
        """return-> 成功:True 失敗:False"""
        result = download_video(camera_name, camera_id, current_time.strftime("%H:%M:%S"), video_time_seconds)
        if result == False :
            stop_event.set()
            trigger_event.set()  # joinを許可する
            break #ダウンロード処理中止

        # 30秒加算
        current_time += datetime.timedelta(seconds=video_time_seconds)
        if current_time == end_time:
            stop_event.set()
            trigger_event.set()  # joinを許可する
            break
        time.sleep(video_time_seconds) #加算分のsleep処理(30)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

"""負荷率解消後"""
# 動画を0.2秒ごとにフレームごとに処理する関数
def slice_video_to_images(video_filename, interval=0.2, max_frames=150):
    video_time_str = os.path.basename(video_filename).split('.')[0]
    video_time = datetime.datetime.strptime(video_time_str, '%H%M%S%f')

    # output_dir = video_time_str
    output_dir = os.path.join(CURRNT_DIR, video_time_str)
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_filename)
    if not cap.isOpened():
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        return

    frame_interval = int(fps * interval)  # 保存する間隔（フレーム単位）

    frame_idx = 0
    saved_count = 0
    current_video_time = video_time

    while saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            output_time = current_video_time + timedelta(seconds=saved_count * interval)
            timestamp_str = output_time.strftime("%H%M%S%f")[:-3]
            output_file = os.path.join(output_dir, f"{timestamp_str}.jpg")
            cv2.imwrite(output_file, frame)
            saved_count += 1

        frame_idx += 1

    cap.release()
    copy_jpg_files(output_dir)
    # with open("video.txt", "a") as file:
        # file.write(video_time_str + "\n")
    with open(os.path.join(CURRNT_DIR, "video.txt"), "a")as file:
        file.write(os.path.join(CURRNT_DIR, video_time_str) + "\n")
    run_executable()


def copy_jpg_files(video_filename):
    """スライスした画像を指定のフォルダに移動させる処理"""
    cc_images_path = os.path.join(CURRNT_DIR,"CCImageReader/images")
    # cc_images_path = "CCImageReader/images"
    # CCImageReaderに「images」フォルダが存在しない場合は作成
    if os.path.exists(cc_images_path):  # フォルダが存在するかチェック
        try:
            shutil.rmtree(cc_images_path)
        except FileNotFoundError:
            print(f"❌ 削除しようとしたフォルダ {cc_images_path} はすでに存在しません。処理をスキップします。")
            logging.warning(f"削除しようとしたフォルダ {cc_images_path} はすでに存在しません。処理をスキップします。")
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


# ==========================
# ✅ Watchdogのイベントクラス
# ==========================

class VideoListHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("video_list.txt"):
            # with open("video_list.txt", 'r') as f:
            with open(os.path.join(CURRNT_DIR, "video_list.txt"), 'r') as f:
                lines = f.readlines()

            if lines:
                video_filename = lines[0].strip()

                # 残りを再書き込み
                # with open("video_list.txt", 'w') as f:
                with open(os.path.join(CURRNT_DIR, "video_list.txt"), 'w') as f:
                    f.writelines(lines[1:])

                slice_video_to_images(video_filename)

# ==========================
# ✅ Watchdogの起動処理
# ==========================

def start_watchdog():
    """
    video_list.txt ファイルの変更を監視するファイル監視スレッドを起動する。

    処理内容:
        - `watchdog` ライブラリを使用して、指定ディレクトリ（CURRNT_DIR）の `video_list.txt` ファイルを監視。
        - `VideoListHandler` をイベントハンドラーとして使用し、ファイルが変更された場合に処理を実行。
        - `stop_event` がセットされるまで監視を継続。
        - キーボード割り込み（Ctrl+C）などが発生した場合でも監視を終了。
        - 処理終了後は `observer.join()` によってスレッドの終了を待機。

    グローバル変数:
        - CURRNT_DIR (str): 監視対象のカレントディレクトリ。
        - stop_event (threading.Event): 監視終了の指示に使用されるイベントフラグ。
    """
    path = f"./{CURRNT_DIR}"  # カレントディレクトリ
    event_handler = VideoListHandler()
    observer = Observer()
    observer.schedule(event_handler, path=path, recursive=False)
    observer.start()
    print("video_list.txt を監視中...")

    try:
        while not stop_event.is_set():
            time.sleep(1)
        else:
            stop_event.set()
            observer.stop()
    except KeyboardInterrupt:
        stop_event.set()
        observer.stop()
    observer.join()

def run_executable():
    """EXEファイルを実行する"""
    # 実行したいexeファイルのパスを指定
    exe_path = os.path.join(CURRNT_DIR,"CCImageReader/CCImageReader.exe")
    # exe_path = "CCImageReader/CCImageReader.exe"
    # # exeファイルを起動
    process = subprocess.Popen(exe_path)
    process.wait()
    print("CC解析完了しました。")

"""計測用"""
def monitor_usage(label, interval=0.5):
    cpu_list = []
    gpu_list = []
    timestamps = []
    stop_flag = threading.Event()
    proc = psutil.Process()

    def record():
        while not stop_flag.is_set():
            # cpu = psutil.cpu_percent(interval=None)
            cpu = proc.cpu_percent(interval=None)
            gpu = 0
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0].load * 100
            cpu_list.append(cpu)
            gpu_list.append(gpu)
            timestamps.append(time.time())
            time.sleep(interval)

    thread = threading.Thread(target=record)
    thread.start()

    def stop():
        stop_flag.set()
        thread.join()
        print(f"\n📊 {label} 使用率レポート")
        print(f"平均CPU: {sum(cpu_list)/len(cpu_list):.2f}%")
        print(f"最大CPU: {max(cpu_list):.2f}%")
        print(f"平均GPU: {sum(gpu_list)/len(gpu_list):.2f}%")
        print(f"最大GPU: {max(gpu_list):.2f}%")
        # グラフ出力などもここに追加可能

    return stop  # 呼び出すことで監視を終了

if __name__ == '__main__':
    CURRNT_DIR =  sys.argv[1]
    camera_id =  sys.argv[2]
    # CURRNT_DIR =  "1"
    # camera_id =  "192.168.1.146"

    # XMLファイルをパース
    tree = ET.parse('./application.xml')
    root = tree.getroot()

    # SK-VMS情報の取得
    ip = root.find('./SK-VMS/HOST').text
    port = root.find('./SK-VMS/PORT').text
    date = root.find('./SK-VMS/DATE').text
    start_time = root.find('./SK-VMS/START_TIME').text
    end_time = root.find('./SK-VMS/END_TIME').text
    video_time_seconds = int(root.find('./SK-VMS/DURATION').text)
    USER = root.find('./SK-VMS/USER').text
    PASSWD = root.find('./SK-VMS/PASSWD').text

    # URLとパラメータを設定
    # ip = "192.168.1.101"
    # port = "7001"
    # date = datetime.datetime.now().strftime("%Y-%m-%d")
    # #カメレオンコード有りのデータ（検証用）
    # date = "2025-01-28"
    # start_time = "13:48:50"
    # end_time = "13:50:20"
    # video_time_seconds = 30


    # ログの初期設定
    log_level_str = root.find('./LOG/LEVEL').text
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    log_file = root.find('./LOG/FILE').text

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # スレッド制御用フラグ
    stop_event = threading.Event()
    trigger_event = threading.Event()

    #ログインセッションの作成
    TOKEN = create_login_session()
    camera_name, camera_id = get_camera_conf(ip, port, camera_id)

    # 初期時刻を設定
    current_time = datetime.datetime.strptime(start_time, "%H:%M:%S")
    end_time = datetime.datetime.strptime(end_time, "%H:%M:%S")

    # メインスレッド：Webカメラからの録画を開始
    main_thread = threading.Thread(target=main_process, args=(current_time,end_time,video_time_seconds,))
    main_thread.start()
    # サブスレッド：動画リストを読み込み、動画ファイルを処理
    sub_thread = threading.Thread(target=start_watchdog)
    sub_thread.start()

    # 条件が満たされるまで待つ（joinの許可）
    trigger_event.wait()
    main_thread.join()
    sub_thread.join()
    print("スレッド終了！")

    # with open("video.txt", "a") as file:
    with open(os.path.join(CURRNT_DIR ,"video.txt"), "a") as file:
        file.write("stop" + "\n")


