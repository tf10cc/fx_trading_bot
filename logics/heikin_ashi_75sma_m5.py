"""
R氏 平均足75SMA手法（M5版 ツール動作確認用）
"""
import pandas as pd

NAME = "R氏 平均足75SMA M5 ②色継続もエントリー"
GRANULARITY = "M5"  # 足の種類（M5 = 5分足）
COUNT = 200         # 必要な取得本数（SMA75 + 傾き判定5本 + バッファ）

LAST = -1
PREV = LAST - 1


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


def check_long_entry(df):
    """ロングエントリー条件"""
    if len(df) < 2:
        return False

    # トレンドチェック（上昇トレンド）
    has_trend, trend_direction = _check_trend(df)
    if not has_trend or trend_direction != 'up':
        return False

    # 平均足が青（赤→青 または 青→青）
    curr_color = df['ha_color'].iloc[LAST]

    if curr_color == 1:
        # 平均足の実体下限がSMAより上
        ha_body_bottom = df['ha_body_bottom'].iloc[LAST]
        sma = df['sma'].iloc[LAST]
        if not pd.isna(sma) and ha_body_bottom > sma:
            return True

    return False


def check_short_entry(df):
    """ショートエントリー条件"""
    if len(df) < 2:
        return False

    # トレンドチェック（下降トレンド）
    has_trend, trend_direction = _check_trend(df)
    if not has_trend or trend_direction != 'down':
        return False

    # 平均足が赤（青→赤 または 赤→赤）
    curr_color = df['ha_color'].iloc[LAST]

    if curr_color == -1:
        # 平均足の実体上限がSMAより下
        ha_body_top = df['ha_body_top'].iloc[LAST]
        sma = df['sma'].iloc[LAST]
        if not pd.isna(sma) and ha_body_top < sma:
            return True

    return False


def check_long_exit(df):
    """ロング決済条件"""
    if len(df) < 2:
        return False

    # 平均足の色が青→赤に変化
    prev_color = df['ha_color'].iloc[PREV]
    curr_color = df['ha_color'].iloc[LAST]
    return prev_color == 1 and curr_color == -1


def check_short_exit(df):
    """ショート決済条件"""
    if len(df) < 2:
        return False

    # 平均足の色が赤→青に変化
    prev_color = df['ha_color'].iloc[PREV]
    curr_color = df['ha_color'].iloc[LAST]
    return prev_color == -1 and curr_color == 1


def _check_trend(df, lookback=5):
    """SMAの傾きを調べる"""
    if len(df) <= lookback:
        return False, None

    current_sma = df['sma'].iloc[LAST]
    past_sma = df['sma'].iloc[LAST - lookback]

    if pd.isna(current_sma) or pd.isna(past_sma):
        return False, None

    if current_sma > past_sma:
        return True, 'up'
    elif current_sma < past_sma:
        return True, 'down'
    else:
        return False, None
