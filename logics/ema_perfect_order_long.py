"""
EMAパーフェクトオーダー ロング専用
エントリー：EMA75 < EMA25 < EMA10 かつ close > EMA75
決済      ：ローソク足の安値がEMA25に触れる or EMA25の傾きがなくなる → 次足始値で決済
"""

NAME = "EMAパーフェクトオーダー ロング専用"
CHART_TITLE = "ローソク足 + EMA10/25/75"
GRANULARITY = "H1"
COUNT = 300
STOP_LOSS_PIPS = 0

LAST = -1
PREV = LAST - 1

EMA_GAP_MIN = 5.0  # ギャップ（開き）フィルター：EMA25とEMA75の最低間隔（ドル）

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

    # エンジン互換（ローソク足をそのまま使用）
    df['ha_open']  = df['open']
    df['ha_high']  = df['high']
    df['ha_low']   = df['low']
    df['ha_close'] = df['close']
    df['sma']      = df['ema75']

    return df


def check_long_entry(df):
    if len(df) < 80:
        return False
    # EMAパーフェクトオーダー（上昇）
    if not (df['ema75'].iloc[LAST] < df['ema25'].iloc[LAST] < df['ema10'].iloc[LAST]):
        return False
    # 3本のEMAがすべて右肩上がり
    if not (df['ema10'].iloc[LAST] > df['ema10'].iloc[PREV]):
        return False
    if not (df['ema25'].iloc[LAST] > df['ema25'].iloc[PREV]):
        return False
    if not (df['ema75'].iloc[LAST] > df['ema75'].iloc[PREV]):
        return False
    # 終値がEMA75より上
    if df['close'].iloc[LAST] <= df['ema75'].iloc[LAST]:
        return False
    # ギャップ（開き）フィルター：EMA25とEMA75が十分離れていないとエントリーしない
    if df['ema25'].iloc[LAST] - df['ema75'].iloc[LAST] < EMA_GAP_MIN:
        return False
    return True


def check_short_entry(df):
    return False


def check_long_exit(df):
    if len(df) < 2:
        return False
    # 条件1: ローソク足の安値がEMA25に触れた
    if df['low'].iloc[LAST] <= df['ema25'].iloc[LAST]:
        return True
    # 条件2: EMA25の傾きがなくなった（横ばい or 下向き）
    if df['ema25'].iloc[LAST] <= df['ema25'].iloc[PREV]:
        return True
    return False


def check_short_exit(df):
    return False
