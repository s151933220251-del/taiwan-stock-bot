"""
模擬券商：不連任何券商，限價單直接以委託價成交。
持倉與現金存在 JSON 檔，重跑程式會延續上次的狀態。
"""

import json
import os
import uuid

from .base import Broker
from ..models import OrderResult, Position


class PaperBroker(Broker):
    name = "paper"

    def __init__(self, cash=1000000.0, state_file="logs/paper_state.json", quote_func=None):
        self.state_file = state_file
        self.quote_func = quote_func
        self.cash = cash
        self.positions = {}
        self._load()

    def _load(self):
        if not self.state_file or not os.path.exists(self.state_file):
            return
        with open(self.state_file, encoding="utf-8") as f:
            raw = json.load(f)
        self.cash = raw.get("cash", self.cash)
        self.positions = {s: Position(**p) for s, p in raw.get("positions", {}).items()}

    def _save(self):
        if not self.state_file:
            return
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({
                "cash": self.cash,
                "positions": {s: p.__dict__ for s, p in self.positions.items()},
            }, f, ensure_ascii=False, indent=2)

    def get_positions(self):
        return dict(self.positions)

    def get_cash(self):
        return self.cash

    def get_quote(self, symbol):
        if self.quote_func:
            return self.quote_func(symbol)
        closes = self.get_daily_closes(symbol, days=1)
        return closes[-1] if closes else None

    def place_order(self, order):
        pos = self.positions.get(order.symbol, Position(order.symbol, 0, 0.0))
        if order.action == "BUY":
            if order.value > self.cash:
                return OrderResult(False, message="模擬帳戶現金不足", request=order)
            total = pos.quantity + order.quantity
            pos.avg_price = (pos.avg_price * pos.quantity + order.value) / total
            pos.quantity = total
            self.cash -= order.value
        else:
            if order.quantity > pos.quantity:
                return OrderResult(False, message="模擬帳戶庫存不足", request=order)
            pos.quantity -= order.quantity
            self.cash += order.value

        if pos.quantity > 0:
            self.positions[order.symbol] = pos
        else:
            self.positions.pop(order.symbol, None)
        self._save()
        return OrderResult(True, order_no="PAPER-" + uuid.uuid4().hex[:8], message="模擬成交", request=order)
