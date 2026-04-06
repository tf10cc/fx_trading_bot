@echo off
rem backtest.py 起動バッチ
cd /d %~dp0
streamlit run backtest/backtest.py
pause
