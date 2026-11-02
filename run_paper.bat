@echo off
rem Double-click to run the trading bot in paper (simulation) mode
cd /d "%~dp0"
python run_trading_bot.py --ignore-hours
pause
