"""
FES ライブモニター

起動方法:
  streamlit run live/monitor.py
"""

import sys
import calendar
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
JST_OFFSET = 9 * 3600  # チャートタイムスタンプ用

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

CANDLE_LOG = Path(__file__).parent / 'candle_log.csv'
TRADE_LOG  = Path(__file__).parent / 'trade_log.csv'

COLOR_PROFIT       = '#4CAF50'
COLOR_LOSS         = '#f23645'
COLOR_LONG         = '#26a69a'
COLOR_SHORT        = '#ef5350'
COLOR_ENTRY_MARKER = '#2196F3'
COLOR_CLICK_LINE   = '#ffff00'
SMA_PERIOD         = 75


def load_candles():
    if not CANDLE_LOG.exists():
        return None
    df = pd.read_csv(CANDLE_LOG)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    return df


def load_trades():
    """trade_log.csv からエントリー・決済をペアにして返す（決済待ちも含む）"""
    if not TRADE_LOG.exists():
        return []
    log = pd.read_csv(TRADE_LOG)
    trades = []
    pending = None  # 未決済のエントリー

    for _, row in log.iterrows():
        action = row['action']
        if action in ('BUY', 'SELL'):
            pending = row
        elif action in ('EXIT_LONG', 'EXIT_SHORT') and pending is not None:
            direction = 'long' if action == 'EXIT_LONG' else 'short'
            entry_price = float(pending['price'])
            exit_price  = float(row['price'])
            pips = (exit_price - entry_price) * 100 if direction == 'long' \
                   else (entry_price - exit_price) * 100
            trades.append({
                'entry_time':  pending['datetime_utc'],
                'exit_time':   row['datetime_utc'],
                'direction':   direction,
                'entry_price': entry_price,
                'exit_price':  exit_price,
                'pips':        pips,
                'open':        False,
            })
            pending = None

    # 決済待ちのエントリーも追加
    if pending is not None:
        direction = 'long' if pending['action'] == 'BUY' else 'short'
        trades.append({
            'entry_time':  pending['datetime_utc'],
            'exit_time':   '決済待ち',
            'direction':   direction,
            'entry_price': float(pending['price']),
            'exit_price':  None,
            'pips':        None,
            'open':        True,
        })

    return trades


def utc_str_to_jst(s):
    return pd.Timestamp(s, tz='UTC').astimezone(JST).strftime('%Y-%m-%d %H:%M')


