"""
exe_multi.py

このスクリプトは、複数のカメラに対して以下の処理を自動で実行するための管理ツールです。

主な機能:
1. カメラ構成の取得:
    - `Get_Camera_conf.py` を実行して、使用可能なカメラのリストを取得します。

2. 各カメラに必要なディレクトリやファイルの初期化:
    - 古いファイルやディレクトリを削除し、必要な構成を再作成します。
    - 各カメラ用の `CCImageReader` モジュールをコピーします。

3. 各カメラごとに映像取得プロセスを起動:
    - `get_video_watchdog.py` をカメラごとにバックグラウンドで起動します。
    - 起動されたプロセスIDはロックファイルに記録されます。

4. Inference処理の監視・起動:
    - `video.txt` に書き込まれた対象フォルダを監視し、指定があれば `inference_multi.py` を非同期で起動します。
    - 同時に動作できる推論プロセス数は `MAX_PROCESSES` で制限されます。
    - `ESC` キーが押された場合や `"stop"` 指示が書き込まれた場合、ループを中断します。

前提:
- 各カメラは「カメラID」と「IPアドレス」のペアとして認識されます。
- `CCImageReader` フォルダや `Get_Camera_conf.py` が事前に配置されている必要があります。
- Windows環境での動作を想定（`msvcrt` の使用により）。

使用方法:
    python exe_multi.py

推奨環境:
    - Python 3.8 以上
    - Windows OS
    - psutil, pathlib などの標準/外部モジュールがインストール済みであること

注意点:
    - `tmp` ディレクトリにプロセスロックファイルを作成するため、同時実行時には注意。
    - 推論プロセスや映像取得プロセスの異常終了を検知するウォッチドッグ処理は別途必要に応じて追加してください。
"""

import subprocess
from pathlib import Path
import tempfile
import os
import shutil
import time
import msvcrt
import psutil
import threading

ID_TXT_FILE_PATH = Path("id.txt")
CONFIRM_TXT_FILE_PATH = Path("confirm.txt")
SOURCE_DIR = Path("CCImageReader")
GET_CAMERA_CONF_SCRIPT = "module/utils3/Get_Camera_conf.py"
#tmpファイルを参照
tmp = tempfile.gettempdir()

# Reset main files
for file_path in [ID_TXT_FILE_PATH, CONFIRM_TXT_FILE_PATH]:
    if file_path.exists():
        print(f"Deleting existing file: {file_path}")
        file_path.unlink()
    file_path.touch()

# Get camera list by executing the Python script
CAMERAS = subprocess.check_output(["python", GET_CAMERA_CONF_SCRIPT], text=True).strip().splitlines()
print("Detected Cameras:", CAMERAS)

# Determine the last camera ID
last_camera_id = CAMERAS[-1].split()[0] if CAMERAS else None

# Prepare directories and files for each camera
for camera in CAMERAS:
    index, ip = camera.split()
    prefix = Path(index)
    subfolders = [
        prefix,
        prefix / "data",
        prefix / "data/frames",
        prefix / "data/gsam2_output",
        prefix / "CCImageReader"
    ]

    # Remove old files and folders
    for name in ["video.txt", "video_list.txt", "last_object_count.txt"]:
        file = prefix / name
        if file.exists():
            file.unlink()

    for name in ["data/former_images", "data/former_merged_jsons", "data/merged_jsons", "videos"]:
        dir_to_remove = prefix / name
        if dir_to_remove.exists():
            shutil.rmtree(dir_to_remove)

    # Create necessary folders
    for folder in subfolders:
        if folder.name == "CCImageReader":
            if not os.path.exists(folder):
                shutil.copytree(SOURCE_DIR, folder)
        else:
            folder.mkdir(exist_ok=True)

    # Reset last_object_count
    (prefix / "last_object_count.txt").write_text("0")
    (prefix / "gsam.txt").touch()

# Start get_video_slice.py for each camera
for camera in CAMERAS:
    proc = subprocess.Popen(["python", "get_video_watchdog.py", *camera.split()])
    index, ip = camera.split()

    lock_file = os.path.join(tmp, f"inference_pid.lock_{index}")
    with open(lock_file, "a") as f:
        f.write(f"{proc.pid}\n")
    print(f"Started get_video_slice.py for {index} (PID: {proc.pid})")

# Wait 30 seconds
time.sleep(30)

# Start inference process in background for each camera
MAX_PROCESSES = 3
for camera in CAMERAS:
    index, ip = camera.split()

    prefix = Path(index)
    video_txt_path = prefix / "video.txt"

    def monitor_camera(index, ip, prefix, video_txt_path):
        count = 0
        pids = []

        while True:
            if not video_txt_path.exists():
                print(f"{video_txt_path} does not exist. Waiting...")
                time.sleep(5)
                continue

            with video_txt_path.open("r") as f:
                lines = f.readlines()

            if not lines:
                print("video.txt is empty. Waiting...")
                time.sleep(5)
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'\x1b':  # ESCキーのコードは '\x1b'
                        print("ESCキーが押されました。終了します。")
                        break
                continue

            target_imgs_folder = lines[0].strip()
            if target_imgs_folder == "stop":
                print(f"Stopping camera {index} loop.")
                break

            if len(pids) >= MAX_PROCESSES:
                print(f"Max processes ({MAX_PROCESSES}) reached. Waiting...")
                while any(psutil.pid_exists(pid) for pid in pids):
                    time.sleep(5)

            proc = subprocess.Popen(["python", "inference_multi.py", index, ip, last_camera_id, target_imgs_folder, str(count)])
            pids.append(proc.pid)
            count += 1
            print(f"Started inference for {index}: PID={proc.pid}")

            # Remove the first line
            with video_txt_path.open("w") as f:
                f.writelines(lines[1:])

            time.sleep(30)

    threading.Thread(target=monitor_camera, args=(index, ip, prefix, video_txt_path)).start()
    time.sleep(3)

