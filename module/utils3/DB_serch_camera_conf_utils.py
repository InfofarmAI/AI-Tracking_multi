import mysql.connector
import xml.etree.ElementTree as ET

# XMLファイルをパース
tree = ET.parse('./application.xml')
root = tree.getroot()

# DB情報の取得
host = root.find('./DB/HOST').text
port = root.find('./DB/PORT').text
db = root.find('./DB/NAME').text
user = root.find('./DB/USER').text
passwd = root.find('./DB/PASSWD').text

# MySQLの接続情報を設定
# # host = 'localhost'
# host = '192.168.1.101' #MySQL環境のある
# port = '3306'
# db = 'cclog_db'
# user = 'root'
# passwd = 'CCrootpass'

config = {
    'user': user,
    'password': passwd,
    'host': host,  # ホスト名
    'database': db,
    'port': port  # ポート番号
}
async_config = {
    'user': user,
    'password': passwd,
    'host': host,  # ホスト名
    'db': db,
    'port': int(port)  # ポート番号
}

def login_user(login_id, passwd):
    """ログイン情報の認証確認"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT password, last_name, first_name FROM cclog_db.users WHERE login_id = %s;"
        db.execute(query, [login_id]) # 有効な区分のカメラのみ取得
        records = db.fetchall()

        return records
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def fetch_camera_info():
    """カメラ有効区分が'１'のデータを取得する"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor(dictionary=True)
    try:
        query = "SELECT id, code, ip_address FROM cameras WHERE status = %s;"
        db.execute(query, ['1']) # 有効な区分のカメラのみ取得
        records = db.fetchall()

        return records
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()


def get_ccid_name():
    """ccidとidに紐づくnameを取得"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT wk_cc.chameleon_code, wk.name FROM cclog_db.worker_chameleon_codes as wk_cc left join cclog_db.workers as wk on wk_cc.worker_id = wk.id;"
        db.execute(query) # 有効な区分のカメラのみ取得
        records = db.fetchall()

        return records
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def select_camera_data(camera_ip):
    """カメラ情報を取得"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT camera_matrix, dist, new_camera_matrix FROM cclog_db.camera_data WHERE camera_id = %s;"
        db.execute(query, [camera_ip])
        return db.fetchall()
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def select_camera_area(camera_ip):
    """エリア情報を取得"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT area_size FROM cclog_db.camera_data WHERE camera_id = %s;"
        db.execute(query, [camera_ip])
        return db.fetchall()
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()

def select_camera_transform_size(camera_ip):
    """transform_size情報を取得"""
    connection = mysql.connector.connect(**config)
    db = connection.cursor()
    try:
        query = "SELECT transform_size FROM cclog_db.camera_data WHERE camera_id = %s;"
        db.execute(query, [camera_ip])
        return db.fetchall()
    except mysql.connector.Error as e:
        print(e)
    finally:
        db.close()
        connection.close()






