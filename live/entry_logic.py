"""
FES entry_logic.py  ライブトレード（書き直し版）

起動方法:
  python entry_logic.py                          # デフォルト: logics/heikin_ashi_75sma.py
  python entry_logic.py logics/my_strategy.py   # カセット指定
  python entry_logic.py --test                  # 1回だけ実行して終了
"""

import csv
import json
import os
import sys
import time
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

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
LOG_FILE            = Path(__file__).parent / 'trade_log.csv'
LOG_HEADERS         = ['datetime_utc', 'action', 'instrument', 'price']
POSITION_FILE       = Path(__file__).parent / 'position_state.json'


# ---- ポジション状態の保存・読み込み ----

def load_position():
    """ポジション状態をファイルから読み込む"""
    if POSITION_FILE.exists():
        with open(POSITION_FILE, 'r') as f:
            state = json.load(f)
        if isinstance(state, dict):
            return state.get('position')
    return None

def load_state():
    """ライブ判定の状態をファイルから読み込む"""
    if POSITION_FILE.exists():
        with open(POSITION_FILE, 'r') as f:
            state = json.load(f)
        if isinstance(state, dict):
            state.setdefault('position', None)
            state.setdefault('last_processed_candle', None)
            return state
    return {'position': None, 'last_processed_candle': None}


def save_state(state):
    """ライブ判定の状態をファイルに保存する"""
    with open(POSITION_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---- ログ書き出し ----

def log_trade(action, instrument, price):
    """エントリー・決済をtrade_log.csvに追記する"""
    file_exists = LOG_FILE.exists()
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'datetime_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),
            'action':       action,
            'instrument':   instrument,
            'price':        price,
        })


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
        price = fill.get('price')
        print(f'  約定価格: {price}')
        return price
    else:
        print(f'  ❌ 注文失敗: {resp.status_code} {resp.text}')
        return None


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
        key = 'longOrderFillTransaction' if side == 'long' else 'shortOrderFillTransaction'
        price = resp.json().get(key, {}).get('price')
        print(f'  ✅ 決済完了: {price}')
        return price
    else:
        print(f'  ❌ 決済失敗: {resp.status_code} {resp.text}')
        return None


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

    # Freqtradeと同じ考え方で、未完成足は戦略判定に使わない。
    if 'complete' in df.columns:
        incomplete_count = len(df) - int(df['complete'].sum())
        if incomplete_count:
            print(f'[DEBUG] 未完成足を除外: {incomplete_count} 本')
        df = df[df['complete']].copy()

    if len(df) < 2:
        print('❌ 確定足が不足しています')
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

    df = df.reset_index(drop=True)

    # candle_log.csv に保存（初回は全件、以降は新しい足だけ追記）
    candle_log = Path(__file__).parent / 'candle_log.csv'
    if candle_log.exists():
        existing = pd.read_csv(candle_log)
        existing['time'] = pd.to_datetime(existing['time'], errors='coerce', utc=True)
        last_time = existing['time'].iloc[-1]
        new_rows = df[df['time'] > last_time]
        if not new_rows.empty:
            log_columns = [c for c in existing.columns if c in new_rows.columns]
            new_rows[log_columns].to_csv(candle_log, mode='a', header=False, index=False)
    else:
        df.to_csv(candle_log, index=False)

    return df


# ---- 1回の判定サイクル ----

