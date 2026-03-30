"""
FES entry_logic.py  ライブトレード（書き直し版）

起動方法:
  python entry_logic.py                          # デフォルト: logics/heikin_ashi_75sma.py
  python entry_logic.py logics/my_strategy.py   # カセット指定
  python entry_logic.py --test                  # 1回だけ実行して終了
"""

import os
import sys
import time
import importlib.util
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

from heikin_ashi import fetch_candles

# ---- 定数 ----
DEFAULT_COUNT       = 200        # カセットに COUNT がない場合のデフォルト取得本数
DEFAULT_GRANULARITY = 'H1'       # カセットに GRANULARITY がない場合のデフォルト
DEFAULT_INSTRUMENT  = 'USD_JPY'  # 取引銘柄
DEFAULT_UNITS       = 1          # 取引ユニット数（XAU_USD: 1 = 1オンス）
SMA_PERIOD          = 75
OANDA_API_URL       = 'https://api-fxpractice.oanda.com/v3'


# ---- カセット読み込み ----

def load_cassette(path):
    """logics/ フォルダのカセットファイルを読み込む"""
    spec = importlib.util.spec_from_file_location('cassette', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- OANDA API ヘルパー ----

def _headers():
    token = os.environ.get('OANDA_DEMO_API_TOKEN')
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def send_order(instrument, units):
    """
    成行注文を送信する。
    units > 0 = BUY（ロング）、units < 0 = SELL（ショート）
    """
    account_id = os.environ.get('OANDA_DEMO_ACCOUNT_ID')
    url = f'{OANDA_API_URL}/accounts/{account_id}/orders'
    body = {
        'order': {
            'type': 'MARKET',
            'instrument': instrument,
            'units': str(units),
        }
    }
    resp = requests.post(url, headers=_headers(), json=body)
    if resp.status_code == 201:
        fill = resp.json().get('orderFillTransaction', {})
        print(f'  約定価格: {fill.get("price")}')
        return True
    else:
        print(f'  ❌ 注文失敗: {resp.status_code} {resp.text}')
        return False


def close_position(instrument, side):
    """
    ポジションを全決済する。
    side: 'long' または 'short'
    """
    account_id = os.environ.get('OANDA_DEMO_ACCOUNT_ID')
    url = f'{OANDA_API_URL}/accounts/{account_id}/positions/{instrument}/close'
    body = {'longUnits': 'ALL'} if side == 'long' else {'shortUnits': 'ALL'}
    resp = requests.put(url, headers=_headers(), json=body)
    if resp.status_code == 200:
        print(f'  ✅ 決済完了')
        return True
    else:
        print(f'  ❌ 決済失敗: {resp.status_code} {resp.text}')
        return False


# ---- df を作る（OANDAからデータ取得 + 全カラム計算） ----

def build_df(instrument, cassette):
    """
    OANDAからローソク足を取得し、カセットが要求する全カラムを計算して返す。

    カラム: time, open, high, low, close,
            ha_open, ha_close, ha_high, ha_low, ha_color,
            ha_body_top, ha_body_bottom, sma
    """
    count       = getattr(cassette, 'COUNT',       DEFAULT_COUNT)
    granularity = getattr(cassette, 'GRANULARITY', DEFAULT_GRANULARITY)

    # OANDAからローソク足取得
    df = fetch_candles(instrument, granularity=granularity, count=count)
    if df is None or len(df) < 2:
        print('❌ データ取得失敗')
        return None

    # 平均足計算
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open  = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

    df['ha_open']  = ha_open
    df['ha_close'] = ha_close
    df['ha_high']  = pd.concat([df['high'], ha_open, ha_close], axis=1).max(axis=1)
    df['ha_low']   = pd.concat([df['low'],  ha_open, ha_close], axis=1).min(axis=1)
    df['ha_color'] = (df['ha_close'] >= df['ha_open']).map(lambda x: 1 if x else -1)
    df['ha_body_top']    = df[['ha_open', 'ha_close']].max(axis=1)
    df['ha_body_bottom'] = df[['ha_open', 'ha_close']].min(axis=1)

    # SMA計算
    df['sma'] = df['close'].rolling(window=SMA_PERIOD).mean()

    return df.reset_index(drop=True)


# ---- 1回の判定サイクル ----

def run_once(df, cassette, position, instrument=DEFAULT_INSTRUMENT):
    """
    最新の確定済み足（idx = 末尾から2番目）でカセットを呼び出し、
    BUY / SELL / EXIT を判定して注文を送信する。

    ※ OANDAは未確定の現在足も返す場合があるため、
       安全のため末尾-1（1本前の確定足）で判定する。

    Returns: 新しい position ('long' / 'short' / None)
    """
    idx = len(df) - 2  # 最新の確定済み足

    if position is None:
        if cassette.check_long_entry(df, idx):
            print('✅ BUY シグナル → 注文送信')
            if send_order(instrument, DEFAULT_UNITS):
                return 'long'
        elif cassette.check_short_entry(df, idx):
            print('✅ SELL シグナル → 注文送信')
            if send_order(instrument, -DEFAULT_UNITS):
                return 'short'
        else:
            print('⏸️  待機（条件不成立）')

    else:
        if position == 'long' and cassette.check_long_exit(df, idx):
            print('🔴 ロング決済 → 決済注文送信')
            if close_position(instrument, 'long'):
                return None
        elif position == 'short' and cassette.check_short_exit(df, idx):
            print('🔵 ショート決済 → 決済注文送信')
            if close_position(instrument, 'short'):
                return None
        else:
            print(f'📊 ポジション保有中（{position}）')

    return position


# ---- メインループ（毎時0分に実行） ----

def main_loop(cassette, instrument=DEFAULT_INSTRUMENT):
    position = None  # 現在のポジション（None / 'long' / 'short'）

    print(f'FES ライブトレード起動')
    print(f'カセット  : {getattr(cassette, "NAME", "不明")}')
    print(f'銘柄      : {instrument}')
    print(f'足の種類  : {getattr(cassette, "GRANULARITY", DEFAULT_GRANULARITY)}')
    print(f'取得本数  : {getattr(cassette, "COUNT", DEFAULT_COUNT)}')

    while True:
        now = datetime.now(timezone.utc)
        print(f'\n{"=" * 40}')
        print(f'[{now.strftime("%Y-%m-%d %H:%M")} UTC] 判定開始')

        df = build_df(instrument, cassette)
        if df is not None:
            position = run_once(df, cassette, position, instrument)
        else:
            print('データ取得エラー。次の時間まで待機します')

        # 次の時間0分まで待機
        wait_seconds = 3600 - (now.minute * 60 + now.second)
        print(f'次の判定まで {wait_seconds // 60} 分 {wait_seconds % 60} 秒待機...')
        time.sleep(wait_seconds)


# ---- 起動 ----

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    load_dotenv()

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    cassette_path = args[0] if args else 'logics/heikin_ashi_75sma.py'
    if not os.path.exists(cassette_path):
        print(f'[ERROR] カセットファイルが見つかりません: {cassette_path}')
        sys.exit(1)

    cassette = load_cassette(cassette_path)

    if '--test' in sys.argv:
        print('【テストモード】1回だけ実行して終了')
        df = build_df(DEFAULT_INSTRUMENT, cassette)
        if df is not None:
            run_once(df, cassette, None, DEFAULT_INSTRUMENT)
    else:
        main_loop(cassette)
