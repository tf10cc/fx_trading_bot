"""
バックテスト比較スクリプト
①色変化のみ vs ②色継続もOK を3ヶ月分比較してHTMLに出力
実行: python backtest/run_compare.py
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SMA_PERIOD = 75
OUTPUT_HTML = Path(__file__).resolve().parent / "compare_result.html"


# ---- BacktestEngine（streamlitなし版）----

class BacktestEngine:
    def __init__(self, csv_path, logic_module, pip_multiplier=100, pip_unit="pips"):
        self.csv_path = csv_path
        self.logic_module = logic_module
        self.pip_multiplier = pip_multiplier
        self.pip_unit = pip_unit
        self.df = None
        self.trades = []
        self.current_position = None
        self.entry_time = None
        self.entry_price = None
        self.total_pips = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_win_pips = 0
        self.total_loss_pips = 0

    def load_data(self):
        self.df = pd.read_csv(self.csv_path)
        self.df.columns = self.df.columns.str.replace('<', '').str.replace('>', '').str.lower()
        if 'ticker' in self.df.columns and 'dtyyyymmdd' in self.df.columns:
            date_str = self.df['dtyyyymmdd'].astype(str)
            time_str = self.df['time'].astype(str).str.zfill(4)
            self.df['time'] = pd.to_datetime(date_str + ' ' + time_str, format='%Y%m%d %H%M')
        elif 'utc' in self.df.columns:
            self.df['time'] = pd.to_datetime(self.df['utc'], dayfirst=True)
            self.df['open']   = self.df['open']
            self.df['high']   = self.df['high']
            self.df['low']    = self.df['low']
            self.df['close']  = self.df['close']
        elif 'time' in self.df.columns:
            self.df['time'] = pd.to_datetime(self.df['time'], dayfirst=True)

    def calculate_indicators(self):
        self.df['sma'] = self.df['close'].rolling(window=SMA_PERIOD).mean()
        ha_close = (self.df['open'] + self.df['high'] + self.df['low'] + self.df['close']) / 4
        ha_open = pd.Series(index=self.df.index, dtype=float)
        ha_open.iloc[0] = (self.df['open'].iloc[0] + self.df['close'].iloc[0]) / 2
        for i in range(1, len(self.df)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
        self.df['ha_open']        = ha_open
        self.df['ha_close']       = ha_close
        self.df['ha_high']        = pd.concat([self.df['high'], ha_open, ha_close], axis=1).max(axis=1)
        self.df['ha_low']         = pd.concat([self.df['low'],  ha_open, ha_close], axis=1).min(axis=1)
        self.df['ha_color']       = np.where(self.df['ha_close'] >= self.df['ha_open'], 1, -1)
        self.df['ha_body_top']    = self.df[['ha_open', 'ha_close']].max(axis=1)
        self.df['ha_body_bottom'] = self.df[['ha_open', 'ha_close']].min(axis=1)

    def run(self):
        self.load_data()
        self.calculate_indicators()
        for idx in range(len(self.df)):
            just_exited = False
            if self.current_position == 'long' and self.logic_module.check_long_exit(self.df, idx):
                self._exit(idx)
                just_exited = True
            elif self.current_position == 'short' and self.logic_module.check_short_exit(self.df, idx):
                self._exit(idx)
                just_exited = True
            if self.current_position is None and not just_exited:
                if self.logic_module.check_long_entry(self.df, idx):
                    self._enter(idx, 'long')
                elif self.logic_module.check_short_entry(self.df, idx):
                    self._enter(idx, 'short')
        if self.current_position is not None:
            last = len(self.df) - 1
            exit_price = self.df['close'].iloc[last]
            pips = (exit_price - self.entry_price) * self.pip_multiplier if self.current_position == 'long' \
                else (self.entry_price - exit_price) * self.pip_multiplier
            self._record_trade(self.df['time'].iloc[last], exit_price, pips)

    def _enter(self, idx, direction):
        if idx + 1 >= len(self.df):
            return
        self.current_position = direction
        self.entry_time  = self.df['time'].iloc[idx + 1]
        self.entry_price = self.df['open'].iloc[idx + 1]

    def _exit(self, idx):
        if idx + 1 >= len(self.df):
            return
        exit_price = self.df['open'].iloc[idx + 1]
        pips = (exit_price - self.entry_price) * self.pip_multiplier if self.current_position == 'long' \
            else (self.entry_price - exit_price) * self.pip_multiplier
        self._record_trade(self.df['time'].iloc[idx + 1], exit_price, pips)

    def _record_trade(self, exit_time, exit_price, pips):
        self.trades.append({
            'entry_time':  self.entry_time,
            'exit_time':   exit_time,
            'direction':   self.current_position,
            'entry_price': self.entry_price,
            'exit_price':  exit_price,
            'pips':        pips,
        })
        self.total_pips += pips
        if pips > 0:
            self.win_count       += 1
            self.total_win_pips  += pips
        else:
            self.loss_count      += 1
            self.total_loss_pips += abs(pips)
        self.current_position = None
        self.entry_time = self.entry_price = None

    def metrics(self):
        total = self.win_count + self.loss_count
        win_rate = self.win_count / total * 100 if total else 0
        pf = self.total_win_pips / self.total_loss_pips if self.total_loss_pips else float('inf')
        cum, peak, max_dd = 0, 0, 0
        for t in self.trades:
            cum += t['pips']
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        return {
            'pips':       self.total_pips,
            'trades':     total,
            'wins':       self.win_count,
            'losses':     self.loss_count,
            'win_rate':   win_rate,
            'pf':         pf,
            'max_dd':     max_dd,
        }


# ---- ユーティリティ ----

def load_module(path):
    spec = importlib.util.spec_from_file_location('logic', path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_bt(csv_path, logic_module):
    bt = BacktestEngine(str(csv_path), logic_module)
    bt.run()
    return bt.metrics()


# ---- HTML生成 ----

def pips_cell(v):
    color = '#4CAF50' if v >= 0 else '#f23645'
    return f'<td style="color:{color};font-weight:bold">{v:.1f}</td>'

def pct_cell(v):
    return f'<td>{v:.1f}%</td>'

def pf_cell(v):
    color = '#4CAF50' if v >= 1 else '#f23645'
    s = f'{v:.2f}' if v != float('inf') else '∞'
    return f'<td style="color:{color}">{s}</td>'

def generate_html(rows, totals):
    month_rows_html = ""
    for month, r1, r2 in rows:
        diff_pips = r2['pips'] - r1['pips']
        diff_color = '#4CAF50' if diff_pips >= 0 else '#f23645'
        month_rows_html += f"""
        <tr>
            <td rowspan="2" style="text-align:center;font-weight:bold;background:#1a2a3a">{month}</td>
            <td style="color:#90CAF9">①色変化のみ</td>
            {pips_cell(r1['pips'])}
            <td>{r1['trades']}</td>
            {pct_cell(r1['win_rate'])}
            {pf_cell(r1['pf'])}
            <td>{r1['max_dd']:.1f}</td>
            <td rowspan="2" style="color:{diff_color};font-weight:bold;font-size:1.1em;text-align:center;background:#111">
                {'+' if diff_pips >= 0 else ''}{diff_pips:.1f}
            </td>
        </tr>
        <tr>
            <td style="color:#FFD54F">②色継続もOK</td>
            {pips_cell(r2['pips'])}
            <td>{r2['trades']}</td>
            {pct_cell(r2['win_rate'])}
            {pf_cell(r2['pf'])}
            <td>{r2['max_dd']:.1f}</td>
        </tr>
        <tr><td colspan="8" style="height:4px;background:#2a2a2a"></td></tr>
        """

    t1, t2 = totals
    diff_total = t2['pips'] - t1['pips']
    diff_total_color = '#4CAF50' if diff_total >= 0 else '#f23645'

    total_rows_html = f"""
        <tr style="background:#1a3050">
            <td rowspan="2" style="text-align:center;font-weight:bold;font-size:1.1em">3ヶ月<br>合計</td>
            <td style="color:#90CAF9">①色変化のみ</td>
            {pips_cell(t1['pips'])}
            <td>{t1['trades']}</td>
            {pct_cell(t1['win_rate'])}
            {pf_cell(t1['pf'])}
            <td>{t1['max_dd']:.1f}</td>
            <td rowspan="2" style="color:{diff_total_color};font-weight:bold;font-size:1.3em;text-align:center;background:#0d1f30">
                {'+' if diff_total >= 0 else ''}{diff_total:.1f}
            </td>
        </tr>
        <tr style="background:#1a3050">
            <td style="color:#FFD54F">②色継続もOK</td>
            {pips_cell(t2['pips'])}
            <td>{t2['trades']}</td>
            {pct_cell(t2['win_rate'])}
            {pf_cell(t2['pf'])}
            <td>{t2['max_dd']:.1f}</td>
        </tr>
    """

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>バックテスト比較 ①vs②</title>
<style>
  body {{ background:#121212; color:#e0e0e0; font-family:monospace; padding:24px; }}
  h1   {{ color:#90CAF9; margin-bottom:4px; }}
  .sub {{ color:#888; margin-bottom:24px; font-size:0.9em; }}
  table {{ border-collapse:collapse; width:100%; max-width:900px; }}
  th, td {{ padding:10px 14px; border:1px solid #333; text-align:right; }}
  th {{ background:#263238; color:#cfd8dc; text-align:center; }}
  td:nth-child(1), td:nth-child(2) {{ text-align:left; }}
  .legend {{ margin-top:20px; font-size:0.85em; color:#888; }}
</style>
</head>
<body>
<h1>📊 バックテスト比較結果</h1>
<div class="sub">対象期間: 2024年7月〜9月（USD/JPY 1時間足） | SMA75 平均足手法</div>
<table>
  <thead>
    <tr>
      <th>月</th>
      <th>ロジック</th>
      <th>総損益<br>(pips)</th>
      <th>取引数</th>
      <th>勝率</th>
      <th>PF</th>
      <th>最大DD<br>(pips)</th>
      <th>②−①差</th>
    </tr>
  </thead>
  <tbody>
    {month_rows_html}
    {total_rows_html}
  </tbody>
</table>
<div class="legend">
  ①: 色変化のみ（赤→青 / 青→赤）でエントリー<br>
  ②: 色継続もOK（青なら青継続でもエントリー）<br>
  ②−①差: ②が①より何pips多いか（プラス=②が優秀）
</div>
</body>
</html>
"""
    return html


