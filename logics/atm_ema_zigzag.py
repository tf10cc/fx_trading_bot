"""
ATM手法（EMAパーフェクトオーダー + ジグザグブレイクアウト）
エントリー：EMA10/25/75パーフェクトオーダー + 直近ジグザグ高値（安値）ブレイク
損切り    ：ジグザグ直近安値（高値）に足のヒゲが届いたら次足始値で決済
利確      ：RR1:1（損切り幅と同じ距離）
"""
import numpy as np
import pandas as pd

NAME = "ATM手法 H1（EMAパーフェクトオーダー + ジグザグ）"
CHART_TITLE = "ローソク足 + EMA10/25/75 + ジグザグ"
GRANULARITY = "H1"
COUNT = 300
STOP_LOSS_PIPS = 0  # SL/TPはカセット内で管理

LAST = -1
PREV = LAST - 1

ZIGZAG_THRESHOLD = 0.003  # 感度（0.3% ≈ 45pips at USDJPY 150円）
ZIGZAG_LOOKBACK  = 200    # ジグザグ計算に使う本数

plot_config = {
    "main_plot": {
        "ema75":   {"color": "#333333", "lineWidth": 2, "title": "75EMA"},
        "ema25":   {"color": "#2196F3", "lineWidth": 1, "title": "25EMA"},
        "ema10":   {"color": "#F44336", "lineWidth": 1, "title": "10EMA"},
        "zz_line": {"color": "#FFEB3B", "lineWidth": 1, "title": "ZigZag"},
    }
}

# ポジション中のSL・TP価格（絶対値）
_sl_price = None
_tp_price = None


def _calc_pivots(prices, threshold):
    """
    ZigZagのピボット点を計算する。
    prices    : 価格の配列（close推奨）
    threshold : 最小変動率（例: 0.003 = 0.3%）
    戻り値    : 各インデックスが 1（高値ピボット）/ -1（安値ピボット）/ 0（なし）の配列
    """
    n = len(prices)
    if n < 3:
        return np.zeros(n, dtype=int)

    pivots = np.zeros(n, dtype=int)
    trend = 0            # 0=未確定, 1=上昇, -1=下降
    last_idx   = 0
    last_price = prices[0]

    for i in range(1, n):
        change = (prices[i] - last_price) / last_price if last_price != 0 else 0

        if trend == 0:
            if change >= threshold:
                trend = 1
                pivots[0] = -1   # 最初の点は安値ピボット
                last_idx, last_price = 0, prices[0]
            elif change <= -threshold:
                trend = -1
                pivots[0] = 1    # 最初の点は高値ピボット
                last_idx, last_price = 0, prices[0]

        elif trend == 1:           # 上昇中 → 高値を更新 or 反転
            if prices[i] >= last_price:
                last_idx, last_price = i, prices[i]
            elif (prices[i] - last_price) / last_price <= -threshold:
                pivots[last_idx] = 1   # 直前の高値を確定
                trend = -1
                last_idx, last_price = i, prices[i]

        else:                      # 下降中 → 安値を更新 or 反転
            if prices[i] <= last_price:
                last_idx, last_price = i, prices[i]
            elif (prices[i] - last_price) / last_price >= threshold:
                pivots[last_idx] = -1  # 直前の安値を確定
                trend = 1
                last_idx, last_price = i, prices[i]

    # 末尾の暫定ピボットは未確定として記録しておく（チャート表示用のみ利用）
    if trend == 1:
        pivots[last_idx] = 1
    elif trend == -1:
        pivots[last_idx] = -1

    return pivots


def populate_indicators(df):
    global _sl_price, _tp_price
    _sl_price = None
    _tp_price = None

    df = df.copy()
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema25'] = df['close'].ewm(span=25, adjust=False).mean()
    df['ema75'] = df['close'].ewm(span=75, adjust=False).mean()

    # チャートエンジン用（通常ローソク足）
    df['ha_open']  = df['open']
    df['ha_high']  = df['high']
    df['ha_low']   = df['low']
    df['ha_close'] = df['close']
    df['sma']      = df['ema75']

    # チャート表示用ジグザグ（全データで計算 - 表示専用）
    pivots = _calc_pivots(df['close'].values, ZIGZAG_THRESHOLD)
    zz = pd.Series(np.nan, index=df.index)
    for i, p in enumerate(pivots):
        if p == 1:
            zz.iloc[i] = df['high'].iloc[i]
        elif p == -1:
            zz.iloc[i] = df['low'].iloc[i]
    df['zz_line'] = zz

    return df


def _get_confirmed_zz_levels(df):
    """
    df_slice（その時点までのデータ）から確定済みの直近ジグザグ高値・安値を返す。
    末尾の暫定ピボットは除外してリペイントを防ぐ。
    """
    n = min(ZIGZAG_LOOKBACK, len(df))
    sub = df.iloc[-n:]
    pivots = _calc_pivots(sub['close'].values, ZIGZAG_THRESHOLD)

    last_high = None
    last_low  = None
    # 末尾の1点（暫定）を除いた範囲を後ろから走査
    for i in range(len(pivots) - 2, -1, -1):
        if pivots[i] == 1 and last_high is None:
            last_high = float(sub['high'].iloc[i])
        if pivots[i] == -1 and last_low is None:
            last_low  = float(sub['low'].iloc[i])
        if last_high is not None and last_low is not None:
            break

    return last_high, last_low


def _perfect_order_long(df):
    return df['ema75'].iloc[LAST] < df['ema25'].iloc[LAST] < df['ema10'].iloc[LAST]


def _perfect_order_short(df):
    return df['ema75'].iloc[LAST] > df['ema25'].iloc[LAST] > df['ema10'].iloc[LAST]


def check_long_entry(df):
    global _sl_price, _tp_price
    if len(df) < 80:
        return False
    if not _perfect_order_long(df):
        return False
    if df['close'].iloc[LAST] < df['ema75'].iloc[LAST]:
        return False

    zz_high, zz_low = _get_confirmed_zz_levels(df)
    if zz_high is None or zz_low is None:
        return False

    risk = zz_high - zz_low
    if risk <= 0:
        return False

    # 現在の足のHighがジグザグ高値に届いたらブレイクアウト
    if df['high'].iloc[LAST] >= zz_high:
        _sl_price = zz_low
        _tp_price = zz_high + risk
        return True

    return False


def check_short_entry(df):
    global _sl_price, _tp_price
    if len(df) < 80:
        return False
    if not _perfect_order_short(df):
        return False
    if df['close'].iloc[LAST] > df['ema75'].iloc[LAST]:
        return False

    zz_high, zz_low = _get_confirmed_zz_levels(df)
    if zz_high is None or zz_low is None:
        return False

    risk = zz_high - zz_low
    if risk <= 0:
        return False

    # 現在の足のLowがジグザグ安値に届いたらブレイクアウト
    if df['low'].iloc[LAST] <= zz_low:
        _sl_price = zz_high
        _tp_price = zz_low - risk
        return True

    return False


def check_long_exit(df):
    global _sl_price, _tp_price
    if _sl_price is None or _tp_price is None:
        return False
    if df['low'].iloc[LAST] <= _sl_price or df['high'].iloc[LAST] >= _tp_price:
        _sl_price = None
        _tp_price = None
        return True
    return False


def check_short_exit(df):
    global _sl_price, _tp_price
    if _sl_price is None or _tp_price is None:
        return False
    if df['high'].iloc[LAST] >= _sl_price or df['low'].iloc[LAST] <= _tp_price:
        _sl_price = None
        _tp_price = None
        return True
    return False
