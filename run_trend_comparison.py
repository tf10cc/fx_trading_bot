"""
傾きフィルター（TREND_THRESHOLD）比較スクリプト
7月・8月・9月 × 5パターンの結果をHTMLに出力
"""
import importlib.util
import sys
import os

# カセット読み込み
spec = importlib.util.spec_from_file_location('logic', 'logics/heikin_ashi_75sma.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

# エンジン読み込み
spec2 = importlib.util.spec_from_file_location('backtest_engine', 'backtest/backtest_engine.py')
engine_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(engine_mod)
BacktestEngine = engine_mod.BacktestEngine

MONTHS = [
    ('2024年7月', 'data/USD-JPY_Hour_2024-07-01_to_2024-07-31_UTC.csv'),
    ('2024年8月', 'data/USD-JPY_Hour_2024-08-01_to_2024-08-31_UTC.csv'),
    ('2024年9月', 'data/USD-JPY_Hour_2024-09-01_to_2024-09-30_UTC.csv'),
]

THRESHOLDS = [0, 0.05, 0.10, 0.15, 0.20]
THRESHOLD_LABELS = ['なし（元）', '0.05', '0.10', '0.15', '0.20']

def run_backtest(csv_path, threshold):
    logic.TREND_THRESHOLD = threshold
    engine = BacktestEngine(csv_path, logic, pip_multiplier=100)
    engine.run()
    return engine.calculate_metrics()

# 全パターン実行
all_results = {}
for month_label, csv_path in MONTHS:
    all_results[month_label] = []
    for threshold in THRESHOLDS:
        m = run_backtest(csv_path, threshold)
        all_results[month_label].append(m)

# 3か月合計を計算
totals = []
for i, threshold in enumerate(THRESHOLDS):
    total_pips = sum(all_results[ml][i]['total_pips'] for ml, _ in MONTHS)
    total_trades = sum(all_results[ml][i]['total_trades'] for ml, _ in MONTHS)
    total_win = sum(all_results[ml][i]['win_count'] for ml, _ in MONTHS)
    total_loss_pips = sum(all_results[ml][i]['total_trades'] * (1 - all_results[ml][i]['win_rate']/100) * all_results[ml][i].get('avg_loss', 0) for ml, _ in MONTHS)
    win_rate = (total_win / total_trades * 100) if total_trades > 0 else 0

    total_win_pips = sum(all_results[ml][i]['win_count'] * all_results[ml][i].get('avg_win', 0) for ml, _ in MONTHS)
    total_loss_pips2 = sum(all_results[ml][i]['loss_count'] * all_results[ml][i].get('avg_loss', 0) for ml, _ in MONTHS)
    pf = total_win_pips / total_loss_pips2 if total_loss_pips2 > 0 else float('inf')

    totals.append({
        'total_pips': total_pips,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': pf,
    })

def fmt_pips(v):
    color = '#4caf50' if v > 0 else '#f44336'
    sign = '+' if v > 0 else ''
    return f'<span style="color:{color}">{sign}{v:.2f}</span>'

def fmt_pf(v):
    color = '#4caf50' if v >= 1.0 else '#f44336'
    s = f'{v:.2f}' if v != float('inf') else '∞'
    return f'<span style="color:{color}">{s}</span>'

def build_month_table(month_label, results):
    # 各指標のベスト行を特定
    best_pips = max(range(len(results)), key=lambda i: results[i]['total_pips'])
    best_pf = max(range(len(results)), key=lambda i: results[i]['profit_factor'] if results[i]['profit_factor'] != float('inf') else 0)

    rows = ''
    for i, (m, label) in enumerate(zip(results, THRESHOLD_LABELS)):
        highlight = ' style="background:#1a3a1a;"' if i == best_pips else ''
        star = ' ★' if i == best_pips else ''
        pf_val = m['profit_factor']
        pf_str = fmt_pf(pf_val)
        rows += f'''
        <tr{highlight}>
            <td>{label}{star}</td>
            <td>{fmt_pips(m["total_pips"])}</td>
            <td>{m["total_trades"]}回</td>
            <td>{m["win_rate"]:.2f}%</td>
            <td>{m["max_drawdown"]:.2f}</td>
            <td>{pf_str}</td>
        </tr>'''

    return f'''
    <div class="month-section">
        <h2>{month_label}</h2>
        <table>
            <thead>
                <tr>
                    <th>傾きフィルター</th>
                    <th>総損益 (pips)</th>
                    <th>取引回数</th>
                    <th>勝率</th>
                    <th>最大DD (pips)</th>
                    <th>PF</th>
                </tr>
            </thead>
            <tbody>{rows}
            </tbody>
        </table>
    </div>'''

def build_total_table(totals):
    best_pips = max(range(len(totals)), key=lambda i: totals[i]['total_pips'])
    rows = ''
    for i, (t, label) in enumerate(zip(totals, THRESHOLD_LABELS)):
        highlight = ' style="background:#1a3a1a;"' if i == best_pips else ''
        star = ' ★' if i == best_pips else ''
        rows += f'''
        <tr{highlight}>
            <td>{label}{star}</td>
            <td>{fmt_pips(t["total_pips"])}</td>
            <td>{t["total_trades"]}回</td>
            <td>{t["win_rate"]:.2f}%</td>
            <td>-</td>
            <td>{fmt_pf(t["profit_factor"])}</td>
        </tr>'''
    return f'''
    <div class="month-section">
        <h2>3か月合計</h2>
        <table>
            <thead>
                <tr>
                    <th>傾きフィルター</th>
                    <th>総損益 (pips)</th>
                    <th>取引回数</th>
                    <th>勝率</th>
                    <th>最大DD</th>
                    <th>PF</th>
                </tr>
            </thead>
            <tbody>{rows}
            </tbody>
        </table>
    </div>'''

html_parts = ''
for month_label, _ in MONTHS:
    html_parts += build_month_table(month_label, all_results[month_label])
html_parts += build_total_table(totals)

html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>傾きフィルター 比較結果</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:sans-serif; padding:24px; }}
  h1 {{ color:#f0a500; }}
  h2 {{ color:#f0a500; margin-top:32px; }}
  .subtitle {{ color:#aaa; margin-bottom:24px; }}
  .month-section {{ margin-bottom:40px; }}
  table {{ border-collapse:collapse; width:580px; }}
  th {{ background:#2a2a4a; color:#f0a500; padding:10px 14px; text-align:left; }}
  td {{ padding:8px 14px; border-bottom:1px solid #333; }}
  tr:hover {{ background:#252545; }}
  .note {{ color:#888; font-size:0.85em; margin-top:8px; }}
</style>
</head>
<body>
<h1>傾きフィルター 比較結果</h1>
<p class="subtitle">手法：R氏 平均足75SMA／ドル円H1／2024年7〜9月<br>損切り：30pips固定</p>
{html_parts}
<p class="note">※ 緑ハイライト（★）＝その月の最良値（総損益基準）</p>
<p class="note">傾きフィルター：5本前のSMAと現在のSMAの差。0=元の動作（少しでも動けばOK）</p>
</body>
</html>'''

out_path = 'etc/trend_filter_results.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'完了: {out_path}')
