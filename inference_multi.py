"""
inference_multi.py

このスクリプトは、指定されたカメラIDに対応する画像フォルダに対して、人物検出・ID補正・セグメンテーション・DB登録・動画生成処理を一連で実行します。

主な機能:
---------
1. move_images.pyの実行：
    - 対象の画像を一時フォルダに移動し、以前の画像と重複を回避。

2. split.pyの実行：
    - 画像を指定されたインターバルとフレーム数に分割し、処理対象に準備。

3. gsam2_c-idv2.pyの実行：
    - 指定された画像に対して、SAM2を用いたセグメンテーションを実行。
    - 処理は一度に一セットの画像フォルダに対して行う。

4. correct_id.pyの実行：
    - セグメンテーション結果に基づき、ID情報の補正を行う。
    - カメレオンコードとの紐づけ処理を行う。

5. merge_segment.py / merge_json_merge.pyの実行：
    - セグメントごとのJSONファイルをマージし、処理単位ごとに統合。

6. create_db.pyの実行：
    - マージ済みデータからDB挿入に適した形式で情報を生成。

7. id_handover.pyの実行：
    - 複数カメラ間でIDの引き継ぎ推定を行い、個体追跡の整合性を確保。

8. create_movie.pyの実行（条件を満たした場合）：
    - 処理が完了した対象に対し、結果動画を生成。

9. post_processing.pyの実行：
    - フォルダ整理および処理結果の保存を行う。

実行方法:
----------
本スクリプトは以下の引数を必要とします。

    python inference_multi.py <PREFIX> <CAMERA_IP> <LAST_CAMERA_ID> <TARGET_IMGS_FOLDER> <EXE_COUNT>

引数説明:
----------
- PREFIX: カメラID（文字列）
- CAMERA_IP: 対象カメラのIPアドレス
- LAST_CAMERA_ID: カメラ構成中の最大ID（推定用に必要）
- TARGET_IMGS_FOLDER: 処理対象の画像フォルダ名
- EXE_COUNT: 実行カウント（複数プロセス間の同期に使用）

注意事項:
----------
- Windows環境での実行を想定（`msvcrt` モジュールを使用）。
- 複数プロセスとのロックファイルによる同期により、実行順序を制御。
- 実行に必要な補助スクリプト（`move_images.py` 等）がすべてモジュールとして `module/` 配下に存在している必要があります。

"""

import os
import sys
import shutil
import time
import subprocess
from datetime import datetime
import tempfile

def timed_run(label, func):
    print(f"==== {label} ====")
    start_time = time.time()
    func()
    end_time = time.time()
    print(f"Elapsed Time for {label}: {int(end_time - start_time)} seconds\n")

def run_py(script, **kwargs):
    args = ["python", script] + [f"--{k}" if v is True else f"--{k} {v}" for k, v in kwargs.items() if v is not None]
    args_flat = []
    for a in args:
        args_flat.extend(a.split())
    subprocess.run(args_flat)