def create_chart(df, trades, chart_height=600):
    candlestick_data = []
    for _, row in df.iterrows():
        if pd.notna(row.get('ha_open')) and pd.notna(row.get('ha_close')):
            try:
                candlestick_data.append({
                    'time':  calendar.timegm(row['time'].timetuple()) + JST_OFFSET,
                    'open':  round(float(row['ha_open']),  5),
                    'high':  round(float(row['ha_high']),  5),
                    'low':   round(float(row['ha_low']),   5),
                    'close': round(float(row['ha_close']), 5),
                })
            except:
                continue

    sma_data = []
    for _, row in df.iterrows():
        if pd.notna(row.get('sma')):
            try:
                sma_data.append({
                    'time':  calendar.timegm(row['time'].timetuple()) + JST_OFFSET,
                    'value': round(float(row['sma']), 5),
                })
            except:
                continue

    markers = []
    trades_for_js = []
    rows_data = []
    cum_pips = 0

    for i, trade in enumerate(trades):
        entry_ts  = calendar.timegm(pd.Timestamp(trade['entry_time']).timetuple()) + JST_OFFSET
        dir_color = COLOR_LONG if trade['direction'] == 'long' else COLOR_SHORT
        dir_label = 'Long' if trade['direction'] == 'long' else 'Short'

        markers.append({
            'time':     entry_ts,
            'position': 'belowBar' if trade['direction'] == 'long' else 'aboveBar',
            'color':    COLOR_ENTRY_MARKER,
            'shape':    'arrowUp' if trade['direction'] == 'long' else 'arrowDown',
            'text':     '',
        })

        if trade['open']:
            rows_data.append({
                'open': True, 'i': i, 'entry_ts': entry_ts,
                'entry_time': utc_str_to_jst(trade['entry_time']), 'dir_color': dir_color, 'dir_label': dir_label,
                'entry_price': trade['entry_price'],
            })
        else:
            exit_ts   = calendar.timegm(pd.Timestamp(trade['exit_time']).timetuple()) + JST_OFFSET
            cum_pips += trade['pips']
            markers.append({
                'time':     exit_ts,
                'position': 'aboveBar' if trade['direction'] == 'long' else 'belowBar',
                'color':    COLOR_PROFIT if trade['pips'] > 0 else COLOR_LOSS,
                'shape':    'circle' if trade['pips'] > 0 else 'square',
                'text':     '',
            })
            trades_for_js.append({'entry_ts': entry_ts, 'exit_ts': exit_ts,
                                   'entry_price': trade['entry_price'], 'exit_price': trade['exit_price']})
            rows_data.append({
                'open': False, 'i': i, 'entry_ts': entry_ts,
                'entry_time': utc_str_to_jst(trade['entry_time']), 'exit_time': utc_str_to_jst(trade['exit_time']),
                'dir_color': dir_color, 'dir_label': dir_label,
                'entry_price': trade['entry_price'], 'exit_price': trade['exit_price'],
                'pips': trade['pips'], 'cum_pips': cum_pips,
            })

    # テーブルHTML：新しい順（上が最新）
    table_rows_html = ''
    for row in reversed(rows_data):
        if row['open']:
            table_rows_html += f"""<tr data-entry-ts="{row['entry_ts']}" style="background:#2a2a00;">
                <td>{row['i']}</td><td>{row['entry_time']}</td><td style="color:#ffcc00;">決済待ち</td>
                <td style="color:{row['dir_color']}">{row['dir_label']}</td>
                <td>{row['entry_price']:.3f}</td><td>-</td>
                <td>-</td><td style="color:#ffcc00;">open</td>
            </tr>"""
        else:
            pips_color = COLOR_PROFIT if row['pips'] > 0 else COLOR_LOSS
            cum_color  = COLOR_PROFIT if row['cum_pips'] >= 0 else COLOR_LOSS
            table_rows_html += f"""<tr data-entry-ts="{row['entry_ts']}">
                <td>{row['i']}</td><td>{row['entry_time']}</td><td>{row['exit_time']}</td>
                <td style="color:{row['dir_color']}">{row['dir_label']}</td>
                <td>{row['entry_price']:.3f}</td><td>{row['exit_price']:.3f}</td>
                <td style="color:{pips_color}">{row['pips']:.2f}</td>
                <td style="color:{cum_color}">{row['cum_pips']:.2f}</td>
            </tr>"""

    candle_json  = json.dumps(candlestick_data)
    sma_json     = json.dumps(sma_data)
    markers_json = json.dumps(markers)
    trades_json  = json.dumps(trades_for_js)

    html = f"""<!DOCTYPE html><html><head>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{ margin:0; padding:0; background:#1e1e1e; }}
        #chart {{ width:100%; height:{chart_height}px; }}
        #trade-table-container {{ max-height:300px; overflow-y:auto; margin-top:8px; background:#1e1e1e; }}
        #trade-table {{ width:100%; border-collapse:collapse; font-family:monospace; font-size:12px; color:#d1d4dc; }}
        #trade-table th {{ background:#2B2B43; padding:6px 10px; text-align:left; position:sticky; top:0; z-index:1; white-space:nowrap; }}
        #trade-table td {{ padding:4px 10px; border-bottom:1px solid #2B2B43; white-space:nowrap; }}
        #trade-table tbody tr:hover {{ background:#2a3a4a; cursor:pointer; }}
        #trade-table tbody tr.highlighted {{ background:#1a4a7a !important; }}
    </style></head><body>
    <div id="chart"></div>
    <div id="trade-table-container">
        <table id="trade-table">
            <thead><tr>
                <th>#</th><th>entry_time</th><th>exit_time</th><th>direction</th>
                <th>entry_price</th><th>exit_price</th><th>pips</th><th>累積pips</th>
            </tr></thead>
            <tbody>{table_rows_html}</tbody>
        </table>
    </div>
    <script>
    setTimeout(function() {{
        const chartElement = document.getElementById('chart');
        const chart = LightweightCharts.createChart(chartElement, {{
            width: chartElement.clientWidth, height: {chart_height},
            layout: {{ background: {{ color: '#1e1e1e' }}, textColor: '#d1d4dc' }},
            localization: {{ timeFormatter: (t) => {{
                const d = new Date(t * 1000);
                return d.getUTCFullYear() + '/' + String(d.getUTCMonth()+1).padStart(2,'0') + '/' +
                       String(d.getUTCDate()).padStart(2,'0') + ' ' +
                       String(d.getUTCHours()).padStart(2,'0') + ':' + String(d.getUTCMinutes()).padStart(2,'0');
            }} }},
            grid: {{ vertLines: {{ color: '#2B2B43' }}, horzLines: {{ color: '#363C4E' }} }},
            rightPriceScale: {{ borderColor: '#2B2B43' }},
            timeScale: {{ borderColor: '#2B2B43', timeVisible: true, secondsVisible: false }},
        }});
        const candleSeries = chart.addCandlestickSeries({{
            upColor: '{COLOR_LONG}', downColor: '{COLOR_SHORT}',
            borderUpColor: '{COLOR_LONG}', borderDownColor: '{COLOR_SHORT}',
            wickUpColor: '{COLOR_LONG}', wickDownColor: '{COLOR_SHORT}',
            priceLineVisible: false,
        }});
        candleSeries.setData({candle_json});
        const smaSeries = chart.addLineSeries({{ color: '#ff9800', lineWidth: 2, title: '{SMA_PERIOD}SMA', priceLineVisible: false }});
        smaSeries.setData({sma_json});
        candleSeries.setMarkers({markers_json});

        chartElement.style.position = 'relative';
        const lineCanvas = document.createElement('canvas');
        lineCanvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:9999;';
        lineCanvas.width = chartElement.clientWidth;
        lineCanvas.height = {chart_height};
        chartElement.appendChild(lineCanvas);

        let clickedTs = null, entryPrice = null, exitPrice = null;
        const tradesData = {trades_json};

        function drawLines() {{
            const ctx = lineCanvas.getContext('2d');
            lineCanvas.width = chartElement.clientWidth;
            lineCanvas.height = {chart_height};
            ctx.clearRect(0, 0, lineCanvas.width, lineCanvas.height);
            if (clickedTs !== null) {{
                const x = chart.timeScale().timeToCoordinate(clickedTs);
                if (x !== null) {{
                    ctx.beginPath(); ctx.strokeStyle = '{COLOR_CLICK_LINE}'; ctx.lineWidth = 1;
                    ctx.setLineDash([4,4]); ctx.moveTo(x,0); ctx.lineTo(x, lineCanvas.height); ctx.stroke();
                }}
            }}
            function drawHLine(price, color, label) {{
                const y = candleSeries.priceToCoordinate(price);
                if (y === null || y < 0 || y > lineCanvas.height) return;
                ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([4,4]);
                ctx.moveTo(0,y); ctx.lineTo(lineCanvas.width,y); ctx.stroke(); ctx.setLineDash([]);
                const tw = ctx.measureText(label).width;
                ctx.fillStyle = color; ctx.fillRect(lineCanvas.width-tw-14, y-9, tw+10, 16);
                ctx.fillStyle = '#fff'; ctx.font = 'bold 11px sans-serif'; ctx.fillText(label, lineCanvas.width-tw-9, y+3);
            }}
            if (entryPrice !== null) drawHLine(entryPrice, '{COLOR_LONG}', 'Entry ' + entryPrice.toFixed(3));
            if (exitPrice  !== null) drawHLine(exitPrice,  '{COLOR_SHORT}', 'Exit '  + exitPrice.toFixed(3));
        }}
        chart.timeScale().subscribeVisibleTimeRangeChange(drawLines);
        chart.subscribeCrosshairMove(drawLines);
        chart.subscribeClick(function(param) {{
            if (!param.time) return;
            clickedTs = param.time; entryPrice = null; exitPrice = null;
            const matched = tradesData.find(t => t.entry_ts === param.time);
            if (matched) {{ entryPrice = matched.entry_price; exitPrice = matched.exit_price; }}
            drawLines();
            document.querySelectorAll('#trade-table tbody tr').forEach(r => r.classList.remove('highlighted'));
            if (matched) {{
                document.querySelectorAll('#trade-table tbody tr').forEach(r => {{
                    if (parseInt(r.dataset.entryTs) === matched.entry_ts) {{
                        r.classList.add('highlighted');
                        r.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
                    }}
                }});
            }}
        }});
        window.addEventListener('resize', () => {{ try {{ chart.applyOptions({{ width: chartElement.clientWidth }}); }} catch(e) {{}} }});
        chart.timeScale().fitContent();
    }}, 100);
    </script></body></html>"""
    return html


