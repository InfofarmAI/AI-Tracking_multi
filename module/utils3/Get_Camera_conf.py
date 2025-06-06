from DB_serch_camera_conf_utils import fetch_camera_info

"""
いろあとDBからカメラの有効区分が有効なcamera_ipを取得する
Return: ID, camera_ip
"""

cameras = []

records = fetch_camera_info()

for record in records:
    id = record['id']
    camera_ip = record['ip_address']
    print(f'{id} {camera_ip} ')