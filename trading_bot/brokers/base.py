"""券商介面：策略與風控只依賴這個介面，換券商或模擬都不用改其他程式"""

from ..datafeed import fetch_daily_closes_finmind


class Broker:
    name = "base"

    def login(self):
        pass

    def logout(self):
        pass

    def get_positions(self):
        """回傳 {symbol: Position}"""
        raise NotImplementedError

    def get_cash(self):
        raise NotImplementedError

    def get_quote(self, symbol):
        """回傳最新成交價，取不到回傳 None"""
        raise NotImplementedError

    def get_daily_closes(self, symbol, days=60):
        return fetch_daily_closes_finmind(symbol, days)

    def place_order(self, order):
        """送出 OrderRequest，回傳 OrderResult"""
        raise NotImplementedError
