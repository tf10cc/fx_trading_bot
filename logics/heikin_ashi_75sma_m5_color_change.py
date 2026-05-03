"""
R氏 平均足75SMA手法（M5版 色変化のみエントリー）
"""
import pandas as pd

NAME = "R氏 平均足75SMA M5 ①色変化のみ（赤→青・青→赤）"
GRANULARITY = "M5"
COUNT = 200


def populate_indicators(df):
    """平均足・75SMAを計算してdfに追加して返す"""
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
    return df


def check_long_entry(df, idx):
    """ロングエントリー条件"""
    if idx < 1:
        return False

    # トレンドチェック（上昇トレンド）
    has_trend, trend_direction = _check_trend(df, idx)
    if not has_trend or trend_direction != 'up':
        return False

    # 平均足の色が赤→青に変化
    prev_color = df['ha_color'].iloc[idx - 1]
    curr_color = df['ha_color'].iloc[idx]

    if prev_color == -1 and curr_color == 1:
        # 平均足の実体下限がSMAより上
        ha_body_bottom = df['ha_body_bottom'].iloc[idx]
        sma = df['sma'].iloc[idx]
        if not pd.isna(sma) and ha_body_bottom > sma:
            return True

    return False


def check_short_entry(df, idx):
    """ショートエントリー条件"""
    if idx < 1:
        return False

    # トレンドチェック（下降トレンド）
    has_trend, trend_direction = _check_trend(df, idx)
    if not has_trend or trend_direction != 'down':
        return False

    # 平均足の色が青→赤に変化
    prev_color = df['ha_color'].iloc[idx - 1]
    curr_color = df['ha_color'].iloc[idx]

    if prev_color == 1 and curr_color == -1:
        # 平均足の実体上限がSMAより下
        ha_body_top = df['ha_body_top'].iloc[idx]
        sma = df['sma'].iloc[idx]
        if not pd.isna(sma) and ha_body_top < sma:
            return True

    return False


def check_long_exit(df, idx):
    """ロング決済条件"""
    if idx < 1:
        return False

    prev_color = df['ha_color'].iloc[idx - 1]
    curr_color = df['ha_color'].iloc[idx]
    return prev_color == 1 and curr_color == -1


def check_short_exit(df, idx):
    """ショート決済条件"""
    if idx < 1:
        return False

    prev_color = df['ha_color'].iloc[idx - 1]
    curr_color = df['ha_color'].iloc[idx]
    return prev_color == -1 and curr_color == 1


def _check_trend(df, idx, lookback=5):
    """SMAの傾きを調べる"""
    if idx < lookback:
        return False, None

    current_sma = df['sma'].iloc[idx]
    past_sma = df['sma'].iloc[idx - lookback]

    if pd.isna(current_sma) or pd.isna(past_sma):
        return False, None

    if current_sma > past_sma:
        return True, 'up'
    elif current_sma < past_sma:
        return True, 'down'
    else:
        return False, None
