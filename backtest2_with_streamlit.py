"""
R氏 平均足75SMA手法 バックテストシステム（Streamlit版）
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

# ========== 定数定義 ==========
STRATEGY_NAME = "R氏 平均足75SMA手法"

class BacktestEngine:
    """バックテストエンジン"""
    
    def __init__(self, csv_path, spread_pips=0, slippage_pips=0):
        """
        初期化
        
        Args:
            csv_path: CSVファイルパス
            spread_pips: スプレッド (pips) ※将来の拡張用
            slippage_pips: スリッページ (pips) ※将来の拡張用
        """
        self.csv_path = csv_path
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        
        # データ
        self.df = None
        
        # トレード記録
        self.trades = []
        self.current_position = None  # None, 'long', 'short'
        self.entry_time = None
        self.entry_price = None
        
        # パフォーマンス指標
        self.total_pips = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_win_pips = 0
        self.total_loss_pips = 0
        
    def load_data(self):
        """CSVファイルを読み込み"""
        self.df = pd.read_csv(self.csv_path)
        
        # 列名を小文字に統一
        self.df.columns = self.df.columns.str.lower()
        
        # UTCがあればtimeにリネーム
        if 'utc' in self.df.columns:
            self.df = self.df.rename(columns={'utc': 'time'})
        
        self.df['time'] = pd.to_datetime(self.df['time'], dayfirst=True)
        
    def calculate_sma(self, period=75):
        """単純移動平均を計算"""
        self.df['sma'] = self.df['close'].rolling(window=period).mean()
        
    def calculate_heikin_ashi(self):
        """平均足を計算"""
        # 平均足の終値
        ha_close = (self.df['open'] + self.df['high'] + self.df['low'] + self.df['close']) / 4
        
        # 平均足の始値
        ha_open = pd.Series(index=self.df.index, dtype=float)
        ha_open.iloc[0] = (self.df['open'].iloc[0] + self.df['close'].iloc[0]) / 2
        
        for i in range(1, len(self.df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
        
        # 平均足の高値と安値
        ha_high = pd.concat([self.df['high'], ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([self.df['low'], ha_open, ha_close], axis=1).min(axis=1)
        
        self.df['ha_open'] = ha_open
        self.df['ha_close'] = ha_close
        self.df['ha_high'] = ha_high
        self.df['ha_low'] = ha_low
        
    def calculate_ha_color(self):
        """平均足の色を判定（青=1, 赤=-1）"""
        self.df['ha_color'] = np.where(self.df['ha_close'] >= self.df['ha_open'], 1, -1)
        
    def calculate_ha_body(self):
        """平均足の実体の上下を計算"""
        self.df['ha_body_top'] = self.df[['ha_open', 'ha_close']].max(axis=1)
        self.df['ha_body_bottom'] = self.df[['ha_open', 'ha_close']].min(axis=1)
        
    def check_trend(self, idx, lookback=5):
        """トレンドをチェック"""
        if idx < lookback:
            return False, None
            
        current_sma = self.df['sma'].iloc[idx]
        past_sma = self.df['sma'].iloc[idx - lookback]
        
        if pd.isna(current_sma) or pd.isna(past_sma):
            return False, None
            
        if current_sma > past_sma:
            return True, 'up'
        elif current_sma < past_sma:
            return True, 'down'
        else:
            return False, None
            
    def check_long_entry(self, idx):
        """ロングエントリー条件"""
        if idx < 1:
            return False
            
        # トレンドチェック
        has_trend, trend_direction = self.check_trend(idx)
        if not has_trend or trend_direction != 'up':
            return False
            
        # 平均足の色が赤→青に変化
        prev_color = self.df['ha_color'].iloc[idx - 1]
        curr_color = self.df['ha_color'].iloc[idx]
        
        if prev_color == -1 and curr_color == 1:
            # 平均足の実体下限がSMAより上
            ha_body_bottom = self.df['ha_body_bottom'].iloc[idx]
            sma = self.df['sma'].iloc[idx]
            
            if not pd.isna(sma) and ha_body_bottom > sma:
                return True
                
        return False
        
    def check_short_entry(self, idx):
        """ショートエントリー条件"""
        if idx < 1:
            return False
            
        # トレンドチェック
        has_trend, trend_direction = self.check_trend(idx)
        if not has_trend or trend_direction != 'down':
            return False
            
        # 平均足の色が青→赤に変化
        prev_color = self.df['ha_color'].iloc[idx - 1]
        curr_color = self.df['ha_color'].iloc[idx]
        
        if prev_color == 1 and curr_color == -1:
            # 平均足の実体上限がSMAより下
            ha_body_top = self.df['ha_body_top'].iloc[idx]
            sma = self.df['sma'].iloc[idx]
            
            if not pd.isna(sma) and ha_body_top < sma:
                return True
                
        return False
        
    def check_long_exit(self, idx):
        """ロング決済条件"""
        if idx < 1:
            return False
            
        # 平均足の色が青→赤に変化
        prev_color = self.df['ha_color'].iloc[idx - 1]
        curr_color = self.df['ha_color'].iloc[idx]
        
        return prev_color == 1 and curr_color == -1
        
    def check_short_exit(self, idx):
        """ショート決済条件"""
        if idx < 1:
            return False
            
        # 平均足の色が赤→青に変化
        prev_color = self.df['ha_color'].iloc[idx - 1]
        curr_color = self.df['ha_color'].iloc[idx]
        
        return prev_color == -1 and curr_color == 1
        
    def enter_position(self, idx, direction):
        """エントリー"""
        self.current_position = direction
        self.entry_time = self.df['time'].iloc[idx]
        self.entry_price = self.df['open'].iloc[idx]
        
    def exit_position(self, idx):
        """決済"""
        exit_time = self.df['time'].iloc[idx]
        exit_price = self.df['open'].iloc[idx]
        
        # 損益計算
        if self.current_position == 'long':
            pips = (exit_price - self.entry_price) * 100
        else:  # short
            pips = (self.entry_price - exit_price) * 100
            
        # トレード記録
        self.trades.append({
            'entry_time': self.entry_time,
            'exit_time': exit_time,
            'direction': self.current_position,
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'pips': pips
        })
        
        # 統計更新
        self.total_pips += pips
        if pips > 0:
            self.win_count += 1
            self.total_win_pips += pips
        else:
            self.loss_count += 1
            self.total_loss_pips += abs(pips)
            
        # ポジションクリア
        self.current_position = None
        self.entry_time = None
        self.entry_price = None
        
    def run(self):
        """バックテスト実行"""
        self.load_data()
        self.calculate_sma()
        self.calculate_heikin_ashi()
        self.calculate_ha_color()
        self.calculate_ha_body()
        
        # 1本ずつ処理
        for idx in range(len(self.df)):
            if self.current_position is None:
                # エントリーチェック
                if self.check_long_entry(idx):
                    self.enter_position(idx, 'long')
                elif self.check_short_entry(idx):
                    self.enter_position(idx, 'short')
            else:
                # 決済チェック
                if self.current_position == 'long' and self.check_long_exit(idx):
                    self.exit_position(idx)
                elif self.current_position == 'short' and self.check_short_exit(idx):
                    self.exit_position(idx)
                    
    def calculate_metrics(self):
        """パフォーマンス指標を計算"""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = self.total_win_pips / self.win_count if self.win_count > 0 else 0
        avg_loss = self.total_loss_pips / self.loss_count if self.loss_count > 0 else 0
        
        profit_factor = self.total_win_pips / self.total_loss_pips if self.total_loss_pips > 0 else float('inf')
        
        # 最大ドローダウン
        cumulative_pips = []
        cum_sum = 0
        for trade in self.trades:
            cum_sum += trade['pips']
            cumulative_pips.append(cum_sum)
            
        max_dd = 0
        peak = cumulative_pips[0] if cumulative_pips else 0
        for pips in cumulative_pips:
            if pips > peak:
                peak = pips
            dd = peak - pips
            if dd > max_dd:
                max_dd = dd
                
        return {
            'total_pips': self.total_pips,
            'total_trades': total_trades,
            'win_count': self.win_count,
            'loss_count': self.loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_dd
        }

# ========== Streamlitアプリ ==========

st.set_page_config(page_title=STRATEGY_NAME, layout="wide")

st.title(f"📊 {STRATEGY_NAME} バックテスト可視化")

# サイドバー
st.sidebar.header("設定")

# CSVファイル選択
data_dir = Path("data")
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

# バックテスト実行ボタン
if st.sidebar.button("バックテスト実行", type="primary"):
    with st.spinner("バックテスト実行中..."):
        # バックテスト実行
        bt = BacktestEngine(str(csv_path))
        bt.run()
        metrics = bt.calculate_metrics()
        
        # 結果を session_state に保存
        st.session_state['bt'] = bt
        st.session_state['metrics'] = metrics

# 結果表示
if 'bt' in st.session_state and 'metrics' in st.session_state:
    bt = st.session_state['bt']
    metrics = st.session_state['metrics']
    
    # パフォーマンス指標
    st.header("📈 パフォーマンス指標")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("総損益", f"{metrics['total_pips']:.2f} pips")
    
    with col2:
        st.metric("取引回数", f"{metrics['total_trades']}回")
    
    with col3:
        st.metric("勝率", f"{metrics['win_rate']:.2f}%")
    
    with col4:
        st.metric("最大DD", f"{metrics['max_drawdown']:.2f} pips")
    
    with col5:
        st.metric("PF", f"{metrics['profit_factor']:.2f}")
    
    # チャート
    st.header("📊 チャート")
    
    fig = go.Figure()
    
    # ローソク足
    fig.add_trace(go.Candlestick(
        x=bt.df['time'],
        open=bt.df['open'],
        high=bt.df['high'],
        low=bt.df['low'],
        close=bt.df['close'],
        name='ローソク足',
        increasing_line_color='cyan',
        decreasing_line_color='pink'
    ))
    
    # 75SMA
    fig.add_trace(go.Scatter(
        x=bt.df['time'],
        y=bt.df['sma'],
        mode='lines',
        name='75SMA',
        line=dict(color='orange', width=2)
    ))
    
    # エントリー・決済マーカー
    for trade in bt.trades:
        # エントリー
        color = 'blue' if trade['direction'] == 'long' else 'red'
        symbol = 'triangle-up' if trade['direction'] == 'long' else 'triangle-down'
        
        fig.add_trace(go.Scatter(
            x=[trade['entry_time']],
            y=[trade['entry_price']],
            mode='markers',
            name=f"Entry ({trade['direction']})",
            marker=dict(size=12, color=color, symbol=symbol),
            showlegend=False
        ))
        
        # 決済
        exit_color = 'green' if trade['pips'] > 0 else 'red'
        
        fig.add_trace(go.Scatter(
            x=[trade['exit_time']],
            y=[trade['exit_price']],
            mode='markers',
            name=f"Exit ({trade['pips']:.1f}p)",
            marker=dict(size=10, color=exit_color, symbol='circle'),
            showlegend=False
        ))
    
    fig.update_layout(
        title=f"{STRATEGY_NAME} バックテスト結果",
        xaxis_title="日時",
        yaxis_title="価格",
        height=600,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 取引一覧
    st.header("📋 取引一覧")
    
    if bt.trades:
        trades_df = pd.DataFrame(bt.trades)
        trades_df['cumulative_pips'] = trades_df['pips'].cumsum()
        
        st.dataframe(
            trades_df.style.format({
                'entry_price': '{:.3f}',
                'exit_price': '{:.3f}',
                'pips': '{:.2f}',
                'cumulative_pips': '{:.2f}'
            }),
            use_container_width=True
        )
    else:
        st.info("取引がありません")