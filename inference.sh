ARG1=$1
echo "Received argument: $ARG1"
ARG2=$2
echo "Received argument: $ARG2"
ARG3=$3
echo "Received argument: $ARG3"

FILE_PATH="id.txt"
FILE_PATH2="confirm.txt"

SLEEP_INTERVAL=5

# 現在のプロセスIDを取得し、ロックファイルに保存
# CURRENT_PID=$$
# LOCK_FILE="/tmp/inference_pid.lock"

# echo "現在のプロセスID: $CURRENT_PID"
# echo "$CURRENT_PID" >> "$LOCK_FILE" 

#2024.10.21 torisato
IMAGE_PATH=$(head -n 1 "${ARG1}/video.txt")
NEW_IMAGE_PATH=$(echo "$IMAGE_PATH" | sed "s|^${ARG1}/||")
# VIDEO_PATH="./gsam2/notebooks/videos/images"
OUTPUT_DIR="./${ARG1}/data/frames"
OUTPUT_DIR_GSAM2="./${ARG1}/data/gsam2_output"
#5FPS
DURATION=155 #秒数ではなく枚数
INTERVAL=50 #秒数ではなく枚数
FRAME_DURATION_COUNT=5 #(動画間のID継承処理用の画像重なり枚数の設定)
MOVIE_TIME=155
#10FPS
# DURATION=310 #秒数ではなく枚数
# INTERVAL=100 #秒数ではなく枚数
# FRAME_DURATION_COUNT=10 #(動画間のID継承処理用の画像重なり枚数の設定)
# OUTPUT_DIR内のフォルダを削除
rm -rf $OUTPUT_DIR/*
rm -rf $OUTPUT_DIR_GSAM2/*
# 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
#former_imagesフォルダから画像を移動させる 2024.10.25 torisato
#移動させたら、former_imagesフォルダを削除させる
python module/move_images.py \
    --frames_folder "$IMAGE_PATH" \
    --former_images_dir ./$ARG1/data/former_images
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for move_images.py: ${elapsed_time} seconds"
# 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
#2024.10.21 torisato
python module/split.py \
    --frames_folder "$IMAGE_PATH" \
    --output_base_dir "$OUTPUT_DIR" \
    --duration $DURATION \
    --interval $INTERVAL \
    --frame_count $FRAME_DURATION_COUNT \
    --former_images_dir ./$ARG1/data/former_images \
    --video $IMAGE_PATH
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for split.py: ${elapsed_time} seconds"
# # 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
# OUTPUT_DIR内のすべてのディレクトリに対して処理を行う
for dir in `ls $OUTPUT_DIR`
do
    python gsam2/gsam2_c-idv2.py \
        --input_folder $OUTPUT_DIR/$dir \
        --output_dir $OUTPUT_DIR_GSAM2/$dir \
        --device_id 0 \
        --camera_id $ARG1
    #2024.11.12 torisato
    break
done
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for gsam2_c-idv2.py: ${elapsed_time} seconds"
# 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
# $OUTPUT_DIR_GSAM2内のすべてのディレクトリに対して処理を行う
for dir in `ls $OUTPUT_DIR_GSAM2`
do
    echo $dir
    MASK_DATA_DIR="$OUTPUT_DIR_GSAM2/$dir/mask_data"
    JSON_DATA_DIR="$OUTPUT_DIR_GSAM2/$dir/json_data"
    # CSV_FILE_PATH="./data/results.csv"
    CSV_FILE_PATH="./${ARG1}/CCImageReader/result_$NEW_IMAGE_PATH/result.csv"
    echo $CSV_FILE_PATH
    CORRECTED_MASK_DIR="$OUTPUT_DIR_GSAM2/$dir/corrected_masks"
    CORRECTED_JSON_DIR="$OUTPUT_DIR_GSAM2/$dir/corrected_jsons"
    DEVICE="cuda"
    python module/correct_id.py \
        --mask_data_dir "$MASK_DATA_DIR" \
        --json_data_dir "$JSON_DATA_DIR" \
        --csv_file_path "$CSV_FILE_PATH" \
        --corrected_mask_dir "$CORRECTED_MASK_DIR" \
        --corrected_json_dir "$CORRECTED_JSON_DIR" \
        --device $DEVICE
    # python gsam2/create_correct_id_video.py \
    #     --input_folder ./data/frames/$dir \
    #     --mask_data_dir $OUTPUT_DIR_GSAM2/$dir/mask_data \
    #     --json_data_dir $OUTPUT_DIR_GSAM2/$dir/corrected_jsons \
    #     --result_dir $OUTPUT_DIR_GSAM2/$dir/result2 \
    #     --output_video_path $OUTPUT_DIR_GSAM2/$dir/output2.mp4 \
    #     --frame_rate 5
    #2024.11.12 torisato
    break
done
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for correct_id.py: ${elapsed_time} seconds"
# # 実行開始時間を記録
# start_time=$(date +"%H:%M:%S")

# # merge_segment.py実行前に前回のプロセスを確認
# if [ -f "$LOCK_FILE" ]; then
#   # ARG2が0でない場合にのみ処理を行う
#   if [ "$ARG2" -ne 0 ]; then
#     PREV_PID=$(sed -n "${ARG2}p" "$LOCK_FILE")
#     if [ "$PREV_PID" != "$CURRENT_PID" ]; then
#       echo "前回のinference.sh (PID=$PREV_PID) を確認中..."
#       # 前回のプロセスが終了していない場合は待機
#       while ps -p "$PREV_PID" > /dev/null; do
#         echo "前回のプロセス (PID=$PREV_PID) が実行中です。終了を待機します..."
#         sleep 5
#       done
#       echo "前回のプロセス (PID=$PREV_PID) が終了しました。"
#       # 待機が終了したら、このプロセスを最優先に設定
#       # echo "このプロセス (PID=$CURRENT_PID) を最優先に設定します..."
#       # sudo renice -n -20 -p "$CURRENT_PID"
#     fi
#   else
#     echo "ARG2は0なので確認処理はスキップします。"
#   fi
# fi

# #2024.10.25 torisato
python module/merge_segment.py \
    --base_dir $OUTPUT_DIR_GSAM2/ \
    --merge_dir ./$ARG1/data/merged_jsons \
    --former_merge_dir ./$ARG1/data/former_merged_jsons \
    --frame_count $FRAME_DURATION_COUNT \
    --former_images_dir ./$ARG1/data/former_images \
    --video $IMAGE_PATH \
    --duration $MOVIE_TIME
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for merge_segment.py: ${elapsed_time} seconds"
# 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
python module/merge_json_merge.py \
    --merge_dir ./$ARG1/data/merged_jsons \
    --former_merge_dir ./$ARG1/data/former_merged_jsons \
    --frame_count $FRAME_DURATION_COUNT \
    --camera_id $ARG1
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for merge_json_merge.py: ${elapsed_time} seconds"
# 実行開始時間を記録
start_time=$(date +"%H:%M:%S")
python module/create_db.py \
    --merge_dir ./$ARG1/data/merged_jsons \
    --duration $MOVIE_TIME \
    --frame_count $FRAME_DURATION_COUNT \
    --frames_folder $IMAGE_PATH \
    --camera_id $ARG1 \
    --confirm_text $FILE_PATH2
# 実行終了時間を記録
end_time=$(date +"%H:%M:%S")
# 実行時間を計算
start_sec=$(date -d "$start_time" +%s)
end_sec=$(date -d "$end_time" +%s)
elapsed_time=$((end_sec - start_sec))
echo "Elapsed Time for create_db.py: ${elapsed_time} seconds"

#VIDEO_TXTの一行目を削除する
sed -i '1d' "${ARG1}/video.txt"

python module/id_handover.py \
    --video $IMAGE_PATH \
    --merge_dir data/merged_jsons \
    --former_merge_dir data/former_merged_jsons \
    --frame_count $FRAME_DURATION_COUNT \
    --camera_id $ARG1 \
    --id_text $FILE_PATH \
    --last_camera_id $ARG3 \
    --confirm_text $FILE_PATH2

while true; do
    # 指定した値が見つかったらスクリプトを実行
    if grep -q "^$NEW_IMAGE_PATH$" "$FILE_PATH"; then
        echo "一致するデータ ($NEW_IMAGE_PATH) が見つかりました！スクリプトを実行します。"
        # 実行開始時間を記録
        start_time=$(date +"%H:%M:%S")
        #2024.10.21 torisato
        # python module/save_folder.py \
        #     --base_dir $OUTPUT_DIR_GSAM2/ \
        #     --merge_dir ./data/merged_jsons \
        #     --image_path $IMAGE_PATH
        #2024.10.22 torisato
        python create_movie.py \
            --image_path $NEW_IMAGE_PATH \
            --frame_count $FRAME_DURATION_COUNT \
            --merge_dir ./$ARG1/data/merged_jsons \
            --duration $MOVIE_TIME \
            --camera_id $ARG1 
        # 実行終了時間を記録
        end_time=$(date +"%H:%M:%S")
        # 実行時間を計算
        start_sec=$(date -d "$start_time" +%s)
        end_sec=$(date -d "$end_time" +%s)
        elapsed_time=$((end_sec - start_sec))
        echo "Elapsed Time for create_movie.py: ${elapsed_time} seconds"  
        break
    fi

    # # 試行回数を増加
    # ((attempt++))

    # # MAX_ATTEMPTS が 0 でない場合、試行回数をチェック
    # if [[ $MAX_ATTEMPTS -ne 0 && $attempt -ge $MAX_ATTEMPTS ]]; then
    #     echo "最大試行回数 ($MAX_ATTEMPTS) に達しました。スクリプトを終了します。"
    #     exit 1
    # fi

    # 指定時間待機
    echo "データが見つかりません。${SLEEP_INTERVAL} 秒後に再試行します..."
    sleep "$SLEEP_INTERVAL"
done


# # 実行開始時間を記録
# start_time=$(date +"%H:%M:%S")
#2024.11.21 torisato
# rm -r "./$IMAGE_PATH"
# rm -r "./CCImageReader/result_$IMAGE_PATH"
#2024.10.21 torisato
