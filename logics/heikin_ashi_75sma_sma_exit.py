"""
平均足75SMA手法（SMA割れ決済版）
エントリー：R氏手法と同じ
決済：ha_closeがSMAを下回ったら（ロング）/ 上回ったら（ショート）
"""
import pandas as pd

NAME = "平均足75SMA H1（75SMA割れ決済・ADXあり）"
GRANULARITY = "H1"
COUNT = 200

LAST = -1
PREV = LAST - 1

STOP_LOSS_PIPS = 30
TREND_THRESHOLD = 0
ADX_PERIOD    = 14
ADX_THRESHOLD = 25
BB_PERIOD     = 20
BB_STD        = 2

plot_config = {
    "main_plot": {
        "bb_upper": {"color": "#555555", "lineWidth": 1, "title": "BB Upper"},
        "bb_mid":   {"color": "#444444", "lineWidth": 1, "title": "BB Mid"},
        "bb_lower": {"color": "#555555", "lineWidth": 1, "title": "BB Lower"},
    }
}


def populate_indicators(df):
    """平均足・75SMA・ADXを計算してdfに追加して返す"""
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
    df['ha_open']        = ha_open
    df['ha_close']       = ha_close
    df['ha_high']        = pd.concat([df['high'], ha_open, ha_close], axis=1).max(axis=1)
    df['ha_low']         = pd.concat([df['low'],  ha_open, ha_close], axis=1).min(axis=1)
    df['ha_color']       = (df['ha_close'] >= df['ha_open']).map(lambda x: 1 if x else -1)
    df['ha_body_top']    = df[['ha_open', 'ha_close']].max(axis=1)
    df['ha_body_bottom'] = df[['ha_open', 'ha_close']].min(axis=1)
    df['sma']            = df['close'].rolling(window=75).mean()

    # ボリンジャーバンド計算
    bb_mid             = df['close'].rolling(window=BB_PERIOD).mean()
    bb_std             = df['close'].rolling(window=BB_PERIOD).std()
    df['bb_mid']       = bb_mid
    df['bb_upper']     = bb_mid + BB_STD * bb_std
    df['bb_lower']     = bb_mid - BB_STD * bb_std

    # ADX計算
    n = ADX_PERIOD
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    plus_dm  = (high - high.shift(1)).clip(lower=0).where((high - high.shift(1)) > (low.shift(1) - low), 0)
    minus_dm = (low.shift(1) - low).clip(lower=0).where((low.shift(1) - low) > (high - high.shift(1)), 0)
    atr      = tr.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/n, min_periods=n, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/n, min_periods=n, adjust=False).mean() / atr
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['adx'] = dx.ewm(alpha=1/n, min_periods=n, adjust=False).mean()

    return df


def check_long_entry(df):
    """ロングエントリー条件"""
    if len(df) < 2:
        return False

    adx = df['adx'].iloc[LAST]
    if pd.isna(adx) or adx < ADX_THRESHOLD:
        return False

    has_trend, trend_direction = _check_trend(df)
    if not has_trend or trend_direction != 'up':
        return False

    prev_color = df['ha_color'].iloc[PREV]
    curr_color = df['ha_color'].iloc[LAST]

    if prev_color == -1 and curr_color == 1:
        ha_body_bottom = df['ha_body_bottom'].iloc[LAST]
        sma = df['sma'].iloc[LAST]
        if not pd.isna(sma) and ha_body_bottom > sma:
            return True

    return False


def check_short_entry(df):
    """ショートエントリー条件"""
    if len(df) < 2:
        return False

    adx = df['adx'].iloc[LAST]
    if pd.isna(adx) or adx < ADX_THRESHOLD:
        return False

    has_trend, trend_direction = _check_trend(df)
    if not has_trend or trend_direction != 'down':
        return False

    prev_color = df['ha_color'].iloc[PREV]
    curr_color = df['ha_color'].iloc[LAST]

    if prev_color == 1 and curr_color == -1:
        ha_body_top = df['ha_body_top'].iloc[LAST]
        sma = df['sma'].iloc[LAST]
        if not pd.isna(sma) and ha_body_top < sma:
            return True

    return False


def check_long_exit(df):
    """ロング決済条件：ha_closeがSMAを下回ったら決済"""
    if len(df) < 1:
        return False

    ha_close = df['ha_close'].iloc[LAST]
    sma = df['sma'].iloc[LAST]

    if pd.isna(sma):
        return False

    return ha_close < sma


def check_short_exit(df):
    """ショート決済条件：ha_closeがSMAを上回ったら決済"""
    if len(df) < 1:
        return False

    ha_close = df['ha_close'].iloc[LAST]
    sma = df['sma'].iloc[LAST]

    if pd.isna(sma):
        return False

    return ha_close > sma


def _check_trend(df, lookback=5):
    """SMAの傾きを調べる"""
    if len(df) <= lookback:
        return False, None

    current_sma = df['sma'].iloc[LAST]
    past_sma = df['sma'].iloc[LAST - lookback]

    if pd.isna(current_sma) or pd.isna(past_sma):
        return False, None

    diff = current_sma - past_sma

    if diff > TREND_THRESHOLD:
        return True, 'up'
    elif diff < -TREND_THRESHOLD:
        return True, 'down'
    else:
        return False, None
