import os
from dotenv import load_dotenv
import requests

# .env 読み込み
load_dotenv()

api_token = os.getenv('OANDA_DEMO_API_TOKEN')
account_id = os.getenv('OANDA_DEMO_ACCOUNT_ID')

# 価格取得API
url = "https://api-fxpractice.oanda.com/v3/instruments/USD_JPY/candles"

params = {
    "count": 1,  # 最新1本
    "granularity": "M1"  # 1分足
}

headers = {
    "Authorization": f"Bearer {api_token}"
}

response = requests.get(url, headers=headers, params=params)

if response.status_code == 200:
    data = response.json()
    candle = data['candles'][0]
    
    print("=== ドル円 最新価格 ===")
    print(f"時刻: {candle['time']}")
    print(f"始値: {candle['mid']['o']}")
    print(f"高値: {candle['mid']['h']}")
    print(f"安値: {candle['mid']['l']}")
    print(f"終値: {candle['mid']['c']}")
else:
    print(f"エラー: {response.status_code}")