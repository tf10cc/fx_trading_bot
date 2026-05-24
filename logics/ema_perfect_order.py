"""
りょうちゃん式 EMAパーフェクトオーダー手法
エントリー：EMA10・25・75がパーフェクトオーダー + 直近高値/安値ブレイク
決済    ：パーフェクトオーダーが崩れたら
損切り  ：固定30pips
※ 本来はRR1:1（損切り幅と同じ距離で利確）だが、エンジン未対応のため現状はEMA崩れで決済
"""
import pandas as pd

NAME = "EMAパーフェクトオーダー H1（りょうちゃん式）"
CHART_TITLE = "ローソク足 + EMA10/25/75"
GRANULARITY = "H1"
COUNT = 200

LAST = -1
PREV = LAST - 1

STOP_LOSS_PIPS = 30
SWING_LOOKBACK = 20  # 直近高値/安値を探す本数

plot_config = {
    "main_plot": {
        "ema75": {"color": "#333333", "lineWidth": 2, "title": "75EMA"},
        "ema25": {"color": "#2196F3", "lineWidth": 1, "title": "25EMA"},
        "ema10": {"color": "#F44336", "lineWidth": 1, "title": "10EMA"},
    }
}


def populate_indicators(df):
    df = df.copy()
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema25'] = df['close'].ewm(span=25, adjust=False).mean()
    df['ema75'] = df['close'].ewm(span=75, adjust=False).mean()

    # チャートエンジンが要求するha_列に通常ローソク足の値を渡す（ローソク足表示）
    df['ha_open']  = df['open']
    df['ha_high']  = df['high']
    df['ha_low']   = df['low']
    df['ha_close'] = df['close']

    # sma列はema75を代用（チャートのオレンジ線として表示）
    df['sma'] = df['ema75']

    return df


def _perfect_order_long(df):
    """上昇パーフェクトオーダー：ema75 < ema25 < ema10"""
    return (df['ema75'].iloc[LAST] < df['ema25'].iloc[LAST] < df['ema10'].iloc[LAST])


def _perfect_order_short(df):
    """下降パーフェクトオーダー：ema75 > ema25 > ema10"""
    return (df['ema75'].iloc[LAST] > df['ema25'].iloc[LAST] > df['ema10'].iloc[LAST])


def check_long_entry(df):
    if len(df) < SWING_LOOKBACK + 2:
        return False
    if not _perfect_order_long(df):
        return False
    # 直近SWING_LOOKBACK本の高値をブレイクしたらエントリー
    recent_high = df['high'].iloc[-(SWING_LOOKBACK + 1):-1].max()
    return df['close'].iloc[LAST] > recent_high


def check_short_entry(df):
    if len(df) < SWING_LOOKBACK + 2:
        return False
    if not _perfect_order_short(df):
        return False
    # 直近SWING_LOOKBACK本の安値をブレイクしたらエントリー
    recent_low = df['low'].iloc[-(SWING_LOOKBACK + 1):-1].min()
    return df['close'].iloc[LAST] < recent_low


def check_long_exit(df):
    """パーフェクトオーダーが崩れたら決済"""
    return not _perfect_order_long(df)


def check_short_exit(df):
    """パーフェクトオーダーが崩れたら決済"""
    return not _perfect_order_short(df)
