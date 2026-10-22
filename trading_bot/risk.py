"""
風險控管：每一筆委託送出前都必須通過這裡的檢查
"""

import math
import os
from datetime import datetime, time, timedelta, timezone

from .models import SHARES_PER_LOT

TW_TZ = timezone(timedelta(hours=8))
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(13, 30)


def now_tw():
    return datetime.now(TW_TZ)


def is_market_open(dt=None):
    """台股一般交易時段：週一至週五 09:00-13:30（不含國定假日判斷，假日送單會被券商拒絕）"""
    dt = dt or now_tw()
    if dt.weekday() >= 5:
        return False
    return MARKET_OPEN <= dt.time() <= MARKET_CLOSE


def tick_size(price):
    """台股升降單位"""
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0


def round_to_tick(price, direction="down"):
    """把價格對齊到合法的升降單位。買單用 up、賣單用 down，讓限價單容易成交"""
    tick = tick_size(price)
    steps = round(price / tick, 6)  # 消除浮點誤差，例如 33.3 / 0.05 = 665.999...
    if direction == "up":
        steps = math.ceil(steps)
    else:
        steps = math.floor(steps)
    return round(steps * tick, 2)


class RiskManager:
    def __init__(self, config):
        self.config = config
        self.orders_today = 0
        self._day = now_tw().date()

    def _reset_if_new_day(self):
        today = now_tw().date()
        if today != self._day:
            self._day = today
            self.orders_today = 0

    def check(self, order, ref_price, current_qty, check_hours=True):
        """回傳 (是否通過, 原因)"""
        self._reset_if_new_day()
        c = self.config

        if os.path.exists(c.kill_switch_file):
            return False, "偵測到緊急停止檔案 " + c.kill_switch_file
        if check_hours and not is_market_open():
            return False, "非交易時段"
        if order.quantity <= 0 or order.quantity % SHARES_PER_LOT != 0:
            return False, "股數必須是 1000 的倍數（整股）"
        if order.price <= 0 or ref_price <= 0:
            return False, "價格無效"
        if abs(order.price - ref_price) / ref_price > c.max_price_deviation:
            return False, "委託價 {} 偏離參考價 {} 超過 {:.0%}".format(
                order.price, ref_price, c.max_price_deviation)
        if self.orders_today >= c.max_daily_orders:
            return False, "已達每日委託上限 {} 筆".format(c.max_daily_orders)

        if order.action == "BUY":
            if order.value > c.max_order_value:
                return False, "單筆金額 {:,.0f} 超過上限 {:,.0f}".format(order.value, c.max_order_value)
            if (current_qty + order.quantity) * ref_price > c.max_position_value:
                return False, "買進後持股市值將超過上限 {:,.0f}".format(c.max_position_value)
        elif order.action == "SELL":
            if order.quantity > current_qty:
                return False, "賣出股數 {} 大於庫存 {}（不做融券放空）".format(order.quantity, current_qty)
        else:
            return False, "未知的買賣別 " + str(order.action)

        return True, "OK"

    def record_order(self):
        self._reset_if_new_day()
        self.orders_today += 1
