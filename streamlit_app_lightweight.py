"""
R氏 平均足75SMA手法 バックテストシステム（TradingView Lightweight Charts版）
"""

import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
from pathlib import Path
import json

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
        """CSVファイルを読み込み、標準フォーマットに変換"""
        self.df = pd.read_csv(self.csv_path)
        
        # 列名を標準化（<>を除去、小文字に統一）
        self.df.columns = self.df.columns.str.replace('<', '').str.replace('>', '').str.lower()
        
        # フォーマット判定と変換
        if 'ticker' in self.df.columns and 'dtyyyymmdd' in self.df.columns:
            # Forex Tester形式
            self.df = self._convert_forex_tester_format()
        elif 'utc' in self.df.columns:
            # 既存ドル円形式
            self.df = self._convert_standard_format()
        elif 'time' in self.df.columns:
            # 標準形式（そのまま使用）
            self.df['time'] = pd.to_datetime(self.df['time'], dayfirst=True)
        else:
            raise ValueError("不明なCSVフォーマットです")
    
    def _convert_forex_tester_format(self):
        """Forex Tester形式を標準フォーマットに変換"""
        # 日付と時刻を結合
        df_converted = pd.DataFrame()
        
        # DTYYYYMMDD + TIME を datetime に変換
        date_str = self.df['dtyyyymmdd'].astype(str)
        time_str = self.df['time'].astype(str).str.zfill(4)  # 4桁に0埋め
        datetime_str = date_str + ' ' + time_str
        
        df_converted['datetime'] = pd.to_datetime(datetime_str, format='%Y%m%d %H%M')
        df_converted['open'] = self.df['open']
        df_converted['high'] = self.df['high']
        df_converted['low'] = self.df['low']
        df_converted['close'] = self.df['close']
        df_converted['volume'] = self.df['vol']
        
        # timeカラムにリネーム（既存ロジック互換性）
        df_converted = df_converted.rename(columns={'datetime': 'time'})
        
        return df_converted
    
    def _convert_standard_format(self):
        """既存ドル円形式を標準フォーマットに変換"""
        df_converted = pd.DataFrame()
        
        # UTCカラムをdatetimeに変換
        df_converted['time'] = pd.to_datetime(self.df['utc'], dayfirst=True)
        df_converted['open'] = self.df['open']
        df_converted['high'] = self.df['high']
        df_converted['low'] = self.df['low']
        df_converted['close'] = self.df['close']
        df_converted['volume'] = self.df['volume']
        
        return df_converted
        
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
        if idx + 1 >= len(self.df):
            return
        
        self.current_position = direction
        self.entry_time = self.df['time'].iloc[idx + 1]
        self.entry_price = self.df['open'].iloc[idx + 1]
        
    def exit_position(self, idx):
        """決済"""
        if idx + 1 >= len(self.df):
            return
        
        exit_time = self.df['time'].iloc[idx + 1]
        exit_price = self.df['open'].iloc[idx + 1]
        
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
        
        # 1本ずつ処理（CLI版と同じ順序：決済→エントリー）
        for idx in range(len(self.df)):
            # 決済チェック（先に決済）
            if self.current_position == 'long' and self.check_long_exit(idx):
                self.exit_position(idx)
            elif self.current_position == 'short' and self.check_short_exit(idx):
                self.exit_position(idx)
            
            # エントリーチェック（決済後にエントリー）
            if self.current_position is None:
                if self.check_long_entry(idx):
                    self.enter_position(idx, 'long')
                elif self.check_short_entry(idx):
                    self.enter_position(idx, 'short')
        
        # 未決済ポジションの強制決済
        if self.current_position is not None and len(self.df) > 0:
            last_idx = len(self.df) - 1
            exit_price = self.df['close'].iloc[last_idx]
            exit_time = self.df['time'].iloc[last_idx]
            
            if self.current_position == 'long':
                pips = (exit_price - self.entry_price) * 100
            else:
                pips = (self.entry_price - exit_price) * 100
            
            trade = {
                'entry_time': self.entry_time,
                'exit_time': exit_time,
                'direction': self.current_position,
                'entry_price': self.entry_price,
                'exit_price': exit_price,
                'pips': pips
            }
            self.trades.append(trade)
            
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

