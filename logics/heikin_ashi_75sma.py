"""
R氏 平均足75SMA手法
"""
import pandas as pd

NAME = "R氏 平均足75SMA"


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

    # 平均足の色が青→赤に変化
    prev_color = df['ha_color'].iloc[idx - 1]
    curr_color = df['ha_color'].iloc[idx]
    return prev_color == 1 and curr_color == -1


def check_short_exit(df, idx):
    """ショート決済条件"""
    if idx < 1:
        return False

    # 平均足の色が赤→青に変化
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
