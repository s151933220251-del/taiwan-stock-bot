"""
交易策略
範例：均線黃金交叉買進、死亡交叉賣出。
要換策略只要寫一個有 generate(symbol, closes, position_qty) 方法的類別即可。
"""

from .models import Signal


def sma(values, window):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


class MovingAverageCrossStrategy:
    def __init__(self, short_window=5, long_window=20):
        if short_window >= long_window:
            raise ValueError("short_window 必須小於 long_window")
        self.short_window = short_window
        self.long_window = long_window

    def generate(self, symbol, closes, position_qty=0):
        """
        closes: 由舊到新的每日收盤價
        position_qty: 目前持股股數
        """
        if len(closes) < self.long_window + 1:
            return Signal(symbol, "HOLD", "資料不足（需要 {} 天）".format(self.long_window + 1))

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
