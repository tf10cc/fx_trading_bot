import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv


@dataclass(frozen=True)
class OandaConfig:
    """OANDA Practice API config (最低限)"""

    api_token: str
    base_url: str = "https://api-fxpractice.oanda.com"


def _load_oanda_config() -> Optional[OandaConfig]:
    load_dotenv()
    token = os.getenv("OANDA_DEMO_API_TOKEN")
    if not token:
        return None
    return OandaConfig(api_token=token)


def fetch_candles(
    instrument: str,
    *,
    granularity: str = "H1",
    count: int = 200,
    config: Optional[OandaConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    OANDA Practiceからローソク足を取得して DataFrame で返す。

    Returns:
        columns: time, open, high, low, close
    """
    cfg = config or _load_oanda_config()
    if cfg is None:
        return None

    url = f"{cfg.base_url}/v3/instruments/{instrument}/candles"
    headers = {"Authorization": f"Bearer {cfg.api_token}"}
    params = {"count": count, "granularity": granularity, "price": "M"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()
    candles = data.get("candles", [])
    rows = []
    for c in candles:
        mid = c.get("mid")
        if not mid:
            continue
        rows.append(
            {
                "time": c.get("time"),
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
            }
        )

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    df = df.dropna(subset=["time"]).reset_index(drop=True)
    return df


def calculate_heikin_ashi(
    instrument: str,
    *,
    granularity: str = "H1",
    count: int = 200,
    config: Optional[OandaConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    OANDA Practiceのデータから平均足を計算する。

    Returns:
        DataFrame: time, open, high, low, close, ha_open, ha_close, ha_high, ha_low, ha_color
        ha_color: 青=1, 赤=-1
    """
    df = fetch_candles(instrument, granularity=granularity, count=count, config=config)
    if df is None or len(df) < 2:
        return None

    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)

    out = df.copy()
    out["ha_open"] = ha_open
    out["ha_close"] = ha_close
    out["ha_high"] = ha_high
    out["ha_low"] = ha_low
    out["ha_color"] = (out["ha_close"] >= out["ha_open"]).map(lambda x: 1 if x else -1)
    return out

