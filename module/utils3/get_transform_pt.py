import numpy as np
import cv2
from utils3.Camera_conf_utils import bbox_list, x_change, y_change
from shapely.geometry import Polygon, LineString

def to_two_dimension(trans_settings):
    """
    射影変換（Perspective Transform）を行うための行列を生成する関数。

    カメラ視点で撮影された画像の四隅の座標と、それを変換した後の平面上の座標を元に、
    OpenCV の `cv2.getPerspectiveTransform` を使って 3x3 の変換行列を生成します。

    Args:
        trans_settings (dict): 以下の2つのキーを持つ辞書。
            - 'area_size' (list of list): 写真上の四隅の座標（[top_left, top_right, bottom_right, bottom_left]）。
            - 'transform_size' (list of list): 変換後に対応する座標（[t_left, t_right, b_right, b_left]）。

    Returns:
        numpy.ndarray: 3x3 の射影変換行列（float32型）。
    """
    # 基準とする四隅(カメラ視点)の写真上の座標（px)
    top_left, top_right, bottom_right, bottom_left = trans_settings['area_size']
    # print(top_left, top_right, bottom_right, bottom_left)
    pts1 = np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)
    # 変換後の画像サイズ
    t_left, t_right, b_right, b_left = trans_settings['transform_size']
    pts2 = np.array([t_left, t_right, b_right, b_left], dtype=np.float32)
    # 射影行列の取得
    M = cv2.getPerspectiveTransform(pts1, pts2)
    np.set_printoptions(precision=5, suppress=True)
    # print (M)
    return M

def transform_pt(pt, M):
    '''座標ptを変換行列Mで変換'''
    if isinstance(pt, (list, tuple)):
        pt = np.array(pt, dtype=np.float32)
    assert pt.ndim == 1 and pt.shape[0] == 2 # 1次元のx,y2要素を前提
    pt = np.append(pt, 1.0)
    # print(f'追加前：{pt}')
    pt = np.dot(M, pt) # 射影行列で座標変換
    # print(f'{pt}')
    pt = pt / pt[2] # 第3要素が１となるよう按分
    # print(f'{pt}')
    pt = pt[:2] # x,y要素
    # print(f'{pt}')
    return tuple(pt.astype(int).tolist()) # 後でdrawMarkerで使うのでtupleにしておく


