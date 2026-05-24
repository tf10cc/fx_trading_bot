"""
75SMA割れ決済 vs 20SMA割れ決済 比較スクリプト
1年分データ（USDJPY_H1_2024_OANDA.csv）で両カセットを実行しHTMLに出力
"""
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

engine_mod = load_module('backtest_engine', 'backtest/backtest_engine.py')
BacktestEngine = engine_mod.BacktestEngine

CASSETTES = [
    ('heikin_ashi_75sma_exit_noadx',  'logics/heikin_ashi_75sma_exit_noadx.py'),
    ('heikin_ashi_75sma_20sma_exit',  'logics/heikin_ashi_75sma_20sma_exit.py'),
]

CSV = 'data/USDJPY_H1_2024_OANDA.csv'

results = []
for key, path in CASSETTES:
    logic = load_module(key, path)
    bt = BacktestEngine(CSV, logic_module=logic, pip_multiplier=100, pip_unit='pips')
    bt.run()
    m = bt.calculate_metrics()
    results.append((logic.NAME, m))

def fmt_pips(v):
    color = '#4caf50' if v >= 0 else '#f44336'
    sign = '+' if v > 0 else ''
    return f'<span style="color:{color}">{sign}{v:.2f}</span>'

def fmt_pf(v):
    color = '#4caf50' if v >= 1.0 else '#f44336'
    s = f'{v:.2f}' if v != float('inf') else '∞'
    return f'<span style="color:{color}">{s}</span>'

METRICS = [
    ('総損益 (pips)',  lambda m: fmt_pips(m['total_pips'])),
    ('取引回数',       lambda m: f"{m['total_trades']}回"),
    ('勝率',          lambda m: f"{m['win_rate']:.2f}%"),
    ('最大DD (pips)', lambda m: f"{m['max_drawdown']:.2f}"),
    ('PF',            lambda m: fmt_pf(m['profit_factor'])),
]

header = '<tr><th>指標</th>' + ''.join(f'<th>{name}</th>' for name, _ in results) + '</tr>'
rows = ''
for label, fn in METRICS:
    rows += f'<tr><td>{label}</td>' + ''.join(f'<td>{fn(m)}</td>' for _, m in results) + '</tr>'

html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>決済条件 比較結果</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:sans-serif; padding:24px; }}
  h1 {{ color:#f0a500; }}
  .subtitle {{ color:#aaa; margin-bottom:24px; }}
  table {{ border-collapse:collapse; min-width:500px; }}
  th {{ background:#2a2a4a; color:#f0a500; padding:10px 20px; text-align:left; }}
  td {{ padding:10px 20px; border-bottom:1px solid #333; }}
  tr:hover {{ background:#252545; }}
</style>
</head>
<body>
<h1>決済条件 比較結果</h1>
<p class="subtitle">データ：USDJPY H1 2024年1月〜12月（1年間）</p>
<table>
  <thead>{header}</thead>
  <tbody>{rows}</tbody>
</table>
</body>
</html>"""

out = 'etc/exit_comparison_results.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'完了: {out}')
for name, m in results:
    pf = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else 'inf'
    print(f"  {name}")
    print(f"    総損益={m['total_pips']:.2f} 取引={m['total_trades']} 勝率={m['win_rate']:.2f}% DD={m['max_drawdown']:.2f} PF={pf}")
