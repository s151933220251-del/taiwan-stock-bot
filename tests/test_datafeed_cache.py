import pytest

from trading_bot import datafeed

HEADER = "date,stock_id,Trading_Volume,Trading_money,open,max,min,close,spread,Trading_turnover\n"


def write_cache(root, symbol, rows, bom=False):
    d = root / "cache" / "TaiwanStockPrice"
    d.mkdir(parents=True, exist_ok=True)
    text = HEADER + "".join(
        "{},{},1000,30000,{},0,0,{},0,10\n".format(date, symbol, o, c) for date, o, c in rows)
    (d / (symbol + ".csv")).write_text(("﻿" if bom else "") + text, encoding="utf-8")
    return [str(root / "cache")]


@pytest.fixture
def api_calls(monkeypatch):
    calls = []

    def fake(dataset, symbol, start, end):
        calls.append((dataset, symbol, start, end))
        return [{"date": "2024-01-05", "stock_id": symbol, "open": 13, "close": 14}]

    monkeypatch.setattr(datafeed, "fetch_finmind_raw", fake)
    return calls


def test_cache_hit_no_api(tmp_path, api_calls):
    dirs = write_cache(tmp_path, "2884", [("2024-01-02", 10, 11), ("2024-01-03", 11, 12)], bom=True)
    bars = datafeed.fetch_daily_bars("2884", "2024-01-02", "2024-01-03", cache_dirs=dirs, log=lambda m: None)
    assert bars == [{"date": "2024-01-02", "open": 10, "close": 11},
                    {"date": "2024-01-03", "open": 11, "close": 12}]
    assert api_calls == []


def test_cache_missing_symbol_uses_api(tmp_path, api_calls):
    dirs = write_cache(tmp_path, "2884", [("2024-01-02", 10, 11)])
    bars = datafeed.fetch_daily_bars("0056", "2024-01-01", "2024-01-10", cache_dirs=dirs, log=lambda m: None)
    assert api_calls == [("TaiwanStockPrice", "0056", "2024-01-01", "2024-01-10")]
    assert [b["date"] for b in bars] == ["2024-01-05"]


def test_cache_fills_only_missing_tail(tmp_path, api_calls):
    dirs = write_cache(tmp_path, "2884", [("2024-01-02", 10, 11), ("2024-01-03", 11, 12)])
    bars = datafeed.fetch_daily_bars("2884", "2024-01-02", "2024-01-10", cache_dirs=dirs, log=lambda m: None)
    assert api_calls == [("TaiwanStockPrice", "2884", "2024-01-04", "2024-01-10")]
    assert [b["date"] for b in bars] == ["2024-01-02", "2024-01-03", "2024-01-05"]


def test_cache_api_failure_falls_back_to_cache(tmp_path, monkeypatch):
    def boom(*a):
        raise RuntimeError("network down")
    monkeypatch.setattr(datafeed, "fetch_finmind_raw", boom)
    dirs = write_cache(tmp_path, "2884", [("2024-01-02", 10, 11)])
    bars = datafeed.fetch_daily_bars("2884", "2024-01-01", "2024-01-10", cache_dirs=dirs, log=lambda m: None)
    assert [b["date"] for b in bars] == ["2024-01-02"]


def test_nested_cache_folder_found(tmp_path, monkeypatch, api_calls):
    nested = tmp_path / "finmind_cache"
    write_cache(nested, "2884", [("2024-01-02", 10, 11)])
    monkeypatch.chdir(tmp_path)
    bars = datafeed.fetch_daily_bars("2884", "2024-01-02", "2024-01-02", log=lambda m: None)
    assert len(bars) == 1 and api_calls == []


def test_rows_to_bars_skips_bad_and_duplicate_rows():
    rows = [{"date": "2024-01-02", "open": "0", "close": "0"},
            {"date": "2024-01-03", "open": "x", "close": "1"},
            {"date": "2024-01-04", "open": "10", "close": "11"},
            {"date": "2024-01-04", "open": "10", "close": "11"}]
    assert datafeed.rows_to_bars(rows) == [{"date": "2024-01-04", "open": 10.0, "close": 11.0}]