# ---- メイン ----

if __name__ == '__main__':
    base = Path(__file__).resolve().parent.parent

    csv_months = [
        ('2024-07', base / 'data' / 'USD-JPY_Hour_2024-07-01_to_2024-07-31_UTC.csv'),
        ('2024-08', base / 'data' / 'USD-JPY_Hour_2024-08-01_to_2024-08-31_UTC.csv'),
        ('2024-09', base / 'data' / 'USD-JPY_Hour_2024-09-01_to_2024-09-30_UTC.csv'),
    ]

    logic1 = load_module(base / 'logics' / 'heikin_ashi_75sma_m5_color_change.py')
    logic2 = load_module(base / 'logics' / 'heikin_ashi_75sma_m5.py')

    rows = []
    total1 = {'pips': 0, 'trades': 0, 'wins': 0, 'losses': 0,
              'total_win_pips': 0, 'total_loss_pips': 0, 'max_dd': 0}
    total2 = dict(total1)

    for month, csv_path in csv_months:
        r1 = run_bt(csv_path, logic1)
        r2 = run_bt(csv_path, logic2)
        rows.append((month, r1, r2))
        for key in ('pips', 'trades', 'wins', 'losses'):
            total1[key] += r1[key]
            total2[key] += r2[key]
        # 最大DDは月別の最大値で集計
        total1['max_dd'] = max(total1['max_dd'], r1['max_dd'])
        total2['max_dd'] = max(total2['max_dd'], r2['max_dd'])
        # PF再計算用に勝ち負けpipsも積算
        total1['total_win_pips']  = total1.get('total_win_pips', 0)  + r1['wins'] * (r1['pips'] / r1['trades'] if r1['trades'] else 0)
        total2['total_win_pips']  = total2.get('total_win_pips', 0)  + r2['wins'] * (r2['pips'] / r2['trades'] if r2['trades'] else 0)

        print(f"{month}  ① pips={r1['pips']:.1f} trades={r1['trades']} wr={r1['win_rate']:.1f}% pf={r1['pf']:.2f} dd={r1['max_dd']:.1f}")
        print(f"{month}  ② pips={r2['pips']:.1f} trades={r2['trades']} wr={r2['win_rate']:.1f}% pf={r2['pf']:.2f} dd={r2['max_dd']:.1f}")

    # トータルのPF・勝率を再計算（月をまたいで全トレードを再集計するのが正確だが、
    # 月別メトリクスから近似計算）
    for t in (total1, total2):
        t['win_rate'] = t['wins'] / t['trades'] * 100 if t['trades'] else 0
        t['pf'] = float('inf')  # 後で上書き

    # PFは月別をまとめてBacktestEngineで再実行して正確な値を取得
    for i, (month, csv_path) in enumerate(csv_months):
        pass  # 月別BacktestEngineは既に実行済み

    # 正確なトータルPFのために全CSVを結合して再実行
    def run_all_months(logic_module):
        dfs = []
        for _, csv_path in csv_months:
            bt = BacktestEngine(str(csv_path), logic_module)
            bt.load_data()
            dfs.append(bt.df)
        combined_df = pd.concat(dfs, ignore_index=True)
        bt2 = BacktestEngine.__new__(BacktestEngine)
        bt2.df = combined_df
        bt2.logic_module = logic_module
        bt2.pip_multiplier = 100
        bt2.trades = []
        bt2.current_position = bt2.entry_time = bt2.entry_price = None
        bt2.total_pips = bt2.win_count = bt2.loss_count = 0
        bt2.total_win_pips = bt2.total_loss_pips = 0
        # indicatorsは結合後に再計算が必要
        import numpy as np
        bt2.df['sma'] = bt2.df['close'].rolling(window=SMA_PERIOD).mean()
        ha_close = (bt2.df['open'] + bt2.df['high'] + bt2.df['low'] + bt2.df['close']) / 4
        ha_open = pd.Series(index=bt2.df.index, dtype=float)
        ha_open.iloc[0] = (bt2.df['open'].iloc[0] + bt2.df['close'].iloc[0]) / 2
        for i in range(1, len(bt2.df)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
        bt2.df['ha_open']        = ha_open
        bt2.df['ha_close']       = ha_close
        bt2.df['ha_high']        = pd.concat([bt2.df['high'], ha_open, ha_close], axis=1).max(axis=1)
        bt2.df['ha_low']         = pd.concat([bt2.df['low'],  ha_open, ha_close], axis=1).min(axis=1)
        bt2.df['ha_color']       = np.where(bt2.df['ha_close'] >= bt2.df['ha_open'], 1, -1)
        bt2.df['ha_body_top']    = bt2.df[['ha_open', 'ha_close']].max(axis=1)
        bt2.df['ha_body_bottom'] = bt2.df[['ha_open', 'ha_close']].min(axis=1)
        for idx in range(len(bt2.df)):
            just_exited = False
            if bt2.current_position == 'long' and bt2.logic_module.check_long_exit(bt2.df, idx):
                bt2._exit(idx)
                just_exited = True
            elif bt2.current_position == 'short' and bt2.logic_module.check_short_exit(bt2.df, idx):
                bt2._exit(idx)
                just_exited = True
            if bt2.current_position is None and not just_exited:
                if bt2.logic_module.check_long_entry(bt2.df, idx):
                    bt2._enter(idx, 'long')
                elif bt2.logic_module.check_short_entry(bt2.df, idx):
                    bt2._enter(idx, 'short')
        return bt2.metrics()

    print("\n3ヶ月合計を計算中...")
    t1 = run_all_months(logic1)
    t2 = run_all_months(logic2)

    print(f"\n=== 3ヶ月合計 ===")
    print(f"① pips={t1['pips']:.1f} trades={t1['trades']} wr={t1['win_rate']:.1f}% pf={t1['pf']:.2f} dd={t1['max_dd']:.1f}")
    print(f"② pips={t2['pips']:.1f} trades={t2['trades']} wr={t2['win_rate']:.1f}% pf={t2['pf']:.2f} dd={t2['max_dd']:.1f}")

    html = generate_html(rows, (t1, t2))
    OUTPUT_HTML.write_text(html, encoding='utf-8')
    print(f"\nHTML出力: {OUTPUT_HTML}")
