import os
from dotenv import load_dotenv
import requests
import pandas as pd

# .env 読み込み
load_dotenv()

api_token = os.getenv('OANDA_DEMO_API_TOKEN')

def calculate_heikin_ashi(instrument='USD_JPY', count=50):
    """
    平均足を計算する
    
    Parameters:
    - instrument: 通貨ペア
    - count: 取得する足の数
    
    Returns:
    - DataFrame: 平均足データ
    """
    url = f"https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
    
    params = {
        "count": count,
        "granularity": "H1"  # 1時間足
    }
    
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"エラー: {response.status_code}")
        return None
    
    data = response.json()
    
    # 通常のローソク足データを取得
    candles = []
    for candle in data['candles']:
        candles.append({
            'time': candle['time'],
            'open': float(candle['mid']['o']),
            'high': float(candle['mid']['h']),
            'low': float(candle['mid']['l']),
            'close': float(candle['mid']['c'])
        })
    
    df = pd.DataFrame(candles)
    
    # 平均足の計算
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # 最初の平均足始値は通常の始値と終値の平均
    df.loc[0, 'ha_open'] = (df.loc[0, 'open'] + df.loc[0, 'close']) / 2
    
    # 2本目以降の平均足始値
    for i in range(1, len(df)):
        df.loc[i, 'ha_open'] = (df.loc[i-1, 'ha_open'] + df.loc[i-1, 'ha_close']) / 2
    
    # 平均足高値・安値
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)
    
    # 平均足の色判定（陽線=1, 陰線=-1）
    df['ha_color'] = (df['ha_close'] > df['ha_open']).astype(int) * 2 - 1
    
    return df

# テスト実行
if __name__ == "__main__":
    print("=== 平均足計算テスト ===")
    
    df = calculate_heikin_ashi()
    
    if df is not None:
        # 最新10件を表示
        print("\n最新10件の平均足:")
        print(df[['time', 'ha_open', 'ha_high', 'ha_low', 'ha_close', 'ha_color']].tail(10))
        
        # 色変化の確認
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        print(f"\n=== 最新の平均足 ===")
        print(f"始値: {latest['ha_open']:.3f}")
        print(f"終値: {latest['ha_close']:.3f}")
        print(f"色: {'陽線（青）' if latest['ha_color'] == 1 else '陰線（赤）'}")
        
        # 色変化判定
        if prev['ha_color'] == -1 and latest['ha_color'] == 1:
            print("\n🔵 色変化：陰線→陽線（買いシグナル）")
        elif prev['ha_color'] == 1 and latest['ha_color'] == -1:
            print("\n🔴 色変化：陽線→陰線（売りシグナル）")
        else:
            print("\n⚪ 色変化なし")