def create_lightweight_chart(df, trades, chart_height=600, jump_to=None):
    """TradingView Lightweight Chartsを生成"""
    
    # 平均足データを準備（UNIXタイムスタンプに変換）
    candlestick_data = []
    for idx, row in df.iterrows():
        if pd.notna(row['ha_open']) and pd.notna(row['ha_high']) and pd.notna(row['ha_low']) and pd.notna(row['ha_close']):
            try:
                candlestick_data.append({
                    'time': int(row['time'].timestamp()),  # UNIXタイムスタンプに変更
                    'open': round(float(row['ha_open']), 5),
                    'high': round(float(row['ha_high']), 5),
                    'low': round(float(row['ha_low']), 5),
                    'close': round(float(row['ha_close']), 5)
                })
            except:
                continue
    
    # 75SMAデータを準備
    sma_data = []
    for idx, row in df.iterrows():
        if pd.notna(row['sma']):
            try:
                sma_data.append({
                    'time': int(row['time'].timestamp()),  # UNIXタイムスタンプに変更
                    'value': round(float(row['sma']), 5)
                })
            except:
                continue
    
    # マーカーデータを準備（シンプルに記号のみ）
    markers = []
    for trade in trades:
        # エントリーマーカー
        entry_time = int(trade['entry_time'].timestamp()) if hasattr(trade['entry_time'], 'timestamp') else int(pd.Timestamp(trade['entry_time']).timestamp())
        exit_time = int(trade['exit_time'].timestamp()) if hasattr(trade['exit_time'], 'timestamp') else int(pd.Timestamp(trade['exit_time']).timestamp())
        
        # エントリー（↑ロング、↓ショート）
        markers.append({
            'time': entry_time,
            'position': 'belowBar' if trade['direction'] == 'long' else 'aboveBar',
            'color': '#2196F3',
            'shape': 'arrowUp' if trade['direction'] == 'long' else 'arrowDown',
            'text': ''
        })
        
        # 決済：利確＝circle（緑）、損切り＝square（赤）。テキストは空にして二重表示を防ぐ
        is_profit = trade['pips'] > 0
        markers.append({
            'time': exit_time,
            'position': 'aboveBar' if trade['direction'] == 'long' else 'belowBar',
            'color': '#4CAF50' if is_profit else '#f23645',
            'shape': 'circle' if is_profit else 'square',
            'text': ''
        })
    
    # JSONに変換
    candlestick_json = json.dumps(candlestick_data)
    sma_json = json.dumps(sma_data)
    markers_json = json.dumps(markers)
    
    # HTMLコード生成
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 0; }}
            #chart {{ width: 100%; height: {chart_height}px; }}
        </style>
    </head>
    <body>
        <div id="chart"></div>
        <script>
            // iframeでも動作するように少し待機
            setTimeout(function() {{
                console.log('Starting chart initialization...');
                console.log('Candle data count:', {len(candlestick_data)});
                console.log('SMA data count:', {len(sma_data)});
                console.log('Markers count:', {len(markers)});
                
                const chartElement = document.getElementById('chart');
                if (!chartElement) {{
                    console.error('Chart element not found!');
                    return;
                }}
                
                const chart = LightweightCharts.createChart(chartElement, {{
                width: 1400,  // 固定幅に変更
                height: {chart_height},
                layout: {{
                    background: {{ color: '#1e1e1e' }},
                    textColor: '#d1d4dc',
                }},
                localization: {{
                    timeFormatter: (businessDayOrTimestamp) => {{
                        const date = new Date(businessDayOrTimestamp * 1000);
                        const year = date.getFullYear();
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const hours = String(date.getHours()).padStart(2, '0');
                        const minutes = String(date.getMinutes()).padStart(2, '0');
                        return `${{year}}/${{month}}/${{day}} ${{hours}}:${{minutes}}`;
                    }}
                }},
                grid: {{
                    vertLines: {{ color: '#2B2B43' }},
                    horzLines: {{ color: '#363C4E' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                }},
                rightPriceScale: {{
                    borderColor: '#2B2B43',
                }},
                timeScale: {{
                    borderColor: '#2B2B43',
                    timeVisible: true,
                    secondsVisible: false,
                    localization: {{
                        locale: 'en-US',
                        dateFormat: 'yyyy/MM/dd',
                    }},
                }},
            }});

            console.log('Chart created');

            // 平均足チャート
            const candlestickSeries = chart.addCandlestickSeries({{
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderUpColor: '#26a69a',
                borderDownColor: '#ef5350',
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            }});
            
            const candleData = {candlestick_json};
            console.log('First 3 candles:', candleData.slice(0, 3));
            candlestickSeries.setData(candleData);
            console.log('Candlestick data set');

            // 75SMAライン
            const lineSeries = chart.addLineSeries({{
                color: '#ff9800',
                lineWidth: 2,
                title: '75SMA',
            }});
            
            const smaData = {sma_json};
            console.log('First 3 SMA:', smaData.slice(0, 3));
            lineSeries.setData(smaData);
            console.log('SMA data set');

            // マーカー
            const markers = {markers_json};
            console.log('Markers:', markers.slice(0, 5));
            candlestickSeries.setMarkers(markers);
            console.log('Markers set');

            // ウィンドウリサイズ対応
            window.addEventListener('resize', () => {{
                try {{
                    chart.applyOptions({{ width: 1400 }});
                }} catch(e) {{
                    console.error('Resize error:', e);
                }}
            }});

            // 自動フィット（エラーハンドリング追加）
            try {{
                // 日時ジャンプが指定されている場合
                const jumpTimestamp = {int(pd.Timestamp(jump_to).timestamp()) if jump_to and jump_to is not None else 'null'};
                console.log('=== DEBUG INFO ===');
                console.log('Jump timestamp:', jumpTimestamp);
                
                if (jumpTimestamp !== null) {{
                    console.log('Jump date (UTC):', new Date(jumpTimestamp * 1000).toUTCString());
                    console.log('Jump date (local):', new Date(jumpTimestamp * 1000).toLocaleString());
                    
                    // データの範囲を確認
                    const firstCandle = candleData[0];
                    const lastCandle = candleData[candleData.length - 1];
                    console.log('Data range:', {{
                        first: new Date(firstCandle.time * 1000).toLocaleString(),
                        last: new Date(lastCandle.time * 1000).toLocaleString()
                    }});
                    
                    // ジャンプ先の前後24時間を表示範囲に設定（2日分）
                    const twentyFourHoursSeconds = 24 * 60 * 60;
                    const fromTime = jumpTimestamp - twentyFourHoursSeconds;
                    const toTime = jumpTimestamp + twentyFourHoursSeconds;
                    
                    console.log('Setting visible range:', {{
                        from: new Date(fromTime * 1000).toLocaleString(),
                        to: new Date(toTime * 1000).toLocaleString()
                    }});
                    
                    chart.timeScale().setVisibleRange({{
                        from: fromTime,
                        to: toTime,
                    }});
                    
                    console.log('✅ Jump completed!');
                }} else {{
                    console.log('No jump target, fitting content');
                    chart.timeScale().fitContent();
                }}
                console.log('=== END DEBUG ===');
            }} catch(e) {{
                console.error('❌ Error:', e);
            }}
            }}, 100);  // 100ms待機
        </script>
    </body>
    </html>
    """
    
    return html_code

# ========== Streamlitアプリ ==========

st.set_page_config(page_title=STRATEGY_NAME, layout="wide")

st.title(f"📊 {STRATEGY_NAME} バックテスト結果")
st.caption("Powered by TradingView Lightweight Charts")

# サイドバー
st.sidebar.header("設定")

# CSVファイル選択
base_dir = Path(__file__).resolve().parent
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

# バックテスト実行ボタン（上に移動）
if st.sidebar.button("バックテスト実行", type="primary"):
    with st.spinner("バックテスト実行中..."):
        # バックテスト実行
        bt = BacktestEngine(str(csv_path))
        bt.run()
        metrics = bt.calculate_metrics()
        
        # 結果を session_state に保存
        st.session_state['bt'] = bt
        st.session_state['metrics'] = metrics

# 日時ジャンプ設定
# チャート高さは固定（600px）
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
        # 日時を結合してsession_stateに保存
        jump_datetime = pd.Timestamp.combine(jump_date, jump_time)
        st.session_state['jump_to'] = jump_datetime
        st.sidebar.success(f"ジャンプ設定: {jump_datetime}")
        # ページを再実行してチャートを再描画
        st.rerun()
    else:
        st.sidebar.warning("日付と時刻を選択してください")

# デバッグ情報
st.sidebar.header("🐛 デバッグ情報")
if 'jump_to' in st.session_state:
    st.sidebar.info(f"現在のジャンプ先: {st.session_state['jump_to']}")
    st.sidebar.code(f"タイムスタンプ: {int(pd.Timestamp(st.session_state['jump_to']).timestamp())}")
else:
    st.sidebar.info("ジャンプ先: 未設定")
    
if 'bt' in st.session_state:
    st.sidebar.info(f"データ期間: {st.session_state['bt'].df['time'].min()} ～ {st.session_state['bt'].df['time'].max()}")
else:
    st.sidebar.info("バックテスト: 未実行")

# 結果表示
if 'bt' in st.session_state and 'metrics' in st.session_state:
    bt = st.session_state['bt']
    metrics = st.session_state['metrics']
    
    # パフォーマンス指標
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
    
    # Lightweight Chartsチャート
    st.subheader("📈 チャート（平均足 + 75SMA）")
    
    # ジャンプ先の日時を取得
    jump_to = st.session_state.get('jump_to', None)
    
    html_code = create_lightweight_chart(bt.df, bt.trades, chart_height, jump_to)
    components.html(html_code, height=chart_height + 50, scrolling=True)
    
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
            width='stretch'
        )
    else:
        st.info("取引がありません")
else:
    st.info("👈 サイドバーから「バックテスト実行」ボタンを押してください")