@echo off
rem backtest.py 起動バッチ
cd /d %~dp0
start "" "C:\Users\tf10c\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe" -m streamlit run backtest/backtest.py