if __name__ == "__main__":
    #フォルダ名
    PREFIX = sys.argv[1]
    #カメラIP
    CAMERA_IP = sys.argv[2]
    #カメラ配列の最終レコードのカメラID
    LAST_CAMERA_ID = sys.argv[3]
    #推論対象の画像フォルダ
    TARGET_IMGS_FOLDER = sys.argv[4]
    #実行回数
    EXE_COUNT = int(sys.argv[5])

    # print("PREFIX:",PREFIX)
    # print("CAMERA_IP:",CAMERA_IP)
    # print("LAST_CAMERA_ID:",LAST_CAMERA_ID)
    # print("TARGET_IMGS_FOLDER:",TARGET_IMGS_FOLDER)
    # print("EXE_COUNT:",EXE_COUNT)

    #tmpファイルを参照
    tmp = tempfile.gettempdir()

    lock_file = os.path.join(tmp, f"inference_pid.lock_{PREFIX}")
    current_pid = os.getpid()
    with open(lock_file, "a") as f:
        f.write(f"{current_pid}\n")

    # NEW_IMAGE_PATH = TARGET_IMGS_FOLDER.replace(f"{PREFIX}/", "").replace("/", os.sep)
    NEW_IMAGE_PATH = os.path.basename(TARGET_IMGS_FOLDER)
    OUTPUT_DIR = os.path.join(PREFIX, "data", "frames", NEW_IMAGE_PATH)
    OUTPUT_DIR_GSAM2 = os.path.join(PREFIX, "data", "gsam2_output", NEW_IMAGE_PATH)

    DURATION = 155
    INTERVAL = 50
    FRAME_DURATION_COUNT = 5
    MOVIE_TIME = 155

    FILE_PATH = "id.txt"
    FILE_PATH2 = "confirm.txt"
    FILE_PATH3 = f"{PREFIX}/gsam.txt"

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR_GSAM2, ignore_errors=True)

    def move_images():
        run_py("module/move_images.py", frames_folder=TARGET_IMGS_FOLDER, former_images_dir=f"./{PREFIX}/data/former_images")

    def split_images():
        run_py("module/split.py",
            frames_folder=TARGET_IMGS_FOLDER,
            output_base_dir=OUTPUT_DIR,
            duration=DURATION,
            interval=INTERVAL,
            frame_count=FRAME_DURATION_COUNT,
            former_images_dir=f"./{PREFIX}/data/former_images",
            video=TARGET_IMGS_FOLDER)

    def gsam2_run():
        for dir_name in os.listdir(OUTPUT_DIR):
            run_py("gsam2/gsam2_c-idv2.py",
                input_folder=os.path.join(OUTPUT_DIR, dir_name),
                output_dir=os.path.join(OUTPUT_DIR_GSAM2, dir_name),
                device_id=0,
                camera_id=PREFIX)
            break

    def corrected_id():
        for dir_name in os.listdir(OUTPUT_DIR_GSAM2):
            base_path = os.path.join(OUTPUT_DIR_GSAM2, dir_name)
            run_py("module/correct_id.py",
                mask_data_dir=os.path.join(base_path, "mask_data"),
                json_data_dir=os.path.join(base_path, "json_data"),
                csv_file_path=f"./{PREFIX}/CCImageReader/result_{NEW_IMAGE_PATH}/result.csv",
                corrected_mask_dir=os.path.join(base_path, "corrected_masks"),
                corrected_json_dir=os.path.join(base_path, "corrected_jsons"),
                device="cuda")
            break

    def merge_segment():
        run_py("module/merge_segment.py",
        base_dir=OUTPUT_DIR_GSAM2,
        merge_dir=f"./{PREFIX}/data/merged_jsons",
        former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
        frame_count=FRAME_DURATION_COUNT,
        former_images_dir=f"./{PREFIX}/data/former_images",
        video=TARGET_IMGS_FOLDER,
        duration=MOVIE_TIME)

    def merge_json_merge():
        run_py("module/merge_json_merge.py",
        merge_dir=f"./{PREFIX}/data/merged_jsons",
        former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
        frame_count=FRAME_DURATION_COUNT,
        camera_id=PREFIX)

    def create_db():
        run_py("module/create_db.py",
        merge_dir=f"./{PREFIX}/data/merged_jsons",
        duration=MOVIE_TIME,
        frame_count=FRAME_DURATION_COUNT,
        frames_folder=TARGET_IMGS_FOLDER,
        camera_id=PREFIX,
        confirm_text=FILE_PATH2)

    def id_handover():
        run_py("module/id_handover.py",
        video=TARGET_IMGS_FOLDER,
        merge_dir=f"./{PREFIX}/data/merged_jsons",
        former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
        frame_count=FRAME_DURATION_COUNT,
        camera_id=PREFIX,
        id_text=FILE_PATH,
        last_camera_id=LAST_CAMERA_ID,
        confirm_text=FILE_PATH2)

    def create_movie():
        while True:
            with open(FILE_PATH) as f:
                if NEW_IMAGE_PATH in f.read():
                    run_py("create_movie.py",
                        image_path=NEW_IMAGE_PATH,
                        frame_count=FRAME_DURATION_COUNT,
                        merge_dir=f"./{PREFIX}/data/merged_jsons",
                        duration=MOVIE_TIME,
                        camera_id=PREFIX)
                    break
            print("Waiting for video.txt update...")
            time.sleep(5)

    def post_processing():
        #処理が終わった後に、画像フォルダとCC情報のフォルダを移動させる 2025.04.22 torisato
        # post_processing.py
        run_py("post_processing.py",
            save_folder=f"./{PREFIX}",
            image_path=TARGET_IMGS_FOLDER,
            csv_file_path=f"./{PREFIX}/CCImageReader/result_{NEW_IMAGE_PATH}"
        )


    timed_run(f"{EXE_COUNT}回目 move_images.py", move_images)

    timed_run(f"{EXE_COUNT}回目 split.py", split_images)

    if EXE_COUNT != 0:
        while True:
            with open(FILE_PATH3) as f:
                gsam = f.readline().strip()
            if gsam != str(EXE_COUNT):
                time.sleep(5)
            else:
                break

    # for dir_name in os.listdir(OUTPUT_DIR):
    #     run_py("gsam2/gsam2_c-idv2.py",
    #         input_folder=os.path.join(OUTPUT_DIR, dir_name),
    #         output_dir=os.path.join(OUTPUT_DIR_GSAM2, dir_name),
    #         device_id=0,
    #         camera_id=PREFIX)
    #     break

    timed_run(f"{EXE_COUNT}回目 gsam2_c-idv2.py", gsam2_run)

    with open(FILE_PATH3, "w") as f:
        f.write(str(EXE_COUNT + 1))

    # for dir_name in os.listdir(OUTPUT_DIR_GSAM2):
    #     base_path = os.path.join(OUTPUT_DIR_GSAM2, dir_name)
    #     run_py("module/correct_id.py",
    #         mask_data_dir=os.path.join(base_path, "mask_data"),
    #         json_data_dir=os.path.join(base_path, "json_data"),
    #         csv_file_path=f"./{PREFIX}/CCImageReader/result_{NEW_IMAGE_PATH}/result.csv",
    #         corrected_mask_dir=os.path.join(base_path, "corrected_masks"),
    #         corrected_json_dir=os.path.join(base_path, "corrected_jsons"),
    #         device="cuda")
    #     break

    timed_run(f"{EXE_COUNT}回目 corrected_id.py", corrected_id)

    if os.path.exists(lock_file) and EXE_COUNT != 0:
        with open(lock_file) as f:
            lines = f.readlines()
        prev_pid = lines[EXE_COUNT - 1].strip()
        if prev_pid != str(current_pid):
            while subprocess.call(["ps", "-p", prev_pid], stdout=subprocess.DEVNULL) == 0:
                print(f"Waiting for PID {prev_pid} to finish...")
                time.sleep(5)

    # run_py("module/merge_segment.py",
    #     base_dir=OUTPUT_DIR_GSAM2,
    #     merge_dir=f"./{PREFIX}/data/merged_jsons",
    #     former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
    #     frame_count=FRAME_DURATION_COUNT,
    #     former_images_dir=f"./{PREFIX}/data/former_images",
    #     video=TARGET_IMGS_FOLDER,
    #     duration=MOVIE_TIME)

    timed_run(f"{EXE_COUNT}回目 merge_segment.py", merge_segment)

    # run_py("module/merge_json_merge.py",
    #     merge_dir=f"./{PREFIX}/data/merged_jsons",
    #     former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
    #     frame_count=FRAME_DURATION_COUNT,
    #     camera_id=PREFIX)

    timed_run(f"{EXE_COUNT}回目 merge_json_merge.py", merge_json_merge)

    # run_py("module/create_db.py",
    #     merge_dir=f"./{PREFIX}/data/merged_jsons",
    #     duration=MOVIE_TIME,
    #     frame_count=FRAME_DURATION_COUNT,
    #     frames_folder=TARGET_IMGS_FOLDER,
    #     camera_id=PREFIX,
    #     confirm_text=FILE_PATH2)

    timed_run(f"{EXE_COUNT}回目 create_db", create_db)

    # run_py("module/id_handover.py",
    #     video=TARGET_IMGS_FOLDER,
    #     merge_dir=f"./{PREFIX}/data/merged_jsons",
    #     former_merge_dir=f"./{PREFIX}/data/former_merged_jsons",
    #     frame_count=FRAME_DURATION_COUNT,
    #     camera_id=PREFIX,
    #     id_text=FILE_PATH,
    #     last_camera_id=LAST_CAMERA_ID,
    #     confirm_text=FILE_PATH2)

    timed_run(f"{EXE_COUNT}回目 id_handover.py", id_handover)

    # while True:
    #     with open(FILE_PATH) as f:
    #         if NEW_IMAGE_PATH in f.read():
    #             run_py("create_movie.py",
    #                 image_path=NEW_IMAGE_PATH,
    #                 frame_count=FRAME_DURATION_COUNT,
    #                 merge_dir=f"./{PREFIX}/data/merged_jsons",
    #                 duration=MOVIE_TIME,
    #                 camera_id=PREFIX)
    #             break
    #     print("Waiting for video.txt update...")
    #     time.sleep(5)

    # run_py("create_movie.py",
    #     image_path=NEW_IMAGE_PATH,
    #     frame_count=FRAME_DURATION_COUNT,
    #     merge_dir=f"./{PREFIX}/data/merged_jsons",
    #     duration=MOVIE_TIME,
    #     camera_id=PREFIX)

    timed_run(f"{EXE_COUNT}回目 create_movie.py", create_movie)

    # #処理が終わった後に、画像フォルダとCC情報のフォルダを移動させる 2025.04.22 torisato
    # # post_processing.py
    # run_py("post_processing.py",
    #     save_folder=f"./{PREFIX}",
    #     image_path=TARGET_IMGS_FOLDER,
    #     csv_file_path=f"./{PREFIX}/CCImageReader/result_{NEW_IMAGE_PATH}"
    # )

    timed_run(f"{EXE_COUNT}回目 post_processing.py", post_processing)
