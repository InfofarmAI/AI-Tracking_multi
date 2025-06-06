import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 接続情報
base_url = "https://192.168.1.101:7001"
username = "admin"
password = "info1881"

# ログインしてセッショントークンを取得
def login():
    session = requests.Session()
    url = f"{base_url}/rest/v3/login/sessions"
    payload = {"username": username, "password": password, "setCookie": True}
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    res = session.post(url, json=payload, headers=headers, verify=False)
    if res.ok:
        token = res.json().get("token")
        session.cookies.set("csrf_token", token)
        print("✅ ログイン成功")
        return session, token
    else:
        raise Exception(f"❌ ログイン失敗: {res.status_code} {res.text}")

# 全ログインセッションを取得
def get_all_sessions(session, token):
    url = f"{base_url}/rest/v3/login/sessions"
    headers = {
        "accept": "application/json",
        "x-runtime-guid": token
    }
    res = session.get(url, headers=headers, verify=False)
    if res.ok:
        return res.json()
    else:
        raise Exception(f"❌ セッション一覧取得失敗: {res.status_code} {res.text}")

# セッション削除
def delete_session(session, token, target_token):
    url = f"{base_url}/rest/v3/login/sessions/{target_token}"
    headers = {
        "accept": "*/*",
        "x-runtime-guid": token
    }
    res = session.delete(url, headers=headers, verify=False)
    if res.ok:
        print(f"✅ セッション削除成功: {target_token}")
    else:
        print(f"❌ セッション削除失敗: {target_token} {res.status_code} {res.text}")

# 実行処理
session, token = login()
sessions = get_all_sessions(session, token)

for entry in sessions:
    target_token = entry.get("token")
    if target_token and target_token != token:
        delete_session(session, token, target_token)

print("🎉 全セッション削除完了（自分以外）")
