"""
split.py

このスクリプトは、指定されたフレーム画像のフォルダから一定間隔で画像を抽出し、
複数のセグメントに分割して保存します。さらに、最後の N 枚の画像を次の動画処理に
引き継ぐための一時保存ディレクトリにコピーします。

主な機能:
- 動画フレームを間隔付きでセグメントに分割して保存
- 最終フレームの一部を次の処理用にコピー
- ソートされた画像ファイルに対して、番号順で正確なセグメント処理を実施

使用例:
python script.py --frames_folder ./frames --frame_count 5 --former_images_dir ./former --video ./video1 --duration 100 --interval 50
"""


import os
import argparse
import math
import shutil  # ファイルをコピーするために使用

class VideoFrameExtractor:
    def __init__(self, frames_folder, output_base_dir='output_frames', duration=100, interval=50):
        self.frames_folder = frames_folder
        self.output_base_dir = output_base_dir
        self.duration = duration  # セグメントの長さ（フレーム数）
        self.interval = interval  # インターバル（フレーム数）

        # 出力フォルダの作成
        if not os.path.exists(self.output_base_dir):
            os.makedirs(self.output_base_dir, exist_ok=True)

        # フレームファイルのリストを取得し、ファイル名の数字部分でソート
        self.frame_files = os.listdir(self.frames_folder)
        self.frame_files = [f for f in self.frame_files if f.lower().endswith(('.jpg', '.png', '.jpeg'))]

        # ファイル名からタイムスタンプを抽出
        self.timestamps = []
        self.frame_dict = {}
        for filename in self.frame_files:
            name, ext = os.path.splitext(filename)
            try:
                timestamp = int(name)
                self.timestamps.append(timestamp)
                self.frame_dict[timestamp] = filename
            except ValueError:
                pass  # 数値でないファイル名はスキップ

        # タイムスタンプをソート
        self.timestamps.sort()

        # フレームが存在するか確認
        if not self.timestamps:
            raise ValueError("指定されたフォルダに有効なフレームファイルがありません。")

        # 総フレーム数を取得
        self.total_frames = len(self.timestamps)
        #print(self.total_frames)

        # セグメント数を計算
        self.num_segments = math.ceil((self.total_frames - self.duration) / self.interval) + 1

    def extract_frames(self):
        # 通常のセグメントを作成
        for i in range(self.num_segments):
            #print(self.num_segments)
            start_index = i * self.interval
            end_index = start_index + self.duration

            # フレーム数を超えないように調整
            if end_index > self.total_frames:
                end_index = self.total_frames

            # 開始インデックスが総フレーム数を超える場合は処理を終了
            if start_index >= self.total_frames:
                break

            segment_output_dir = os.path.join(self.output_base_dir, f'segment_{i}')

            # セグメントのフレームを抽出
            self.extract_frames_segment(start_index, end_index, segment_output_dir)

        # 最後のセグメントを作成（最後のフレームから前に戻ってduration枚分）
        last_segment_index = self.num_segments
        segment_output_dir = os.path.join(self.output_base_dir, f'segment_{last_segment_index}')

        end_index = self.total_frames
        start_index = max(0, end_index - self.duration)

        # セグメントのフレームを抽出
        self.extract_frames_segment(start_index, end_index, segment_output_dir)

    def extract_frames_segment(self, start_index, end_index, segment_output_dir):
        if not os.path.exists(segment_output_dir):
            os.makedirs(segment_output_dir, exist_ok=True)

        # 該当するフレームをセグメントフォルダにコピー
        for idx in range(start_index, end_index):
            timestamp = self.timestamps[idx]
            filename = self.frame_dict[timestamp]
            src_path = os.path.join(self.frames_folder, filename)
            dst_path = os.path.join(segment_output_dir, filename)
            if os.path.exists(src_path):
                shutil.copy(src_path, dst_path)
            else:
                print(f"警告: フレーム {filename} が存在しません。")

def copy_images(former_images_file,video_file,frame_count):

        # コピー先フォルダが存在しない場合は作成
    os.makedirs(former_images_file, exist_ok=True)

    # フォルダ内のファイル一覧を取得し、ソート
    files = sorted(os.listdir(video_file))

    # ファイルが5つ未満の場合、全てのファイルをコピー
    num_files_to_copy = min(frame_count, len(files))

    # 下から5つのファイルを取得
    files_to_copy = files[-num_files_to_copy:]

    # ファイルをコピー
    for file_name in files_to_copy:
        source_file = os.path.join(video_file, file_name)
        destination_file = os.path.join(former_images_file, file_name)
        shutil.copy(source_file, destination_file)

# メイン部分
if __name__ == '__main__':
    # コマンドライン引数をパース
    parser = argparse.ArgumentParser(description='Video Frame Extractor')
    parser.add_argument('--frames_folder', type=str, required=True, help='入力フレームが格納されたフォルダを指定')
    parser.add_argument('--output_base_dir', type=str, default='output_frames', help='出力フォルダのベースパス')
    parser.add_argument('--duration', type=int, default=100, help='セグメントの長さ（フレーム数）')
    parser.add_argument('--interval', type=int, default=50, help='インターバル（フレーム数）')
    parser.add_argument('--frame_count', type=int, required=True, help='動画間の重ねるフレームの数')
    parser.add_argument('--former_images_dir', type=str, required=True, help='動画間の画像を保存するディレクトリのパス')
    parser.add_argument('--video', type=str, required=True, help='現在処理が行われいるフォルダが記載してあるテキスト')
    args = parser.parse_args()

    extractor = VideoFrameExtractor(
        frames_folder=args.frames_folder,
        output_base_dir=args.output_base_dir,
        duration=args.duration,
        interval=args.interval
    )
    extractor.extract_frames()

    copy_images(args.former_images_dir,args.video,args.frame_count)

