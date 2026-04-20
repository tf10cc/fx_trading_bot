"""
FES — Fushimi EA System バックテストシステム（TradingView Lightweight Charts版）
"""

import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
from pathlib import Path
import json
import calendar
import importlib.util

# ========== 定数定義 ==========
STRATEGY_NAME = "R氏 平均足75SMA手法"
SMA_PERIOD    = 75

# カラー定数
COLOR_PROFIT       = '#4CAF50'  # 利益・プラス（緑）
COLOR_LOSS         = '#f23645'  # 損失・マイナス（赤）
COLOR_LONG         = '#26a69a'  # ロング・エントリー方向（緑）
COLOR_SHORT        = '#ef5350'  # ショート・決済方向（赤）
COLOR_ENTRY_MARKER = '#2196F3'  # エントリーマーカー（青）
COLOR_CLICK_LINE   = '#ffff00'  # クリック縦線（黄）

class BacktestEngine:
    """バックテストエンジン"""
    
    def __init__(self, csv_path, logic_module, spread_pips=0, slippage_pips=0, pip_multiplier=100, pip_unit="pips"):
        """
        初期化

        Args:
            csv_path: CSVファイルパス
            spread_pips: スプレッド (pips) ※将来の拡張用
            slippage_pips: スリッページ (pips) ※将来の拡張用
            pip_multiplier: pips換算倍率（JPYペア=100, Gold=1, EURペア=10000）
            pip_unit: 表示単位
        """
        self.csv_path = csv_path
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.pip_multiplier = pip_multiplier
        self.pip_unit = pip_unit
        self.logic_module = logic_module

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
        
    def calculate_sma(self, period=SMA_PERIOD):
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
        
    def check_long_entry(self, idx):
        return self.logic_module.check_long_entry(self.df, idx)

    def check_short_entry(self, idx):
        return self.logic_module.check_short_entry(self.df, idx)

    def check_long_exit(self, idx):
        return self.logic_module.check_long_exit(self.df, idx)

    def check_short_exit(self, idx):
        return self.logic_module.check_short_exit(self.df, idx)
        
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
            pips = (exit_price - self.entry_price) * self.pip_multiplier
        else:  # short
            pips = (self.entry_price - exit_price) * self.pip_multiplier
            
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
                pips = (exit_price - self.entry_price) * self.pip_multiplier
            else:
                pips = (self.entry_price - exit_price) * self.pip_multiplier
            
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

