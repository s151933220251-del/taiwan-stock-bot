"""
回測工具：比較不同策略在歷史資料上的表現

  python backtest.py                                  # 用設定檔的股票，比較所有策略（近 3 年）
  python backtest.py --symbols 2884 0056 --years 5    # 指定股票與年數
  python backtest.py --strategy rsi --param oversold=25 --trades   # 單一策略、調參數、列出每筆交易
"""

import argparse
import time
import unicodedata
from datetime import datetime, timedelta

from trading_bot.backtest import run_backtest
from trading_bot.config import BotConfig
from trading_bot.datafeed import fetch_daily_bars_finmind
from trading_bot.strategy import STRATEGIES, create_strategy


def pad(text, width, right=False):
    """補空白對齊；中文字在命令列佔兩格寬"""
    text = str(text)
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    space = " " * max(0, width - w)
    return space + text if right else text + space


def row(*cells):
    first, rest = cells[0], cells[1:]
    return pad(first, 14) + "".join(pad(c, 10, right=True) for c in rest)


def parse_param(text):
    key, value = text.split("=", 1)
    try:
        value = float(value)
        if value.is_integer():
            value = int(value)
    except ValueError:
        pass
    return key, value


def parse_args(config):
    p = argparse.ArgumentParser(description="策略回測")
    p.add_argument("--config", default="trading_config.json")
    p.add_argument("--symbols", nargs="+", default=config.symbols)
    p.add_argument("--strategy", default="all", help="all 或 " + " / ".join(STRATEGIES))
    p.add_argument("--param", action="append", default=[], help="策略參數，例如 short_window=10")
    p.add_argument("--years", type=float, default=3)
    p.add_argument("--cash", type=float, default=config.paper_cash)
    p.add_argument("--buy-amount", type=float, default=config.strategy.buy_amount,
                   help="每次買進金額，0 代表全部現金")
    p.add_argument("--no-odd-lot", action="store_true", help="只買整張")
    p.add_argument("--min-fee", type=float, default=20, help="最低手續費（元）")
    p.add_argument("--trades", action="store_true", help="列出每一筆交易")
    return p.parse_args()


def print_trades(result):
    for t in result.trades:
        if t.closed:
            print("    {} 買 {} 股 @{:.2f} → {} 賣 @{:.2f}  損益 {:+,.0f} 元 ({:+.1f}%)".format(
                t.buy_date, t.shares, t.buy_price, t.sell_date, t.sell_price, t.pnl, t.return_pct))
        else:
            print("    {} 買 {} 股 @{:.2f} → 尚未賣出".format(t.buy_date, t.shares, t.buy_price))


def main():
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default="trading_config.json")
    config = BotConfig.load(pre.parse_known_args()[0].config)
    args = parse_args(config)

    params = dict(parse_param(x) for x in args.param)
    if args.strategy == "all":
        names = list(STRATEGIES)
    else:
        names = [args.strategy]
    allow_odd = not args.no_odd_lot

    start = (datetime.today() - timedelta(days=int(args.years * 365))).strftime("%Y-%m-%d")
    print("回測期間：{} ~ 今天　本金：{:,.0f} 元　每次買進：{}　零股：{}　最低手續費：{:.0f} 元".format(
        start, args.cash, "{:,.0f} 元".format(args.buy_amount) if args.buy_amount > 0 else "全部現金",
        "允許" if allow_odd else "不允許", args.min_fee))
    print("※ 未計入股利（高股息 ETF 的實際報酬會比這裡高）；過去績效不代表未來")

    for symbol in args.symbols:
        try:
            bars = fetch_daily_bars_finmind(symbol, start)
        except Exception as e:
            print("\n❌ {} 抓取資料失敗：{}".format(symbol, e))
            continue
        if len(bars) < 30:
            print("\n❌ {} 資料不足（{} 天）".format(symbol, len(bars)))
            continue

        print("\n" + "=" * 72)
        print("📈 {}（{} ~ {}，{} 個交易日）".format(symbol, bars[0]["date"], bars[-1]["date"], len(bars)))
        print(row("策略", "總報酬", "年化", "最大回撤", "交易次數", "勝率"))
        buy_hold = None
        for name in names:
            # 只有指定單一策略時，--param 才套用；全部比較時用預設參數或設定檔參數
            if args.strategy != "all":
                p = params
            elif name == config.strategy.name:
                p = config.strategy.params
            else:
                p = {}
            strategy = create_strategy(name, p)
            r = run_backtest(bars, strategy, symbol, cash=args.cash, buy_amount=args.buy_amount,
                             allow_odd_lot=allow_odd, min_fee=args.min_fee)
            buy_hold = r.buy_hold_return_pct
            print(row(strategy.label, "{:+.1f}%".format(r.total_return_pct),
                      "{:+.1f}%".format(r.annual_return_pct), "{:.1f}%".format(r.max_drawdown_pct),
                      len(r.closed_trades), "{:.0f}%".format(r.win_rate_pct)))
            if args.trades:
                print_trades(r)
        print(row("買進持有", "{:+.1f}%".format(buy_hold)) + "   ← 第一天買進一直抱著（不含股利）")
        time.sleep(0.5)  # 避免 FinMind 請求太頻繁


if __name__ == "__main__":
    main()
