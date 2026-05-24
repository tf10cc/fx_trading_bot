"""
OANDAからUSD/JPY データを取得して保存するスクリプト

使い方:
  python download_oanda_data.py          # 検証用：7・8・9月だけ取得（月別・H1）
  python download_oanda_data.py --all    # 2024年1〜12月を全部取得（月別・H1）
  python download_oanda_data.py --year   # 2024年を1ファイルにまとめて取得（H1）
  python download_oanda_data.py --m5     # 2024年を1ファイルにまとめて取得（M5）

保存先（H1年別）: data/USDJPY_H1_2024_OANDA.csv
保存先（M5年別）: data/USDJPY_M5_2024_OANDA.csv
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

INSTRUMENT   = "USD_JPY"
BASE_URL     = "https://api-fxpractice.oanda.com"
DATA_DIR     = Path(__file__).parent / "data"
MAX_COUNT    = 5000  # OANDAのAPI上限

# --m5 フラグで切り替え
USE_M5      = "--m5" in sys.argv
GRANULARITY = "M5" if USE_M5 else "H1"
STEP        = timedelta(minutes=5) if USE_M5 else timedelta(hours=1)


def _fetch_chunk(headers: dict, from_dt: datetime) -> list:
    """指定期間のロウソク足を取得（最大MAX_COUNT本）"""
    params = {
        "from":        from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "granularity": GRANULARITY,
        "price":       "M",
        "count":       MAX_COUNT,
    }
    resp = requests.get(
        f"{BASE_URL}/v3/instruments/{INSTRUMENT}/candles",
        headers=headers,
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"APIエラー: {resp.status_code} {resp.text}")
    return resp.json().get("candles", [])


def fetch_range(from_dt: datetime, to_dt: datetime) -> pd.DataFrame:
    """指定期間を5000本ずつページングして全件取得"""
    token = os.environ.get("OANDA_DEMO_API_TOKEN")
    if not token:
        raise RuntimeError(".envにOANDA_DEMO_API_TOKENが設定されていません")

    headers = {"Authorization": f"Bearer {token}"}
    all_rows = []
    current_from = from_dt

    while current_from < to_dt:
        candles = _fetch_chunk(headers, current_from)
        if not candles:
            break

        for c in candles:
            if not c.get("complete"):
                continue
            candle_time = datetime.strptime(c["time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if candle_time >= to_dt:
                break
            mid = c.get("mid", {})
            all_rows.append({
                "time":  c["time"],
                "open":  float(mid["o"]),
                "high":  float(mid["h"]),
                "low":   float(mid["l"]),
                "close": float(mid["c"]),
            })

        if len(candles) < MAX_COUNT:
            break

        # 最後のロウソク足の次の時刻から再開
        last_time = datetime.strptime(candles[-1]["time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        current_from = last_time + STEP
        print(f"  ページング: {current_from.strftime('%Y-%m-%d %H:%M')} から続きを取得...", flush=True)

    return pd.DataFrame(all_rows)


def fetch_month(year: int, month: int) -> pd.DataFrame:
    from_dt = datetime(year, month, 1, tzinfo=timezone.utc)
    to_dt   = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return fetch_range(from_dt, to_dt)


def download_month(year: int, month: int):
    print(f"{year}年{month:02d}月を取得中...", end=" ", flush=True)
    df = fetch_month(year, month)
    filename = f"USD-JPY_H1_{year}-{month:02d}_OANDA.csv"
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_DIR / filename, index=False)
    print(f"{len(df)}本 → {filename}")
    return df


def download_year(year: int):
    label = GRANULARITY
    print(f"{year}年（{label}）を1ファイルで取得中...", flush=True)
    from_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
    to_dt   = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    df = fetch_range(from_dt, to_dt)
    filename = f"USDJPY_{label}_{year}_OANDA.csv"
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_DIR / filename, index=False)
    print(f"合計 {len(df)}本 → {filename}")
    return df


if __name__ == "__main__":
    if "--m5" in sys.argv or "--year" in sys.argv:
        download_year(2024)
    elif "--all" in sys.argv:
        for m in range(1, 13):
            download_month(2024, m)
    else:
        for m in [7, 8, 9]:
            download_month(2024, m)

    print("\n完了。")
