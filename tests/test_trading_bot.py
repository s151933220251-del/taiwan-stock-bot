import os

import pytest

from trading_bot.bot import TradingBot
from trading_bot.brokers import PaperBroker
from trading_bot.config import BotConfig, RiskConfig
from trading_bot.models import OrderRequest, Position
from trading_bot.risk import RiskManager, round_to_tick, is_market_open, TW_TZ
from trading_bot.strategy import MovingAverageCrossStrategy
from datetime import datetime


# ---------- 策略 ----------

def golden_cross_series():
    # 長時間下跌後最後一天大漲，造成 MA3 上穿 MA5
    return [100, 99, 98, 97, 96, 95, 94, 93, 120]


def death_cross_series():
    return [90, 91, 92, 93, 94, 95, 96, 97, 70]


def test_strategy_buy_on_golden_cross():
    s = MovingAverageCrossStrategy(3, 5)
    assert s.generate("2330", golden_cross_series(), 0).action == "BUY"


def test_strategy_no_buy_when_already_holding():
    s = MovingAverageCrossStrategy(3, 5)
    assert s.generate("2330", golden_cross_series(), 1000).action == "HOLD"


def test_strategy_sell_on_death_cross_only_when_holding():
    s = MovingAverageCrossStrategy(3, 5)
    assert s.generate("2330", death_cross_series(), 1000).action == "SELL"
    assert s.generate("2330", death_cross_series(), 0).action == "HOLD"


def test_strategy_insufficient_data():
    s = MovingAverageCrossStrategy(3, 5)
    assert s.generate("2330", [1, 2, 3], 0).action == "HOLD"


# ---------- 升降單位 ----------

@pytest.mark.parametrize("price,direction,expected", [
    (33.33, "down", 33.3),
    (33.33, "up", 33.35),
    (33.3, "down", 33.3),     # 浮點誤差不應讓它掉一檔
    (99.95, "up", 100.0),
    (512.3, "down", 512.0),
    (1003, "up", 1005.0),
    (9.876, "down", 9.87),
])
def test_round_to_tick(price, direction, expected):
    assert round_to_tick(price, direction) == expected


def test_market_hours():
    assert is_market_open(datetime(2026, 10, 22, 10, 0, tzinfo=TW_TZ))
    assert not is_market_open(datetime(2026, 10, 22, 14, 0, tzinfo=TW_TZ))
    assert not is_market_open(datetime(2026, 10, 24, 10, 0, tzinfo=TW_TZ))  # 週六


# ---------- 風控 ----------

def make_risk(tmp_path, **kw):
    kw.setdefault("kill_switch_file", str(tmp_path / "STOP"))
    return RiskManager(RiskConfig(**kw))


def test_risk_blocks_odd_lot(tmp_path):
    ok, _ = make_risk(tmp_path).check(OrderRequest("2330", "BUY", 500, 100), 100, 0, check_hours=False)
    assert not ok


def test_risk_blocks_large_order(tmp_path):
    rm = make_risk(tmp_path, max_order_value=50000)
    ok, reason = rm.check(OrderRequest("2330", "BUY", 1000, 100), 100, 0, check_hours=False)
    assert not ok and "上限" in reason


def test_risk_blocks_price_deviation(tmp_path):
    ok, _ = make_risk(tmp_path).check(OrderRequest("2330", "BUY", 1000, 110), 100, 0, check_hours=False)
    assert not ok


def test_risk_blocks_short_sell(tmp_path):
    ok, _ = make_risk(tmp_path).check(OrderRequest("2330", "SELL", 2000, 100), 100, 1000, check_hours=False)
    assert not ok


def test_risk_daily_limit(tmp_path):
    rm = make_risk(tmp_path, max_daily_orders=1)
    order = OrderRequest("2330", "BUY", 1000, 100)
    assert rm.check(order, 100, 0, check_hours=False)[0]
    rm.record_order()
    assert not rm.check(order, 100, 0, check_hours=False)[0]


def test_risk_kill_switch(tmp_path):
    rm = make_risk(tmp_path)
    (tmp_path / "STOP").write_text("")
    ok, reason = rm.check(OrderRequest("2330", "BUY", 1000, 100), 100, 0, check_hours=False)
    assert not ok and "緊急停止" in reason


# ---------- 模擬券商 + 完整流程 ----------

class FakePaperBroker(PaperBroker):
    def __init__(self, series, **kw):
        super().__init__(**kw)
        self.series = series

    def get_daily_closes(self, symbol, days=60):
        return self.series[symbol][-days:]

    def get_quote(self, symbol):
        return self.series[symbol][-1]


def make_bot(tmp_path, series, dry_run=False, **risk_kw):
    risk_kw.setdefault("kill_switch_file", str(tmp_path / "STOP"))
    risk_kw.setdefault("max_order_value", 500000)
    risk_kw.setdefault("max_position_value", 500000)
    config = BotConfig(symbols=list(series), risk=RiskConfig(**risk_kw), log_dir=str(tmp_path / "logs"))
    broker = FakePaperBroker(series, cash=1000000, state_file=str(tmp_path / "state.json"))
    strategy = MovingAverageCrossStrategy(3, 5)
    return TradingBot(broker, strategy, config, dry_run=dry_run, check_hours=False,
                      notify_func=lambda m: None), broker


def test_bot_buys_then_does_not_repeat_same_day(tmp_path):
    bot, broker = make_bot(tmp_path, {"2330": golden_cross_series()})
    results = bot.run_once()
    assert len(results) == 1 and results[0].success
    assert broker.get_positions()["2330"].quantity == 1000
    assert broker.get_cash() == 1000000 - 120 * 1000

    # 重新啟動（新的 bot 物件）也不應該重複下單
    bot2, _ = make_bot(tmp_path, {"2330": golden_cross_series()})
    broker.positions = {}  # 模擬委託尚未成交、庫存還沒出現
    bot2.broker = broker
    assert bot2.run_once() == []


def test_bot_sells_whole_position(tmp_path):
    bot, broker = make_bot(tmp_path, {"2317": death_cross_series()})
    broker.positions["2317"] = Position("2317", 3000, 90)
    results = bot.run_once()
    assert results[0].request.action == "SELL"
    assert results[0].request.quantity == 3000
    assert "2317" not in broker.get_positions()


def test_bot_dry_run_does_not_touch_broker(tmp_path):
    bot, broker = make_bot(tmp_path, {"2330": golden_cross_series()}, dry_run=True)
    results = bot.run_once()
    assert results[0].success and "試跑" in results[0].message
    assert broker.get_positions() == {}
    assert os.path.exists(bot._log_path())


def test_bot_respects_risk(tmp_path):
    bot, broker = make_bot(tmp_path, {"2330": golden_cross_series()}, max_order_value=1000)
    assert bot.run_once() == []
    assert broker.get_positions() == {}
