"""
keep_gold_status.py - OANDA GOLDステータス維持のための自動往復取引

使い方:
  python keep_gold_status.py          # .envのENVIRONMENT設定を使用
  python keep_gold_status.py --live   # 本番口座を強制指定
  python keep_gold_status.py --demo   # デモ口座を強制指定
"""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---- 設定 ----
INSTRUMENT      = 'USD_JPY'
UNITS           = 125_000      # 1回あたりの通貨数（2往復で合計$500,000）
ROUNDS          = 2            # 往復回数
MAX_SPREAD_PIPS = 0.5          # この値より広ければ待機
WAIT_SECONDS    = 30           # スプレッドが広い場合の待機時間（秒）
PIP_SIZE        = 0.01         # USD/JPYの1pip


def get_api_settings(env):
    if env == 'live':
        return (
            'https://api-fxtrade.oanda.com/v3',
            os.environ['OANDA_LIVE_API_TOKEN'],
            os.environ['OANDA_LIVE_ACCOUNT_ID'],
        )
    else:
        return (
            'https://api-fxpractice.oanda.com/v3',
            os.environ['OANDA_DEMO_API_TOKEN'],
            os.environ['OANDA_DEMO_ACCOUNT_ID'],
        )


def get_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def get_spread(api_url, token, account_id):
    """現在のスプレッドをpipsで返す"""
    url = f'{api_url}/accounts/{account_id}/pricing?instruments={INSTRUMENT}'
    resp = requests.get(url, headers=get_headers(token))
    if resp.status_code != 200:
        print(f'❌ スプレッド取得失敗: {resp.status_code}')
        return None
    price = resp.json()['prices'][0]
    ask = float(price['asks'][0]['price'])
    bid = float(price['bids'][0]['price'])
    return (ask - bid) / PIP_SIZE


def send_order(api_url, token, account_id, units):
    """成行注文を送信する。units>0=買い、units<0=売り"""
    url = f'{api_url}/accounts/{account_id}/orders'
    body = {
        'order': {
            'type': 'MARKET',
            'instrument': INSTRUMENT,
            'units': str(units),
        }
    }
    resp = requests.post(url, headers=get_headers(token), json=body)
    if resp.status_code == 201:
        fill = resp.json().get('orderFillTransaction', {})
        price = fill.get('price')
        print(f'  約定価格: {price}')
        return price
    else:
        print(f'  ❌ 注文失敗: {resp.status_code} {resp.text}')
        return None


def close_position(api_url, token, account_id, side):
    """ポジションを全決済する"""
    url = f'{api_url}/accounts/{account_id}/positions/{INSTRUMENT}/close'
    body = {'longUnits': 'ALL'} if side == 'long' else {'shortUnits': 'ALL'}
    resp = requests.put(url, headers=get_headers(token), json=body)
    if resp.status_code == 200:
        key = 'longOrderFillTransaction' if side == 'long' else 'shortOrderFillTransaction'
        price = resp.json().get(key, {}).get('price')
        print(f'  ✅ 決済完了: {price}')
        return price
    else:
        print(f'  ❌ 決済失敗: {resp.status_code} {resp.text}')
        return None


def main():
    load_dotenv(Path(__file__).parent.parent / '.env')

    if '--live' in sys.argv:
        env = 'live'
    elif '--demo' in sys.argv:
        env = 'demo'
    else:
        env = os.environ.get('ENVIRONMENT', 'demo')

    api_url, token, account_id = get_api_settings(env)

    print('=== OANDA GOLDステータス維持 自動往復取引 ===')
    print(f'環境         : {env.upper()}')
    print(f'通貨ペア     : {INSTRUMENT}')
    print(f'通貨数       : {UNITS:,}')
    print(f'往復回数     : {ROUNDS}往復（合計{UNITS * ROUNDS * 2:,}通貨）')
    print(f'スプレッド閾値: {MAX_SPREAD_PIPS}pips以下で実行')
    print()

    # スプレッドが狭くなるまで待機
    while True:
        spread = get_spread(api_url, token, account_id)
        if spread is None:
            print(f'{WAIT_SECONDS}秒後にリトライ...')
            time.sleep(WAIT_SECONDS)
            continue
        print(f'現在のスプレッド: {spread:.2f}pips', end='')
        if spread <= MAX_SPREAD_PIPS:
            print(' → 実行します')
            break
        print(f' → {WAIT_SECONDS}秒後にリトライ...')
        time.sleep(WAIT_SECONDS)

    # 往復取引を実行
    total_cost = 0
    for i in range(1, ROUNDS + 1):
        print(f'\n--- {i}往復目 ---')

        print(f'売りエントリー ({UNITS:,}通貨)')
        entry_price = send_order(api_url, token, account_id, -UNITS)
        if entry_price is None:
            print('❌ エントリー失敗。中止します。')
            break

        time.sleep(1)

        print('即時決済')
        exit_price = close_position(api_url, token, account_id, 'short')
        if exit_price is None:
            print('❌ 決済失敗。手動で決済してください。')
            break

        if entry_price and exit_price:
            cost = (float(exit_price) - float(entry_price)) * UNITS
            total_cost += cost
            print(f'  損益: {cost:+.0f}円')

        time.sleep(1)

    print(f'\n=== 完了 ===')
    print(f'合計損益 : {total_cost:+.0f}円')
    print(f'取引量   : ${UNITS * ROUNDS * 2:,}')


if __name__ == '__main__':
    main()
