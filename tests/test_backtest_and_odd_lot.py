import json

import pytest

from trading_bot.backtest import run_backtest, calc_fee, tax_rate_for
from trading_bot.config import BotConfig, RiskConfig, StrategyConfig
from trading_bot.models import OrderRequest, Signal, shares_for_amount, split_lots
from trading_bot.risk import RiskManager
from trading_bot.strategy import RSIStrategy, BreakoutStrategy, create_strategy

from test_trading_bot import FakePaperBroker, golden_cross_series
from trading_bot.bot import TradingBot


# ---------- 零股工具 ----------

def test_shares_for_amount():
    assert shares_for_amount(45000, 30, True) == 1500
    assert shares_for_amount(45000, 30, False) == 1000
    assert shares_for_amount(45000, 1000, False) == 0
    assert shares_for_amount(45000, 1000, True) == 45


@pytest.mark.parametrize("qty,expected", [(2350, [2000, 350]), (1000, [1000]), (45, [45]), (0, [])])
def test_split_lots(qty, expected):
    assert split_lots(qty) == expected


def test_risk_allows_odd_lot_but_not_mixed(tmp_path):
    rm = RiskManager(RiskConfig(kill_switch_file=str(tmp_path / "STOP")))
    assert rm.check(OrderRequest("2330", "BUY", 45, 1000), 1000, 0, check_hours=False)[0]
    assert not rm.check(OrderRequest("2330", "BUY", 1500, 30), 30, 0, check_hours=False)[0]


def make_odd_bot(tmp_path, buy_amount, allow_odd=True, dry_run=False):
    config = BotConfig(
        symbols=["2330"],
        strategy=StrategyConfig(params={"short_window": 3, "long_window": 5},
                                buy_amount=buy_amount, allow_odd_lot=allow_odd),
        risk=RiskConfig(max_order_value=500000, max_position_value=500000,
                        kill_switch_file=str(tmp_path / "STOP")),
        log_dir=str(tmp_path / "logs"))
    broker = FakePaperBroker({"2330": golden_cross_series()}, cash=100000,
                             state_file=str(tmp_path / "state.json"))
    strategy = create_strategy("ma_cross", config.strategy.params)
    return TradingBot(broker, strategy, config, dry_run=dry_run, check_hours=False,
                      notify_func=lambda m: None), broker


def test_bot_buys_odd_lot(tmp_path):
    bot, broker = make_odd_bot(tmp_path, buy_amount=50000)
    results = bot.run_once()
    # 價格 120，5 萬元 → 416 股，全部是零股
    assert [r.request.quantity for r in results] == [416]
    assert broker.get_positions()["2330"].quantity == 416


def test_bot_splits_lot_and_odd(tmp_path):
    bot, broker = make_odd_bot(tmp_path, buy_amount=150000)
    broker.cash = 1000000
    results = bot.run_once()
    assert [r.request.quantity for r in results] == [1000, 250]
    assert broker.get_positions()["2330"].quantity == 1250


def test_bot_skips_when_odd_lot_disabled_and_amount_too_small(tmp_path):
    bot, broker = make_odd_bot(tmp_path, buy_amount=50000, allow_odd=False)
    assert bot.run_once() == []


# ---------- 設定檔相容 ----------

def test_config_legacy_strategy_format(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"strategy": {"short_window": 3, "long_window": 8, "lots_per_trade": 1}}))
    cfg = BotConfig.load(str(p))
    assert cfg.strategy.name == "ma_cross"
    assert cfg.strategy.params == {"short_window": 3, "long_window": 8}


# ---------- 其他策略 ----------

def test_rsi_strategy():
    s = RSIStrategy(period=5, oversold=30, overbought=70)
    falling_then_up = [100, 95, 90, 85, 80, 75, 70, 80]
    assert s.generate("x", falling_then_up, 0).action == "BUY"
    rising = [50, 52, 54, 56, 58, 60, 62, 64]
    assert s.generate("x", rising, 100).action == "SELL"
    assert s.generate("x", rising, 0).action == "HOLD"


def test_breakout_strategy():
    s = BreakoutStrategy(entry_window=3, exit_window=2)
    assert s.generate("x", [10, 11, 12, 11, 13], 0).action == "BUY"
    assert s.generate("x", [10, 11, 12, 11, 9], 100).action == "SELL"
    assert s.generate("x", [10, 11, 12, 11, 11.5], 0).action == "HOLD"


def test_create_strategy_unknown():
    with pytest.raises(ValueError):
        create_strategy("nope")


# ---------- 回測引擎 ----------

class ScriptedStrategy:
    """第 2 天收盤買、第 3 天收盤賣"""
    name = "scripted"
    min_bars = 1

    def generate(self, symbol, closes, position_qty=0):
        if len(closes) == 2:
            return Signal(symbol, "BUY")
        if len(closes) == 3 and position_qty > 0:
            return Signal(symbol, "SELL")
        return Signal(symbol, "HOLD")


BARS = [
    {"date": "2024-01-01", "open": 10, "close": 10},
    {"date": "2024-01-02", "open": 10, "close": 10},
    {"date": "2024-01-03", "open": 11, "close": 12},
    {"date": "2024-01-04", "open": 13, "close": 14},
]


def test_backtest_executes_next_open_with_costs():
    r = run_backtest(BARS, ScriptedStrategy(), "2884", cash=10000, allow_odd_lot=True, min_fee=20)
    t = r.trades[0]
    # 隔天開盤成交：第 3 天開盤 11 買、第 4 天開盤 13 賣
    assert (t.buy_date, t.buy_price, t.shares) == ("2024-01-03", 11, 907)
    assert t.cost == 907 * 11 + 20
    assert (t.sell_date, t.sell_price) == ("2024-01-04", 13)
    # 賣出：11791 - 手續費 20 - 證交稅 floor(11791*0.003)=35
    assert t.proceeds == 11791 - 20 - 35
    assert r.final_equity == 10000 - t.cost + t.proceeds
    assert r.win_rate_pct == 100
    assert r.buy_hold_return_pct == pytest.approx(40.0)


def test_backtest_whole_lot_only_cannot_afford():
    r = run_backtest(BARS, ScriptedStrategy(), "2884", cash=10000, allow_odd_lot=False)
    assert r.trades == [] and r.final_equity == 10000


def test_backtest_max_drawdown():
    bars = [{"date": "2024-01-0%d" % (i + 1), "open": p, "close": p} for i, p in enumerate([10, 10, 10, 5, 10])]

    class BuyFirst:
        name = "buy"
        def generate(self, symbol, closes, position_qty=0):
            return Signal(symbol, "BUY" if position_qty == 0 else "HOLD")

    r = run_backtest(bars, BuyFirst(), "x", cash=10000, min_fee=0, fee_rate=0)
    assert r.max_drawdown_pct == pytest.approx(50.0)


def test_fees_and_tax():
    assert calc_fee(1000) == 20
    assert calc_fee(100000) == 142
    assert tax_rate_for("0056") == 0.001
    assert tax_rate_for("2330") == 0.003
