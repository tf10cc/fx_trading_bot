import os
from dotenv import load_dotenv
import requests
import pandas as pd
from heikin_ashi import calculate_heikin_ashi

# .env 読み込み
load_dotenv()

api_token = os.getenv('OANDA_DEMO_API_TOKEN')

def get_sma(instrument='USD_JPY', period=75, count=100):
    """
    指定期間のSMAを計算
    """
    url = f"https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
    
    params = {
        "count": count,
        "granularity": "H1"
    }
    
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    
    candles = []
    for candle in data['candles']:
        candles.append({
            'close': float(candle['mid']['c'])
        })
    
    df = pd.DataFrame(candles)
    df['SMA'] = df['close'].rolling(window=period).mean()
    
    return df['SMA'].iloc[-1], df['close'].iloc[-1]

def check_sma_slope(instrument='USD_JPY', period=75, lookback=5):
    """
    SMAが傾いているか確認
    lookback: 何本前と比較するか
    """
    url = f"https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
    
    params = {
        "count": period + lookback + 10,
        "granularity": "H1"
    }
    
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        return False
    
    data = response.json()
    
    candles = []
    for candle in data['candles']:
        candles.append({
            'close': float(candle['mid']['c'])
        })
    
    df = pd.DataFrame(candles)
    df['SMA'] = df['close'].rolling(window=period).mean()
    
    # 最新のSMAと5本前のSMAを比較
    latest_sma = df['SMA'].iloc[-1]
    prev_sma = df['SMA'].iloc[-1-lookback]
    
    slope = latest_sma - prev_sma
    
    return slope, slope > 0  # 傾きと上昇中かどうか

def entry_signal(instrument='USD_JPY'):
    """
    エントリーシグナルを判定
    
    Returns:
    - 'BUY': 買いシグナル
    - 'SELL': 売りシグナル
    - 'WAIT': 待機
    """
    print(f"=== {instrument} エントリー判定 ===\n")

    if not api_token:
        print("❌ OANDA_DEMO_API_TOKEN が未設定です（.env を用意してください）")
        return 'WAIT'
    
    # 1. 現在価格と75SMA取得
    sma_result = get_sma(instrument, period=75)
    if sma_result is None:
        print("❌ SMA取得エラー")
        return 'WAIT'
    
    sma75, current_price = sma_result
    print(f"現在価格: {current_price:.3f}")
    print(f"75SMA: {sma75:.3f}")
    
    # 2. SMAの傾きチェック
    slope, is_uptrend = check_sma_slope(instrument, period=75)
    print(f"SMAの傾き: {slope:.3f} ({'上昇' if is_uptrend else '下降'})")
    
    # 3. 平均足の色変化チェック
    df_ha = calculate_heikin_ashi(instrument, granularity="H1", count=200)
    if df_ha is None:
        print("❌ 平均足取得エラー")
        return 'WAIT'
    
    latest_ha = df_ha.iloc[-1]
    prev_ha = df_ha.iloc[-2]
    
    ha_color_change = None
    if prev_ha['ha_color'] == -1 and latest_ha['ha_color'] == 1:
        ha_color_change = 'RED_TO_BLUE'
        print("平均足: 🔵 陰線→陽線（買いシグナル）")
    elif prev_ha['ha_color'] == 1 and latest_ha['ha_color'] == -1:
        ha_color_change = 'BLUE_TO_RED'
        print("平均足: 🔴 陽線→陰線（売りシグナル）")
    else:
        print("平均足: ⚪ 色変化なし")
    
    # 4. エントリー判定
    print("\n--- 判定結果 ---")
    
    # 買いシグナル判定
    if (current_price > sma75 and  # 価格がSMAより上
        is_uptrend and  # SMAが上昇中
        ha_color_change == 'RED_TO_BLUE'):  # 平均足が陰線→陽線
        print("✅ 買いエントリー！")
        return 'BUY'
    
    # 売りシグナル判定
    elif (current_price < sma75 and  # 価格がSMAより下
          not is_uptrend and  # SMAが下降中
          ha_color_change == 'BLUE_TO_RED'):  # 平均足が陽線→陰線
        print("✅ 売りエントリー！")
        return 'SELL'
    
    else:
        print("⏸️ 待機（条件不成立）")
        
        # 何が足りないか表示
        if current_price <= sma75:
            print("  - 価格がSMAより下")
        if not is_uptrend:
            print("  - SMAが上昇していない")
        if ha_color_change is None:
            print("  - 平均足の色変化なし")
        
        return 'WAIT'

# テスト実行
if __name__ == "__main__":
    signal = entry_signal('USD_JPY')
    print(f"\n最終判定: {signal}")