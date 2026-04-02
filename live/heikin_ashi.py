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

