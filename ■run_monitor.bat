@echo off
rem monitor.py 起動バッチ
cd /d %~dp0
streamlit run live/monitor.py
pause