def create_lightweight_chart(df, trades, chart_height=600, jump_to=None, pip_unit='pips'):
    """TradingView Lightweight Chartsを生成"""
    
    # 平均足データを準備（UNIXタイムスタンプに変換）
    candlestick_data = []
    for idx, row in df.iterrows():
        if pd.notna(row['ha_open']) and pd.notna(row['ha_high']) and pd.notna(row['ha_low']) and pd.notna(row['ha_close']):
            try:
                candlestick_data.append({
                    'time': calendar.timegm(row['time'].timetuple()),  # CSVの時刻をそのまま使用
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
                    'time': calendar.timegm(row['time'].timetuple()),  # CSVの時刻をそのまま使用
                    'value': round(float(row['sma']), 5)
                })
            except:
                continue
    
    # マーカーデータを準備（シンプルに記号のみ）
    markers = []
    for trade in trades:
        # エントリーマーカー
        entry_time = calendar.timegm(pd.Timestamp(trade['entry_time']).timetuple())
        exit_time = calendar.timegm(pd.Timestamp(trade['exit_time']).timetuple())
        
        # エントリー（↑ロング、↓ショート）
        markers.append({
            'time': entry_time,
            'position': 'belowBar' if trade['direction'] == 'long' else 'aboveBar',
            'color': COLOR_ENTRY_MARKER,
            'shape': 'arrowUp' if trade['direction'] == 'long' else 'arrowDown',
            'text': ''
        })

        # 決済：利確＝circle（緑）、損切り＝square（赤）
        is_profit = trade['pips'] > 0
        markers.append({
            'time': exit_time,
            'position': 'aboveBar' if trade['direction'] == 'long' else 'belowBar',
            'color': COLOR_PROFIT if is_profit else COLOR_LOSS,
            'shape': 'circle' if is_profit else 'square',
            'text': ''
        })
    
    # 取引一覧テーブル行 + JavaScript用データをまとめて生成
    cum_pips = 0
    table_rows_html = ""
    trades_for_js = []
    for i, trade in enumerate(trades):
        cum_pips  += trade['pips']
        entry_ts   = calendar.timegm(pd.Timestamp(trade['entry_time']).timetuple())
        exit_ts    = calendar.timegm(pd.Timestamp(trade['exit_time']).timetuple())
        pips_color = COLOR_PROFIT if trade['pips'] > 0 else COLOR_LOSS
        cum_color  = COLOR_PROFIT if cum_pips >= 0 else COLOR_LOSS
        dir_color  = COLOR_LONG if trade['direction'] == 'long' else COLOR_SHORT
        dir_label  = 'Long' if trade['direction'] == 'long' else 'Short'
        table_rows_html += f"""<tr data-entry-ts="{entry_ts}">
            <td>{i}</td>
            <td>{trade['entry_time']}</td>
            <td>{trade['exit_time']}</td>
            <td style="color:{dir_color}">{dir_label}</td>
            <td>{trade['entry_price']:.3f}</td>
            <td>{trade['exit_price']:.3f}</td>
            <td style="color:{pips_color}">{trade['pips']:.2f}</td>
            <td style="color:{cum_color}">{cum_pips:.2f}</td>
        </tr>"""
        # 足のhigh/lowを取得（ひげ基準でマーカーを配置するため）
        entry_bar = df[df['time'] == pd.Timestamp(trade['entry_time'])]
        exit_bar  = df[df['time'] == pd.Timestamp(trade['exit_time'])]
        entry_low  = float(entry_bar['ha_low'].iloc[0])  if not entry_bar.empty  else trade['entry_price']
        entry_high = float(entry_bar['ha_high'].iloc[0]) if not entry_bar.empty  else trade['entry_price']
        exit_low   = float(exit_bar['ha_low'].iloc[0])   if not exit_bar.empty   else trade['exit_price']
        exit_high  = float(exit_bar['ha_high'].iloc[0])  if not exit_bar.empty   else trade['exit_price']
        trades_for_js.append({
            'entry_ts':    entry_ts,
            'exit_ts':     exit_ts,
            'entry_price': trade['entry_price'],
            'exit_price':  trade['exit_price'],
            'profitable':  bool(trade['pips'] > 0),
            'direction':   trade['direction'],
            'entry_low':   entry_low,
            'entry_high':  entry_high,
            'exit_low':    exit_low,
            'exit_high':   exit_high,
        })

    # JSONに変換
    candlestick_json = json.dumps(candlestick_data)
    sma_json         = json.dumps(sma_data)
    trades_js_json   = json.dumps(trades_for_js)
    markers_json     = json.dumps(markers)
    
    # HTMLコード生成
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background: #1e1e1e; }}
            #chart {{ width: 100%; height: {chart_height}px; }}
            #trade-table-container {{
                max-height: 350px;
                overflow-y: auto;
                margin-top: 8px;
                background: #1e1e1e;
            }}
            #trade-table {{
                width: 100%;
                border-collapse: collapse;
                font-family: monospace;
                font-size: 12px;
                color: #d1d4dc;
            }}
            #trade-table th {{
                background: #2B2B43;
                padding: 6px 10px;
                text-align: left;
                position: sticky;
                top: 0;
                z-index: 1;
                white-space: nowrap;
            }}
            #trade-table td {{
                padding: 4px 10px;
                border-bottom: 1px solid #2B2B43;
                white-space: nowrap;
            }}
            #trade-table tbody tr:hover {{ background-color: #2a3a4a; cursor: pointer; }}
            #trade-table tbody tr.highlighted {{ background-color: #1a4a7a !important; }}
        </style>
    </head>
    <body>
        <div id="chart"></div>
        <div id="trade-table-container">
            <table id="trade-table">
                <thead><tr>
                    <th>#</th>
                    <th>entry_time</th>
                    <th>exit_time</th>
                    <th>direction</th>
                    <th>entry_price</th>
                    <th>exit_price</th>
                    <th>{pip_unit}</th>
                    <th>累積{pip_unit}</th>
                </tr></thead>
                <tbody>{table_rows_html}</tbody>
            </table>
        </div>
        <script>
            // iframeでも動作するように少し待機
            setTimeout(function() {{
                const chartElement = document.getElementById('chart');
                if (!chartElement) return;
                
                const chart = LightweightCharts.createChart(chartElement, {{
                width: chartElement.clientWidth,
                height: {chart_height},
                layout: {{
                    background: {{ color: '#1e1e1e' }},
                    textColor: '#d1d4dc',
                }},
                localization: {{
                    timeFormatter: (businessDayOrTimestamp) => {{
                        const date = new Date(businessDayOrTimestamp * 1000);
                        const year = date.getUTCFullYear();
                        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
                        const day = String(date.getUTCDate()).padStart(2, '0');
                        const hours = String(date.getUTCHours()).padStart(2, '0');
                        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
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

            // 平均足チャート
            const candlestickSeries = chart.addCandlestickSeries({{
                upColor:        '{COLOR_LONG}',
                downColor:      '{COLOR_SHORT}',
                borderUpColor:  '{COLOR_LONG}',
                borderDownColor:'{COLOR_SHORT}',
                wickUpColor:    '{COLOR_LONG}',
                wickDownColor:  '{COLOR_SHORT}',
                priceLineVisible: false,
            }});
            candlestickSeries.setData({candlestick_json});

            // 75SMAライン
            const lineSeries = chart.addLineSeries({{
                color: '#ff9800',
                lineWidth: 2,
                title: '{SMA_PERIOD}SMA',
                priceLineVisible: false,
            }});
            lineSeries.setData({sma_json});

            // マーカー（組み込みは非表示・キャンバス円で代替）
            candlestickSeries.setMarkers([]);

            // クリック縦線用canvasをチャートの上に重ねる
            chartElement.style.position = 'relative';
            const lineCanvas = document.createElement('canvas');
            lineCanvas.style.position = 'absolute';
            lineCanvas.style.top = '0';
            lineCanvas.style.left = '0';
            lineCanvas.style.pointerEvents = 'none';
            lineCanvas.style.zIndex = '9999';
            lineCanvas.width = chartElement.clientWidth;
            lineCanvas.height = {chart_height};
            chartElement.appendChild(lineCanvas);

            let clickedTimestamp = null;
            let tradeEntryPrice = null;
            let tradeExitPrice = null;

            // 縦線・横線をcanvasに描画
            function drawLines() {{
                const ctx = lineCanvas.getContext('2d');
                lineCanvas.width = chartElement.clientWidth;
                lineCanvas.height = {chart_height};
                ctx.clearRect(0, 0, lineCanvas.width, lineCanvas.height);

                // エントリー→決済の連結線・円マーカー
                tradesData.forEach(function(trade) {{
                    const x1 = chart.timeScale().timeToCoordinate(trade.entry_ts);
                    const x2 = chart.timeScale().timeToCoordinate(trade.exit_ts);
                    if (x1 === null || x2 === null) return;
                    const offset = 14;
                    const isLong = trade.direction === 'long';
                    const y1anchor = isLong
                        ? candlestickSeries.priceToCoordinate(trade.entry_low)
                        : candlestickSeries.priceToCoordinate(trade.entry_high);
                    const y2anchor = trade.profitable
                        ? (isLong ? candlestickSeries.priceToCoordinate(trade.exit_high)
                                  : candlestickSeries.priceToCoordinate(trade.exit_low))
                        : (isLong ? candlestickSeries.priceToCoordinate(trade.exit_low)
                                  : candlestickSeries.priceToCoordinate(trade.exit_high));
                    if (y1anchor === null || y2anchor === null) return;
                    const y1 = isLong ? y1anchor + offset : y1anchor - offset;
                    const y2 = trade.profitable
                        ? (isLong ? y2anchor - offset : y2anchor + offset)
                        : (isLong ? y2anchor + offset : y2anchor - offset);
                    const tradeColor = trade.profitable ? '{COLOR_PROFIT}' : '{COLOR_LOSS}';
                    const entryColor = '{COLOR_ENTRY_MARKER}';
                    const r = 12;

                    // 連結線
                    ctx.beginPath();
                    ctx.strokeStyle = tradeColor;
                    ctx.lineWidth = 1;
                    ctx.setLineDash([3, 3]);
                    ctx.moveTo(x1, y1);
                    ctx.lineTo(x2, y2);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // エントリー円（青・▲▼）
                    ctx.beginPath();
                    ctx.arc(x1, y1, r, 0, Math.PI * 2);
                    ctx.fillStyle = entryColor;
                    ctx.fill();
                    ctx.fillStyle = '#fff';
                    ctx.font = 'bold 11px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(trade.direction === 'long' ? '▲' : '▼', x1, y1);

                    // エグジット円（緑○ or 赤×）
                    ctx.beginPath();
                    ctx.arc(x2, y2, r, 0, Math.PI * 2);
                    ctx.fillStyle = tradeColor;
                    ctx.fill();
                    ctx.fillStyle = '#fff';
                    ctx.fillText(trade.profitable ? '○' : '×', x2, y2);
                }});

                // 縦線（クリックした時刻）
                if (clickedTimestamp !== null) {{
                    const x = chart.timeScale().timeToCoordinate(clickedTimestamp);
                    if (x !== null) {{
                        ctx.beginPath();
                        ctx.strokeStyle = '{COLOR_CLICK_LINE}';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([4, 4]);
                        ctx.moveTo(x, 0);
                        ctx.lineTo(x, lineCanvas.height);
                        ctx.stroke();
                    }}
                }}

                // 横線を描画するヘルパー
                function drawHLine(price, color, label) {{
                    const y = candlestickSeries.priceToCoordinate(price);
                    if (y === null || y < 0 || y > lineCanvas.height) return;
                    ctx.beginPath();
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 1;
                    ctx.setLineDash([4, 4]);
                    ctx.moveTo(0, y);
                    ctx.lineTo(lineCanvas.width, y);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.font = 'bold 11px sans-serif';
                    const tw = ctx.measureText(label).width;
                    ctx.fillStyle = color;
                    ctx.fillRect(lineCanvas.width - tw - 14, y - 9, tw + 10, 16);
                    ctx.fillStyle = '#ffffff';
                    ctx.fillText(label, lineCanvas.width - tw - 9, y + 3);
                }}

                // エントリー価格（緑）と決済価格（赤）
                if (tradeEntryPrice !== null) {{
                    drawHLine(tradeEntryPrice, '{COLOR_LONG}', 'Entry ' + tradeEntryPrice.toFixed(2));
                }}
                if (tradeExitPrice !== null) {{
                    drawHLine(tradeExitPrice, '{COLOR_SHORT}', 'Exit ' + tradeExitPrice.toFixed(2));
                }}
            }}

            // スクロール・ズーム時に線を追従させる
            chart.timeScale().subscribeVisibleTimeRangeChange(function() {{
                drawLines();
            }});
            chart.subscribeCrosshairMove(function() {{
                drawLines();
            }});

            // 取引データ（Python から JSON で渡す）
            const tradesData = {trades_js_json};

            // クリックで取引一覧ハイライト＋縦線＋横線
            chart.subscribeClick(function(param) {{
                if (!param.time) return;
                const clickedTime = param.time;

                // まず全リセット
                clickedTimestamp = clickedTime;
                tradeEntryPrice = null;
                tradeExitPrice = null;

                // エントリー足かどうか検索
                let matchedTrade = null;
                for (const t of tradesData) {{
                    if (t.entry_ts === clickedTime) {{
                        matchedTrade = t;
                        break;
                    }}
                }}

                // エントリー足なら両方の横線を引く
                if (matchedTrade !== null) {{
                    tradeEntryPrice = matchedTrade.entry_price;
                    tradeExitPrice = matchedTrade.exit_price;
                }}

                // 描画
                drawLines();

                // テーブル行のハイライト更新
                const rows = document.querySelectorAll('#trade-table tbody tr');
                rows.forEach(r => r.classList.remove('highlighted'));
                if (matchedTrade !== null) {{
                    rows.forEach(function(row) {{
                        if (parseInt(row.dataset.entryTs) === matchedTrade.entry_ts) {{
                            row.classList.add('highlighted');
                            row.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                        }}
                    }});
                }}
            }});

            // ウィンドウリサイズ対応
            window.addEventListener('resize', () => {{
                try {{
                    chart.applyOptions({{ width: chartElement.clientWidth }});
                }} catch(e) {{
                    console.error('Resize error:', e);
                }}
            }});

            // 初期表示範囲の設定
            try {{
                const jumpTimestamp = {calendar.timegm(pd.Timestamp(jump_to).timetuple()) if jump_to and jump_to is not None else 'null'};
                if (jumpTimestamp !== null) {{
                    const oneDaySeconds = 24 * 60 * 60;
                    chart.timeScale().setVisibleRange({{
                        from: jumpTimestamp - oneDaySeconds,
                        to:   jumpTimestamp + oneDaySeconds,
                    }});
                }} else {{
                    chart.timeScale().fitContent();
                }}
            }} catch(e) {{}}
            drawLines();
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

# バックテスト実行ボタン（上に移動）
if st.sidebar.button("バックテスト実行", type="primary"):
    with st.spinner("バックテスト実行中..."):
        # バックテスト実行
        bt = BacktestEngine(str(csv_path), logic_module=selected_logic, pip_multiplier=pip_multiplier, pip_unit=pip_unit)
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
    
    # ジャンプ先の日時を取得
    jump_to = st.session_state.get('jump_to', None)
    
    html_code = create_lightweight_chart(bt.df, bt.trades, chart_height, jump_to, bt.pip_unit)
    components.html(html_code, height=chart_height + 420, scrolling=True)
else:
    st.info("👈 サイドバーから「バックテスト実行」ボタンを押してください")