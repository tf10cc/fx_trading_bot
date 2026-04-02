"""
FES ライブモニター

起動方法:
  streamlit run live/monitor.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from entry_logic import build_df, load_cassette, DEFAULT_INSTRUMENT

CASSETTE_PATH = Path(__file__).parent.parent / 'logics' / 'heikin_ashi_75sma.py'
LOG_FILE      = Path(__file__).parent / 'trade_log.csv'

st.set_page_config(page_title='FES モニター', layout='wide')
st.title('FES ライブモニター')
st.caption(f'最終更新: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC')

# ---- 現在の状態 ----
st.subheader('現在の状態')

cassette = load_cassette(str(CASSETTE_PATH))
df = build_df(DEFAULT_INSTRUMENT, cassette)

if df is not None:
    last  = df.iloc[-2]  # 最新確定足
    price = last['close']
    sma   = last['sma']
    ha_color = last['ha_color']

    col1, col2, col3, col4 = st.columns(4)
    col1.metric('銘柄',     DEFAULT_INSTRUMENT)
    col2.metric('現在価格', f'{price:.3f}')
    col3.metric('75SMA',   f'{sma:.3f}')
    col4.metric('価格の位置', 'SMAの上' if price > sma else 'SMAの下')

    st.write(f'平均足の色: {"🔵 青（BUY側）" if ha_color == 1 else "🔴 赤（SELL側）"}')
else:
    st.error('OANDAからデータを取得できませんでした')

# ---- トレード履歴 ----
st.subheader('トレード履歴')

if LOG_FILE.exists():
    log_df = pd.read_csv(LOG_FILE)
    st.dataframe(log_df, use_container_width=True)
else:
    st.info('まだトレードなし')

st.button('更新')
