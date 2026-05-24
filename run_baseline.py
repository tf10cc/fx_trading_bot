import sys
import importlib.util

spec = importlib.util.spec_from_file_location('logic', 'logics/heikin_ashi_75sma.py')
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

spec2 = importlib.util.spec_from_file_location('backtest_engine', 'backtest/backtest_engine.py')
engine_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(engine_mod)
BacktestEngine = engine_mod.BacktestEngine

months = [
    ('Jul-2024', 'data/USD-JPY_Hour_2024-07-01_to_2024-07-31_UTC.csv'),
    ('Aug-2024', 'data/USD-JPY_Hour_2024-08-01_to_2024-08-31_UTC.csv'),
    ('Sep-2024', 'data/USD-JPY_Hour_2024-09-01_to_2024-09-30_UTC.csv'),
]

print(f"{'Month':<10} {'Total(p)':>10} {'Trades':>7} {'WinRate':>8} {'MaxDD(p)':>10} {'PF':>6}")
print('-' * 56)

for label, csv_path in months:
    engine = BacktestEngine(csv_path, logic, pip_multiplier=100)
    engine.run()
    m = engine.calculate_metrics()
    pf = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else 'inf'
    print(f"{label:<10} {m['total_pips']:>10.2f} {m['total_trades']:>7} {m['win_rate']:>7.2f}% {m['max_drawdown']:>10.2f} {pf:>6}")
