date +"%H:%M:%S"

rm -rf process_locks

# ロックファイルのディレクトリを指定
LOCK_DIR="process_locks"

# ロックファイルのディレクトリを作成
mkdir -p "$LOCK_DIR"

# ロックファイルのパス
LOCK_FILE="$LOCK_DIR/get_video.lock"

# テキストファイルのパスを指定
FILE_PATH="id.txt"
FILE_PATH2="confirm.txt"

SOURCE_DIR="CCImageReader"

# 1. ファイルが存在する場合は削除
if [ -f "$FILE_PATH" ]; then
    echo "ファイルを削除します: $FILE_PATH"
    rm "$FILE_PATH"
else
    echo "ファイルは存在しません: $FILE_PATH"
fi

# 2. 新しい空のファイルを作成
echo "新しいファイルを作成します: $FILE_PATH"
touch "$FILE_PATH"

# 1. ファイルが存在する場合は削除
if [ -f "$FILE_PATH2" ]; then
    echo "ファイルを削除します: $FILE_PATH2"
    rm "$FILE_PATH2"
else
    echo "ファイルは存在しません: $FILE_PATH2"
fi

# 2. 新しい空のファイルを作成
echo "新しいファイルを作成します: $FILE_PATH2"
touch "$FILE_PATH2"

# いろあとDBからカメラの有効区分が有効なcamera_ipを取得する 2025.01.23 torisato
PYTHON_SCRIPT="module/utils3/Get_Camera_conf.py"
CAMERAS=()
while IFS= read -r line; do
    CAMERAS+=("$line")
done < <(python "$PYTHON_SCRIPT")

echo "${CAMERAS[@]}"

# CAMERAS=(
#     "1 192.168.1.146"
#     # "2 192.168.1.153"
# )

# 配列の最後の要素を取得
last_camera="${CAMERAS[-1]}"

# 左側の値（最初のフィールド）を取得
last_left_value=$(echo "$last_camera" | awk '{print $1}')

for CAMERA in "${CAMERAS[@]}"; do
    # カメラの1つ目の引数（インデックス部分）を取得
    INDEX=$(echo "$CAMERA" | awk '{print $1}')

    # 動的なパスを生成（インデックスに基づくディレクトリ）
    PREFIX="${INDEX}/"

    # 指定ファイルを削除
    # rm -rf "${PREFIX}video.txt"
    # rm -rf "${PREFIX}video_list.txt"
    rm -rf "${PREFIX}data/former_images"
    rm -rf "${PREFIX}data/former_merged_jsons"
    rm -rf "${PREFIX}data/merged_jsons"
    # rm -rf "${PREFIX}videos"
    rm -rf "${PREFIX}last_object_count.txt"

    #初回起動時、人物カウントを"0"から始める
    echo "0" > "${PREFIX}last_object_count.txt"

    FOLDERS=(
        "${INDEX}"
        "${PREFIX}data"
        "${PREFIX}data/frames"
        "${PREFIX}data/gsam2_output"
        "${PREFIX}CCImageReader"
    )

    # whileループと配列のインデックスを使う
    i=0
    while [ $i -lt ${#FOLDERS[@]} ]; do
        DIR="${FOLDERS[$i]}"
        if [ ! -d "$DIR" ]; then
            echo "フォルダが存在しません。作成します: $DIR"
            mkdir -p "$DIR"
            # `CCImageReader` がない場合はコピー処理を実行
            if [ "$DIR" == "${PREFIX}CCImageReader" ]; then
                echo "CCImageReader がないため、$SOURCE_DIR からコピーします..."
                cp -r "$SOURCE_DIR/" "$INDEX/"
                echo "コピー完了: $DIR"
            fi
        else
            echo "フォルダはすでに存在します: $DIR"
        fi

        i=$((i + 1))
    done
done

# for CAMERA in "${CAMERAS[@]}"; do
#     # 1つ目のコマンドをバックグラウンドで実行
#     python get_video_slice.py $CAMERA &
#     PID=$!  # プロセスIDを取得

#     # ロックファイルにPIDを追記
#     echo "$PID" >> "$LOCK_FILE"
#     echo "カメラ $CAMERA のプロセスを起動 (PID: $PID), ロックファイル: $LOCK_FILE"
# done

# # 30秒間のsleep
# sleep 30

for CAMERA in "${CAMERAS[@]}"; do
    (
        # カウントを初期化
        count=0

        while true; do

            # 2つ目のコマンドをバックグラウンドで実行
            sh inference.sh $CAMERA $last_left_value

            # カウントを1増加
            count=$((count + 1))

            EXE=$(head -n 1 "${PREFIX}video.txt")
            #stop_exe.py実行されたらShellプロセスを終了させる
            if [ "$EXE" = "stop" ]; then
                echo "終了"
                break
            fi

            echo $count
        done
    )&
done
