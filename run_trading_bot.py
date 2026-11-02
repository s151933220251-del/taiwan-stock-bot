"""
台股自動交易機器人 - 執行入口

  python run_trading_bot.py                         # 模擬交易（預設，不連券商）
  python run_trading_bot.py --broker fubon          # 連富邦讀庫存/報價，但不送單（試跑）
  TRADING_MODE=live python run_trading_bot.py --broker fubon --live   # 真的下單
  加上 --loop 5 代表交易時段內每 5 分鐘執行一次
"""

import argparse
import os
import time

from trading_bot.bot import TradingBot
from trading_bot.brokers import PaperBroker
from trading_bot.config import BotConfig, FubonCredentials
from trading_bot.risk import is_market_open, now_tw
from trading_bot.strategy import create_strategy


def load_dotenv(path=".env"):
    """讀取 .env（不覆蓋已存在的環境變數）"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def parse_args():
    p = argparse.ArgumentParser(description="台股自動交易機器人")
    p.add_argument("--config", default="trading_config.json")
    p.add_argument("--broker", choices=["paper", "fubon"], default="paper")
    p.add_argument("--live", action="store_true", help="真的送出委託（需同時設定環境變數 TRADING_MODE=live）")
    p.add_argument("--loop", type=int, default=0, help="每 N 分鐘執行一次，0 代表只跑一次")
    p.add_argument("--ignore-hours", action="store_true", help="不檢查交易時段（僅限模擬模式）")
    return p.parse_args()


def main():
    load_dotenv()
    args = parse_args()
    config = BotConfig.load(args.config)

    if args.live:
        if args.broker != "fubon":
            raise SystemExit("--live 只能搭配 --broker fubon")
        if os.environ.get("TRADING_MODE") != "live":
            raise SystemExit("拒絕實盤：請同時設定環境變數 TRADING_MODE=live 以確認要真的下單")
    if args.ignore_hours and args.broker != "paper":
        raise SystemExit("--ignore-hours 只能用在模擬模式")

    if args.broker == "fubon":
        from trading_bot.brokers.fubon import FubonBroker
        broker = FubonBroker(FubonCredentials.from_env())
    else:
        broker = PaperBroker(cash=config.paper_cash,
                             state_file=os.path.join(config.log_dir, "paper_state.json"))

    strategy = create_strategy(config.strategy.name, config.strategy.params)
    # 模擬券商本身就不會下真單，所以讓它走完整下單流程；富邦券商沒有 --live 就只試跑
    dry_run = args.broker == "fubon" and not args.live
    bot = TradingBot(broker, strategy, config, dry_run=dry_run,
                     check_hours=not args.ignore_hours)

    if args.live:
        print("⚠️⚠️⚠️ 實盤模式：將會送出真實委託 ⚠️⚠️⚠️")

    broker.login()
    try:
        if args.loop <= 0:
            bot.run_once()
            return
        while True:
            if is_market_open() or args.ignore_hours:
                bot.run_once()
            else:
                print(now_tw().strftime("%H:%M") + " 非交易時段，等待中...")
            time.sleep(args.loop * 60)
    except KeyboardInterrupt:
        print("手動停止")
    finally:
        broker.logout()


if __name__ == "__main__":
    main()
