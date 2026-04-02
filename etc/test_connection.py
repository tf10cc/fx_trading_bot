import os
from dotenv import load_dotenv
import requests

# .env ファイル読み込み
load_dotenv()

# 環境変数取得
api_token = os.getenv('OANDA_DEMO_API_TOKEN')
account_id = os.getenv('OANDA_DEMO_ACCOUNT_ID')

print("=== OANDA API 接続テスト ===")
print(f"Account ID: {account_id}")

# APIエンドポイント
url = f"https://api-fxpractice.oanda.com/v3/accounts/{account_id}"

# ヘッダー設定
headers = {
    "Authorization": f"Bearer {api_token}"
}

# リクエスト送信
try:
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        print("✅ 接続成功！")
        data = response.json()
        print(f"残高: {data['account']['balance']} USD")
    else:
        print(f"❌ エラー: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ 例外発生: {e}")