def run_once(df, cassette, state, instrument=DEFAULT_INSTRUMENT):
    """
    最新の確定足で条件を判定し、シグナルが出たら現在足の始値付近で発注する。
    Returns: 更新後の state
    """
    candle_time = df['time'].iloc[-1].isoformat()
    if state.get('last_processed_candle') == candle_time:
        print(f'[DEBUG] 判定済みの確定足のためスキップ: {candle_time}')
        return state

    position = state.get('position')

    prev_color = df['ha_color'].iloc[-2]
    curr_color = df['ha_color'].iloc[-1]
    sma_now = df['sma'].iloc[-1]
    sma_5ago = df['sma'].iloc[-6]
    print(f'[DEBUG] 判定足={df["time"].iloc[-1]}')
    print(f'[DEBUG] prev_color={prev_color}, curr_color={curr_color}')
    print(f'[DEBUG] sma_now={sma_now:.4f}, sma_5ago={sma_5ago:.4f}')
    print(f'[DEBUG] ha_body_bottom={df["ha_body_bottom"].iloc[-1]:.4f}')
    print(f'[DEBUG] ha_body_top={df["ha_body_top"].iloc[-1]:.4f}')

    just_exited = False
    action_failed = False

    # バックテスト版と同じ順序：決済チェック → 同じ足では再エントリーしない → エントリー。
    if position == 'long':
        if cassette.check_long_exit(df):
            print('🔴 ロング決済 → 決済注文送信')
            price = close_position(instrument, 'long')
            if price is not None:
                log_trade('EXIT_LONG', instrument, price)
                position = None
                just_exited = True
            else:
                action_failed = True
        else:
            print('📊 ポジション保有中（long）')
    elif position == 'short':
        if cassette.check_short_exit(df):
            print('🔵 ショート決済 → 決済注文送信')
            price = close_position(instrument, 'short')
            if price is not None:
                log_trade('EXIT_SHORT', instrument, price)
                position = None
                just_exited = True
            else:
                action_failed = True
        else:
            print('📊 ポジション保有中（short）')

    if position is None and not just_exited:
        if cassette.check_long_entry(df):
            print('✅ BUY シグナル → 注文送信')
            price = send_order(instrument, DEFAULT_UNITS)
            if price is not None:
                log_trade('BUY', instrument, price)
                position = 'long'
            else:
                action_failed = True
        elif cassette.check_short_entry(df):
            print('✅ SELL シグナル → 注文送信')
            price = send_order(instrument, -DEFAULT_UNITS)
            if price is not None:
                log_trade('SELL', instrument, price)
                position = 'short'
            else:
                action_failed = True
        else:
            print('⏸️  待機（条件不成立）')
    elif just_exited:
        print('⏸️  決済した足では新規エントリーしません')

    state['position'] = position
    if not action_failed:
        state['last_processed_candle'] = candle_time
    return state


# ---- メインループ（毎時0分に実行） ----

def main_loop(cassette, instrument=DEFAULT_INSTRUMENT):
    state = load_state()

    print(f'FES ライブトレード起動')
    print(f'カセット  : {getattr(cassette, "NAME", "不明")}')
    print(f'銘柄      : {instrument}')
    print(f'足の種類  : {getattr(cassette, "GRANULARITY", DEFAULT_GRANULARITY)}')
    print(f'取得本数  : {getattr(cassette, "COUNT", DEFAULT_COUNT)}')
    print(f'ポジション: {state.get("position")}')
    print(f'最終判定足: {state.get("last_processed_candle")}')

    granularity = getattr(cassette, 'GRANULARITY', DEFAULT_GRANULARITY)
    interval = 300 if granularity == 'M5' else 3600  # M5=5分, H1=1時間

    while True:
        now = datetime.now(timezone.utc)
        print(f'\n{"=" * 40}')
        print(f'[{now.strftime("%Y-%m-%d %H:%M")} UTC] 判定開始')

        df = build_df(instrument, cassette)
        if df is not None:
            state = run_once(df, cassette, state, instrument)
            save_state(state)
        else:
            print('データ取得エラー。次の足まで待機します')

        # 次の足の始まりまで待機
        elapsed = (now.minute * 60 + now.second) % interval
        wait_seconds = interval - elapsed
        print(f'次の判定まで {wait_seconds // 60} 分 {wait_seconds % 60} 秒待機...')
        time.sleep(wait_seconds)


# ---- 起動 ----

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    load_dotenv()

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    cassette_path = args[0] if args else str(Path(__file__).parent.parent / 'logics' / 'heikin_ashi_75sma.py')
    if not os.path.exists(cassette_path):
        print(f'[ERROR] カセットファイルが見つかりません: {cassette_path}')
        sys.exit(1)

    cassette = load_cassette(cassette_path)

    if '--test' in sys.argv:
        print('【テストモード】1回だけ実行して終了')
        df = build_df(DEFAULT_INSTRUMENT, cassette)
        if df is not None:
            state = load_state()
            state = run_once(df, cassette, state, DEFAULT_INSTRUMENT)
            save_state(state)
    else:
        main_loop(cassette)
