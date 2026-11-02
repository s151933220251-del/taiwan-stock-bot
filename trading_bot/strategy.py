"""
交易策略
每個策略都有：
- min_bars：至少需要幾根日K才能判斷
- generate(symbol, closes, position_qty)：回傳 Signal（BUY / SELL / HOLD）

要新增策略：寫一個類別，再加進最下面的 STRATEGIES 即可，機器人與回測都能直接使用。
"""

from .models import Signal


def sma(values, window):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values, period=14):
    """簡單平均版 RSI"""
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for prev, cur in zip(values[-period - 1:-1], values[-period:]):
        diff = cur - prev
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


class MovingAverageCrossStrategy:
    """均線交叉：短均線上穿長均線買進，下穿賣出"""
    name = "ma_cross"
    label = "均線交叉"

    def __init__(self, short_window=5, long_window=20):
        if short_window >= long_window:
            raise ValueError("short_window 必須小於 long_window")
        self.short_window = short_window
        self.long_window = long_window

    @property
    def min_bars(self):
        return self.long_window + 1

    def generate(self, symbol, closes, position_qty=0):
        if len(closes) < self.min_bars:
            return Signal(symbol, "HOLD", "資料不足（需要 {} 天）".format(self.min_bars))

        prev_short = sma(closes[:-1], self.short_window)
        prev_long = sma(closes[:-1], self.long_window)
        cur_short = sma(closes, self.short_window)
        cur_long = sma(closes, self.long_window)

        crossed_up = prev_short <= prev_long and cur_short > cur_long
        crossed_down = prev_short >= prev_long and cur_short < cur_long
        desc = "MA{}={:.2f} MA{}={:.2f}".format(self.short_window, cur_short, self.long_window, cur_long)

        if crossed_up and position_qty == 0:
            return Signal(symbol, "BUY", "黃金交叉 " + desc)
        if crossed_down and position_qty > 0:
            return Signal(symbol, "SELL", "死亡交叉 " + desc)
        return Signal(symbol, "HOLD", desc)


class RSIStrategy:
    """RSI 超賣反彈：RSI 從超賣區往上穿越時買進，進入超買區時賣出"""
    name = "rsi"
    label = "RSI反彈"

    def __init__(self, period=14, oversold=30, overbought=70):
        if not 0 < oversold < overbought < 100:
            raise ValueError("必須 0 < oversold < overbought < 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def min_bars(self):
        return self.period + 2

    def generate(self, symbol, closes, position_qty=0):
        if len(closes) < self.min_bars:
            return Signal(symbol, "HOLD", "資料不足（需要 {} 天）".format(self.min_bars))
        prev = rsi(closes[:-1], self.period)
        cur = rsi(closes, self.period)
        desc = "RSI{}={:.1f}".format(self.period, cur)
        if position_qty == 0 and prev < self.oversold <= cur:
            return Signal(symbol, "BUY", "RSI 脫離超賣區 " + desc)
        if position_qty > 0 and cur > self.overbought:
            return Signal(symbol, "SELL", "RSI 進入超買區 " + desc)
        return Signal(symbol, "HOLD", desc)


class BreakoutStrategy:
    """突破策略：收盤創 N 日新高買進，跌破 M 日新低賣出（海龜交易法的簡化版）"""
    name = "breakout"
    label = "突破新高"

    def __init__(self, entry_window=20, exit_window=10):
        self.entry_window = entry_window
        self.exit_window = exit_window

    @property
    def min_bars(self):
        return max(self.entry_window, self.exit_window) + 1

    def generate(self, symbol, closes, position_qty=0):
        if len(closes) < self.min_bars:
            return Signal(symbol, "HOLD", "資料不足（需要 {} 天）".format(self.min_bars))
        cur = closes[-1]
        high = max(closes[-self.entry_window - 1:-1])
        low = min(closes[-self.exit_window - 1:-1])
        desc = "收盤={:.2f} {}日高={:.2f} {}日低={:.2f}".format(
            cur, self.entry_window, high, self.exit_window, low)
        if position_qty == 0 and cur > high:
            return Signal(symbol, "BUY", "突破新高 " + desc)
        if position_qty > 0 and cur < low:
            return Signal(symbol, "SELL", "跌破新低 " + desc)
        return Signal(symbol, "HOLD", desc)


STRATEGIES = {
    MovingAverageCrossStrategy.name: MovingAverageCrossStrategy,
    RSIStrategy.name: RSIStrategy,
    BreakoutStrategy.name: BreakoutStrategy,
}


def create_strategy(name, params=None):
    if name not in STRATEGIES:
        raise ValueError("未知的策略 {}，可用：{}".format(name, ", ".join(STRATEGIES)))
    return STRATEGIES[name](**(params or {}))
