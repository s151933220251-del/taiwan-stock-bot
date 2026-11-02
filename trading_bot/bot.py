"""
交易主流程：抓資料 → 策略產生訊號 → 風控檢查 → 下單 → 記錄與通知
"""

import json
import os

from .models import SHARES_PER_LOT, OrderRequest, OrderResult, shares_for_amount, split_lots
from .notifier import notify
from .risk import RiskManager, now_tw, round_to_tick


class TradingBot:
    def __init__(self, broker, strategy, config, dry_run=True, check_hours=True, notify_func=notify):
        self.broker = broker
        self.strategy = strategy
        self.config = config
        self.dry_run = dry_run
        self.check_hours = check_hours
        self.notify = notify_func
        self.risk = RiskManager(config.risk)
        self.traded_today = set()
        self._load_today_log()

    # ---------- 委託紀錄 ----------

    def _log_path(self):
        return os.path.join(self.config.log_dir, "orders-" + now_tw().strftime("%Y%m%d") + ".jsonl")

    def _load_today_log(self):
        """重新啟動時恢復今日已委託的筆數與股票，避免重複下單或繞過每日上限"""
        path = self._log_path()
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("success") and not rec.get("dry_run"):
                    self.risk.record_order()
                    self.traded_today.add(rec["request"]["symbol"])

    def _write_log(self, result):
        os.makedirs(self.config.log_dir, exist_ok=True)
        rec = result.to_dict()
        rec["broker"] = self.broker.name
        rec["dry_run"] = self.dry_run
        with open(self._log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------- 主流程 ----------

    def build_orders(self, signal, position_qty, quote):
        """依訊號產生委託；有零股時拆成「整股」與「盤中零股」兩筆"""
        sc = self.config.strategy
        if signal.action == "BUY":
            price = round_to_tick(quote, "up")
            if sc.buy_amount > 0:
                qty = shares_for_amount(sc.buy_amount, price, sc.allow_odd_lot)
            else:
                qty = sc.lots_per_trade * SHARES_PER_LOT
        elif signal.action == "SELL":
            price = round_to_tick(quote, "down")
            qty = position_qty if sc.allow_odd_lot else (position_qty // SHARES_PER_LOT) * SHARES_PER_LOT
        else:
            return []
        return [OrderRequest(signal.symbol, signal.action, q, price, signal.reason)
                for q in split_lots(qty)]

    def run_once(self):
        print("=" * 40)
        print("🤖 執行策略 {}（券商：{}，{}）".format(
            now_tw().strftime("%Y-%m-%d %H:%M"), self.broker.name,
            "試跑不送單" if self.dry_run else "會送出委託"))
        positions = self.broker.get_positions()
        results = []

        for symbol in self.config.symbols:
            try:
                results.extend(self._process_symbol(symbol, positions))
            except Exception as e:
                self.notify("❌ {} 處理失敗：{}".format(symbol, e))
        return results

    def _process_symbol(self, symbol, positions):
        pos = positions.get(symbol)
        qty_held = pos.quantity if pos else 0
        closes = self.broker.get_daily_closes(symbol, self.strategy.min_bars + 5)
        signal = self.strategy.generate(symbol, closes, qty_held)
        print("  {} 持有 {} 股 → {}（{}）".format(symbol, qty_held, signal.action, signal.reason))
        if signal.action == "HOLD":
            return []

        if symbol in self.traded_today:
            print("  {} 今日已委託過，略過".format(symbol))
            return []

        quote = self.broker.get_quote(symbol)
        if not quote:
            print("  {} 取不到報價，略過".format(symbol))
            return []

        orders = self.build_orders(signal, qty_held, quote)
        if not orders:
            print("  {} 沒有可下單的股數（金額不足 1 股，或未開啟零股），略過".format(symbol))
            return []

        results = []
        running_qty = qty_held
        for order in orders:
            result = self._submit(order, quote, running_qty)
            if result is None:
                break
            results.append(result)
            if result.success:
                running_qty += order.quantity if order.action == "BUY" else -order.quantity
        if results and not self.dry_run:
            self.traded_today.add(symbol)
        return results

    def _submit(self, order, quote, current_qty):
        ok, reason = self.risk.check(order, quote, current_qty, check_hours=self.check_hours)
        if not ok:
            self.notify("🛑 風控擋單 {} {} {}股 @{}：{}".format(
                order.action, order.symbol, order.quantity, order.price, reason))
            return None

        if self.dry_run:
            result = OrderResult(True, message="試跑模式，未送出", request=order)
        else:
            result = self.broker.place_order(order)
        if result.success and not self.dry_run:
            self.risk.record_order()
        self._write_log(result)

        icon = "✅" if result.success else "❌"
        tag = "[試跑] " if self.dry_run else ""
        self.notify("{} {}{} {} {} 股{} @{}\n原因：{}\n結果：{} {}".format(
            icon, tag, "買進" if order.action == "BUY" else "賣出", order.symbol,
            order.quantity, "（零股）" if order.is_odd_lot else "", order.price, order.reason,
            result.message, result.order_no))
        return result