# ========== Streamlit UI ==========

st.set_page_config(page_title='FES ライブモニター', layout='wide')
st.title('FES ライブモニター')
st.caption(f'最終更新: {datetime.now(JST).strftime("%Y-%m-%d %H:%M")} JST')

df = load_candles()
trades = load_trades()

if df is None:
    st.warning('candle_log.csv がまだありません。しばらくお待ちください。')
    st.stop()

st.caption(f'取得済み足数: {len(df)} 本 　最新: {df["time"].iloc[-1].astimezone(JST).strftime("%Y-%m-%d %H:%M")} JST')

# サマリー
closed = [t for t in trades if not t['open']]
total_pips = sum(t['pips'] for t in closed)
wins = sum(1 for t in closed if t['pips'] > 0)
n = len(closed)
win_rate = wins / n * 100 if n > 0 else 0
open_trade = next((t for t in trades if t['open']), None)
status = f"{'Long' if open_trade['direction'] == 'long' else 'Short'} 保有中" if open_trade else "待機中"
col1, col2, col3, col4 = st.columns(4)
col1.metric('累積pips', f'{total_pips:+.2f}')
col2.metric('勝率', f'{win_rate:.0f}%  ({wins}/{n})')
col3.metric('トレード数', f'{n} 件')
col4.metric('現在', status)

chart_html = create_chart(df, trades)
components.html(chart_html, height=600 + 350, scrolling=True)

if st.button('更新'):
    st.rerun()
