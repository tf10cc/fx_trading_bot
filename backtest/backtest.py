"""
FES — Fushimi EA System バックテストシステム（TradingView Lightweight Charts版）
"""

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from pathlib import Path
import importlib.util

from backtest_engine import BacktestEngine
from backtest_chart import create_lightweight_chart, SMA_PERIOD

# ========== 定数定義 ==========
STRATEGY_NAME = "R氏 平均足75SMA手法"

# ========== Streamlitアプリ ==========

st.set_page_config(page_title=STRATEGY_NAME, layout="wide")

st.title(f"📊 {STRATEGY_NAME} バックテスト結果")
st.caption("Powered by TradingView Lightweight Charts")

# サイドバー
st.sidebar.header("設定")

# CSVファイル選択
base_dir = Path(__file__).resolve().parent.parent
data_dir = base_dir / "data"
if data_dir.exists():
    csv_files = list(data_dir.glob("*.csv"))
    csv_names = [f.name for f in csv_files]

    if csv_names:
        selected_file = st.sidebar.selectbox("CSVファイルを選択", csv_names)
        csv_path = data_dir / selected_file
    else:
        st.error("dataフォルダにCSVファイルが見つかりません")
        st.stop()
else:
    st.error("dataフォルダが見つかりません")
    st.stop()

# ロジック選択
logics_dir = base_dir / "logics"
logic_files = sorted(logics_dir.glob("*.py")) if logics_dir.exists() else []

def load_logic_module(path):
    spec = importlib.util.spec_from_file_location("logic", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

logic_modules = {f.stem: load_logic_module(f) for f in logic_files}
logic_display_names = {f.stem: getattr(load_logic_module(f), 'NAME', f.stem) for f in logic_files}

if not logic_modules:
    st.error("logicsフォルダにロジックファイルが見つかりません")
    st.stop()

selected_logic_key = st.sidebar.selectbox(
    "ロジックを選択",
    list(logic_modules.keys()),
    format_func=lambda k: logic_display_names[k]
)
selected_logic = logic_modules[selected_logic_key]

# pip換算タイプ選択
pip_type_options = {
    "×1　USD（Gold / Silver / 原油など）": (1, "USD"),
    "×100　pips（USD/JPY等）": (100, "pips"),
    "×10000　pips（EUR/USD等）": (10000, "pips"),
}

def detect_pip_type(filename):
    name = filename.lower()
    if any(x in name for x in ['gold', 'xau', 'silver', 'xag', 'oil', 'wti', 'cl']):
        return "×1　USD（Gold / Silver / 原油など）"
    elif 'jpy' in name:
        return "×100　pips（USD/JPY等）"
    else:
        return "×100　pips（USD/JPY等）"

pip_type_names = list(pip_type_options.keys())
auto_detected = detect_pip_type(selected_file)
default_index = pip_type_names.index(auto_detected)
selected_pip_type = st.sidebar.selectbox("pip換算タイプ", pip_type_names, index=default_index)
pip_multiplier, pip_unit = pip_type_options[selected_pip_type]

# バックテスト実行ボタン
if st.sidebar.button("バックテスト実行", type="primary"):
    with st.spinner("バックテスト実行中..."):
        bt = BacktestEngine(str(csv_path), logic_module=selected_logic, pip_multiplier=pip_multiplier, pip_unit=pip_unit)
        bt.run()
        metrics = bt.calculate_metrics()

        # 結果を session_state に保存
        st.session_state['bt'] = bt
        st.session_state['metrics'] = metrics

# 日時ジャンプ設定
chart_height = 600
st.sidebar.header("日時ジャンプ")
jump_date = st.sidebar.date_input(
    "日付を選択",
    value=None,
    help="チャートをこの日付にジャンプします"
)
jump_time = st.sidebar.time_input(
    "時刻を選択",
    value=None,
    help="ジャンプ先の時刻"
)
if st.sidebar.button("この日時にジャンプ", type="secondary"):
    if 'bt' not in st.session_state:
        st.sidebar.error("先に「バックテスト実行」を押してください")
    elif jump_date and jump_time:
        jump_datetime = pd.Timestamp.combine(jump_date, jump_time)
        st.session_state['jump_to'] = jump_datetime
        st.sidebar.success(f"ジャンプ設定: {jump_datetime}")
        st.rerun()
    else:
        st.sidebar.warning("日付と時刻を選択してください")

# 結果表示
if 'bt' in st.session_state and 'metrics' in st.session_state:
    bt = st.session_state['bt']
    metrics = st.session_state['metrics']

    # パフォーマンス指標
    col1, col2, col3, col4, col5 = st.columns(5)

    unit = bt.pip_unit
    with col1:
        st.metric("総損益", f"{metrics['total_pips']:.2f} {unit}")
    with col2:
        st.metric("取引回数", f"{metrics['total_trades']}回")
    with col3:
        st.metric("勝率", f"{metrics['win_rate']:.2f}%")
    with col4:
        st.metric("最大DD", f"{metrics['max_drawdown']:.2f} {unit}")
    with col5:
        st.metric("PF", f"{metrics['profit_factor']:.2f}")

    # Lightweight Chartsチャート
    st.subheader(f"📈 チャート（平均足 + {SMA_PERIOD}SMA）")

    jump_to = st.session_state.get('jump_to', None)

    html_code = create_lightweight_chart(bt.df, bt.trades, chart_height, jump_to, bt.pip_unit)
    components.html(html_code, height=chart_height + 420, scrolling=True)
else:
    st.info("👈 サイドバーから「バックテスト実行」ボタンを押してください")
