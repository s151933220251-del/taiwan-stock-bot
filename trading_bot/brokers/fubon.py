"""
富邦證券新一代 API（fubon_neo）串接

安裝：fubon_neo 不在 PyPI，需到富邦證券官網「新一代API」頁面下載對應作業系統的 .whl：
    pip install fubon_neo-<版本>-cp37-abi3-<平台>.whl

所有 SDK 呼叫都集中在這個檔案。若富邦 SDK 版本更新導致欄位名稱改變，只需要改這裡。
"""

from datetime import datetime, timedelta

from .base import Broker
from ..models import OrderResult, Position


class FubonBroker(Broker):
    name = "fubon"

    def __init__(self, credentials):
        self.cred = credentials
        self.sdk = None
        self.account = None
        self.rest_stock = None

    # ---------- 連線 ----------

    def login(self):
        missing = self.cred.missing()
        if missing:
            raise RuntimeError("富邦登入資料未設定：" + ", ".join(missing))
        try:
            from fubon_neo.sdk import FubonSDK
        except ImportError:
            raise RuntimeError("找不到 fubon_neo 套件，請先從富邦官網下載 SDK 安裝")

        self.sdk = FubonSDK()
        result = self.sdk.login(self.cred.personal_id, self.cred.password,
                                self.cred.cert_path, self.cred.cert_password)
        if not result.is_success:
            raise RuntimeError("富邦登入失敗：" + str(result.message))

        accounts = result.data
        if self.cred.account_no:
            matched = [a for a in accounts if str(a.account) == self.cred.account_no]
            if not matched:
                raise RuntimeError("找不到指定帳號 " + self.cred.account_no)
            self.account = matched[0]
        else:
            self.account = accounts[0]
        print("✅ 富邦登入成功，使用帳號 " + str(self.account.account)[-4:].rjust(8, "*"))

        try:
            self.sdk.init_realtime()
            self.rest_stock = self.sdk.marketdata.rest_client.stock
        except Exception as e:
            print("⚠️ 富邦行情初始化失敗，改用 FinMind 日K：" + str(e))

    def logout(self):
        if self.sdk:
            try:
                self.sdk.logout()
            except Exception as e:
                print("登出失敗：" + str(e))

    # ---------- 帳務 ----------

    def get_positions(self):
        result = self.sdk.accounting.inventories(self.account)
        if not result.is_success:
            raise RuntimeError("查詢庫存失敗：" + str(result.message))
        positions = {}
        for inv in result.data or []:
            symbol = str(getattr(inv, "stock_no", "")).strip()
            # 整股庫存（股數）；零股另計，這個機器人只交易整股
            qty = int(getattr(inv, "today_qty", 0) or 0)
            if symbol and qty > 0:
                positions[symbol] = Position(symbol, qty, 0.0)
        return positions

    def get_cash(self):
        result = self.sdk.accounting.bank_remain(self.account)
        if not result.is_success:
            raise RuntimeError("查詢銀行餘額失敗：" + str(result.message))
        data = result.data
        return float(getattr(data, "available_balance", None) or getattr(data, "balance", 0) or 0)

    # ---------- 行情 ----------

    def get_quote(self, symbol):
        if not self.rest_stock:
            closes = self.get_daily_closes(symbol, days=1)
            return closes[-1] if closes else None
        q = self.rest_stock.intraday.quote(symbol=symbol)
        for key in ("lastPrice", "closePrice", "referencePrice"):
            if q.get(key):
                return float(q[key])
        return None

    def get_daily_closes(self, symbol, days=60):
        if not self.rest_stock:
            return super().get_daily_closes(symbol, days)
        end = datetime.today()
        start = end - timedelta(days=int(days * 1.6) + 10)
        try:
            resp = self.rest_stock.historical.candles(**{
                "symbol": symbol,
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "timeframe": "D",
            })
            rows = sorted(resp.get("data", []), key=lambda x: x["date"])
            closes = [float(r["close"]) for r in rows]
            if closes:
                return closes[-days:]
        except Exception as e:
            print("富邦歷史K線失敗，改用 FinMind：" + str(e))
        return super().get_daily_closes(symbol, days)

    # ---------- 下單 ----------

    def place_order(self, order):
        from fubon_neo.sdk import Order
        from fubon_neo.constant import BSAction, MarketType, OrderType, PriceType, TimeInForce

        sdk_order = Order(
            buy_sell=BSAction.Buy if order.action == "BUY" else BSAction.Sell,
            symbol=order.symbol,
            price=str(order.price),
            quantity=int(order.quantity),
            market_type=MarketType.Common,      # 整股
            price_type=PriceType.Limit,         # 限價
            time_in_force=TimeInForce.ROD,      # 當日有效
            order_type=OrderType.Stock,         # 現股
            user_def="tw-bot",
        )
        result = self.sdk.stock.place_order(self.account, sdk_order)
        if result.is_success:
            order_no = str(getattr(result.data, "order_no", "") or "")
            return OrderResult(True, order_no=order_no, message="委託成功", request=order)
        return OrderResult(False, message=str(result.message), request=order)
