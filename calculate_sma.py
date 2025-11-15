import os
from dotenv import load_dotenv
import requests
import pandas as pd

# .env 読み込み
load_dotenv()

api_token = os.getenv('OANDA_DEMO_API_TOKEN')

# 過去100本の1時間足データ取得
url = "https://api-fxpractice.oanda.com/v3/instruments/USD_JPY/candles"

params = {
    "count": 100,  # 過去100本
    "granularity": "H1"  # 1時間足
}

headers = {
    "Authorization": f"Bearer {api_token}"
}

print("=== データ取得中 ===")
response = requests.get(url, headers=headers, params=params)

if response.status_code == 200:
    data = response.json()
    
    # DataFrameに変換
    candles = []
    for candle in data['candles']:
        candles.append({
            'time': candle['time'],
            'close': float(candle['mid']['c'])
        })
    
    df = pd.DataFrame(candles)
    
    # 移動平均計算
    df['SMA5'] = df['close'].rolling(window=5).mean()
    df['SMA25'] = df['close'].rolling(window=25).mean()
    
    # 最新10件を表示
    print("\n=== 最新10件 ===")
    print(df[['time', 'close', 'SMA5', 'SMA25']].tail(10))
    
    # 最新の値
    latest = df.iloc[-1]
    print("\n=== 最新値 ===")
    print(f"終値: {latest['close']}")
    print(f"5期間移動平均: {latest['SMA5']:.3f}")
    print(f"25期間移動平均: {latest['SMA25']:.3f}")
    
    # ゴールデンクロス・デッドクロス判定
    prev = df.iloc[-2]
    if prev['SMA5'] < prev['SMA25'] and latest['SMA5'] > latest['SMA25']:
        print("\n🔥 ゴールデンクロス発生！")
    elif prev['SMA5'] > prev['SMA25'] and latest['SMA5'] < latest['SMA25']:
        print("\n❄️ デッドクロス発生！")
    
else:
    print(f"エラー: {response.status_code}")