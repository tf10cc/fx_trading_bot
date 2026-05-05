import pandas as pd
import json
import calendar

SMA_PERIOD = 75

COLOR_PROFIT       = '#4CAF50'
COLOR_LOSS         = '#f23645'
COLOR_LONG         = '#26a69a'
COLOR_SHORT        = '#ef5350'
COLOR_ENTRY_MARKER = '#2196F3'
COLOR_CLICK_LINE   = '#ffff00'


def create_lightweight_chart(df, trades, chart_height=600, jump_to=None, pip_unit='pips'):
    """TradingView Lightweight Chartsを生成"""

    # 平均足データを準備（UNIXタイムスタンプに変換）
    candlestick_data = []
    for idx, row in df.iterrows():
        if pd.notna(row['ha_open']) and pd.notna(row['ha_high']) and pd.notna(row['ha_low']) and pd.notna(row['ha_close']):
            try:
                candlestick_data.append({
                    'time': calendar.timegm(row['time'].timetuple()),
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
                    'time': calendar.timegm(row['time'].timetuple()),
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
            }}, 100);
        </script>
    </body>
    </html>
    """

    return html_code
