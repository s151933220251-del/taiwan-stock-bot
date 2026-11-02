"""
回測引擎：用歷史日K模擬策略的績效

規則（盡量貼近真實）：
- 當天收盤後才判斷訊號，隔天開盤價成交（避免偷看未來）
- 買賣都收手續費（預設 0.1425%，有最低手續費），賣出另收證交稅（股票 0.3%、ETF 0.1%）
- 部位大小與實盤一致：每次用 buy_amount 買進，可選擇是否允許零股
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

from .models import shares_for_amount

FEE_RATE = 0.001425
STOCK_TAX = 0.003
ETF_TAX = 0.001


def tax_rate_for(symbol):
    """台灣 ETF 代號以 00 開頭，證交稅 0.1%"""
    return ETF_TAX if str(symbol).startswith("00") else STOCK_TAX


def calc_fee(value, fee_rate=FEE_RATE, min_fee=20):
    return max(min_fee, math.floor(value * fee_rate))


@dataclass
class Trade:
    buy_date: str
    buy_price: float
    shares: int
    cost: float                  # 含手續費的總成本
    sell_date: str = ""
    sell_price: float = 0.0
    proceeds: float = 0.0        # 扣手續費與稅後拿回的錢

    @property
    def closed(self):
        return bool(self.sell_date)

    @property
    def pnl(self):
        return self.proceeds - self.cost

    @property
    def return_pct(self):
        return self.pnl / self.cost * 100 if self.cost else 0.0


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_cash: float
    final_equity: float
    max_drawdown_pct: float
    buy_hold_return_pct: float
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)   # [(date, equity)]

    @property
    def total_return_pct(self):
        return (self.final_equity / self.initial_cash - 1) * 100

    @property
    def annual_return_pct(self):
        days = (datetime.strptime(self.end_date, "%Y-%m-%d") -
                datetime.strptime(self.start_date, "%Y-%m-%d")).days
        if days <= 0 or self.final_equity <= 0:
            return 0.0
        return ((self.final_equity / self.initial_cash) ** (365 / days) - 1) * 100

    @property
    def closed_trades(self):
        return [t for t in self.trades if t.closed]

    @property
    def win_rate_pct(self):
        closed = self.closed_trades
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.pnl > 0) / len(closed) * 100


def run_backtest(bars, strategy, symbol="", cash=100000.0, buy_amount=0.0,
                 allow_odd_lot=True, min_fee=20, fee_rate=FEE_RATE, tax_rate=None):
    """
    bars: 由舊到新的日K list，每筆 {"date", "open", "close"}
    buy_amount: 每次買進金額，0 代表用全部現金
    """
    if len(bars) < 2:
        raise ValueError("資料太少，無法回測")
    tax_rate = tax_rate_for(symbol) if tax_rate is None else tax_rate

    initial_cash = cash
    shares = 0
    trades = []
    pending = None             # 前一天收盤產生、今天開盤要執行的訊號
    equity_curve = []
    peak = initial_cash
    max_dd = 0.0
    closes = []

    for bar in bars:
        price = bar["open"]
        # 1) 開盤：執行昨天的訊號
        if pending == "BUY" and shares == 0:
            budget = min(buy_amount, cash) if buy_amount > 0 else cash
            qty = shares_for_amount(budget / (1 + fee_rate), price, allow_odd_lot)
            step = 1 if allow_odd_lot else 1000
            while qty > 0 and qty * price + calc_fee(qty * price, fee_rate, min_fee) > cash:
                qty -= step
            if qty > 0:
                cost = qty * price + calc_fee(qty * price, fee_rate, min_fee)
                cash -= cost
                shares = qty
                trades.append(Trade(bar["date"], price, qty, cost))
        elif pending == "SELL" and shares > 0:
            value = shares * price
            proceeds = value - calc_fee(value, fee_rate, min_fee) - math.floor(value * tax_rate)
            cash += proceeds
            t = trades[-1]
            t.sell_date, t.sell_price, t.proceeds = bar["date"], price, proceeds
            shares = 0
        pending = None

        # 2) 收盤：記錄淨值，產生明天要執行的訊號
        closes.append(bar["close"])
        equity = cash + shares * bar["close"]
        equity_curve.append((bar["date"], equity))
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0)

        signal = strategy.generate(symbol, closes, shares)
        if signal.action in ("BUY", "SELL"):
            pending = signal.action

    first, last = bars[0], bars[-1]
    return BacktestResult(
        symbol=symbol,
        strategy=getattr(strategy, "name", type(strategy).__name__),
        start_date=first["date"],
        end_date=last["date"],
        initial_cash=initial_cash,
        final_equity=equity_curve[-1][1],
        max_drawdown_pct=max_dd,
        buy_hold_return_pct=(last["close"] / first["open"] - 1) * 100,
        trades=trades,
        equity_curve=equity_curve,
    )