def get_corrected_feet_coordinates(bbox,result,labels,instance_id,obstacle_list,image,output_folder2,camera_id):
    """
    障害物に隠れた際に画像上の本来の足元の座標を取得する関数

    Args:
    bbox (list): [bboxの左上のX, bboxの左上のY, bboxの右下のX, bboxの右下のY]

    Returns:
    tuple: 本来の足元のX座標とY座標
    """

    # BODY_RATIO = 0.25
    estimate_flg=False

    # # bboxの比率を計算
    # bbox_ratio = calc_bbox_ratio(bbox)
    # print(output_folder2)
    # print(bbox_list[str(camera_id)][0])
    front_height,amount_change_y=y_change(bbox_list[str(camera_id)][0],bbox_list[str(camera_id)][1])
    amount_change_x,big_x=x_change(bbox_list[str(camera_id)][2],bbox_list[str(camera_id)][3])

    # bboxの中心のX座標を計算
    center_x = bbox[0] + ((bbox[2]-bbox[0]) / 2)
    estimate_height=int((front_height+((bbox_list[str(camera_id)][0][1]-bbox[1])*-amount_change_y)+(abs((big_x-bbox[0]))*-amount_change_x))/1)
    estimate_Y=bbox[1]+estimate_height
    # center_x = (bbox[0] + bbox[2]) / 2
    # bboxの底のY座標を取得
    if result:
        # if estimate_height*0.85 > bbox[3]:
        #     bottom_y=estimate_Y
        # else:
        bottom_y = bbox[3]
    else:
        # estimate_height=front_bbox[3]+(front_bbox[1]-bbox[1])*-amount_change_y+abs((big_x-bbox[0]))*-amount_change_x
        real_height=bbox[3]-bbox[1]
        # print(estimate_height,real_height)
        person_flg=False
        obstacle_flg=False

        if estimate_height < 0:
            print(f"マイナス{instance_id}")

        if estimate_height * 0.9 < real_height < estimate_height * 1.1:
            bottom_y=bbox[3]
        else:
            for _, label_info in labels.items():
                if label_info['instance_id'] != instance_id:
                    # 範囲を定義
                    range1_start, range1_end = bbox[0], bbox[2]  # 比較する範囲
                    range2_start, range2_end = label_info['x1'], label_info['x2']  # 基準となる範囲

                    # 重なり部分を計算
                    overlap_start = max(range1_start, range2_start)
                    overlap_end = min(range1_end, range2_end)

                    # 重なりの長さを計算
                    overlap_length = max(0, overlap_end - overlap_start)

                    # 範囲1の長さ
                    range1_length = range1_end - range1_start

                    # 含まれている割合を計算
                    if range1_length > 0:  # 範囲1の長さが0でない場合
                        inclusion_ratio = overlap_length / range1_length
                        if inclusion_ratio > 0.4:
                            # 範囲を定義
                            range1_start, range1_end = bbox[1], bbox[3]  # 比較する範囲
                            range2_start, range2_end = label_info['y1'], label_info['y2']  # 基準となる範囲

                            # 重なり部分を計算
                            overlap_start = max(range1_start, range2_start)
                            overlap_end = min(range1_end, range2_end)

                            # 重なりの長さを計算
                            overlap_length = max(0, overlap_end - overlap_start)

                            # 範囲1の長さ
                            range1_length = range1_end - range1_start

                            # 含まれている割合を計算
                            if range1_length > 0:  # 範囲1の長さが0でない場合
                                inclusion_ratio = overlap_length / range1_length
                                if inclusion_ratio > 0.1:
                                    if range2_start <= bbox[3] <= range2_end:
                                        person_flg=True
                                        break
            if person_flg==False:
                for obstacle in obstacle_list:
                    polygon = Polygon(obstacle)
                    # 固定するy座標とxの範囲を指定
                    fixed_y = bbox[3]  # 固定するy座標
                    x_min, x_max = bbox[0], bbox[2]  # x軸の範囲 [1, 100]

                    # y=fixed_yの水平ラインを作成
                    horizontal_line = LineString([(x_min, fixed_y), (x_max, fixed_y)])

                    # 四角形と水平ラインの交差部分を計算
                    intersection = polygon.intersection(horizontal_line)

                    # 結果の処理
                    if not intersection.is_empty:
                        if intersection.geom_type == "MultiLineString":
                            # 複数の交差部分がある場合
                            total_length = sum(line.length for line in intersection.geoms)
                        else:
                            # 1つの交差部分がある場合
                            total_length = intersection.length

                        # x軸の全体の長さと交差部分の割合を計算
                        total_x_length = x_max - x_min
                        ratio = total_length / total_x_length

                        if ratio > 0.7:
                            obstacle_flg=True
                            break

                if obstacle_flg:
                    # print("障害物あり")
                    bottom_y=estimate_Y
                    estimate_flg=True
                else:
                    if 1075 <= bbox[3] <= 1080:
                        bottom_y=estimate_Y
                        estimate_flg=True
                    else:
                        bottom_y=bbox[3]
            else:
                # print("人前にいる")
                bottom_y=estimate_Y
                estimate_flg=True
    # print(output_folder2,instance_id,center_x, bottom_y,estimate_Y,estimate_height)
    # image = cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[2], bottom_y), (0, 255, 255), 2)
    # cv2.imwrite(output_folder2, image)
    return (center_x, bottom_y),estimate_flg,amount_change_x,amount_change_y