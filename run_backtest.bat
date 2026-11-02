@echo off
rem Double-click to compare all strategies on the stocks in trading_config.json
cd /d "%~dp0"
python backtest.py
pause
