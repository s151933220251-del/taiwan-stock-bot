"""
歷史日K資料（FinMind），模擬模式、回測，以及實盤模式在券商行情不可用時都用這個

回測會優先讀本機快取：cache/<資料集>/<股票代號>.csv（欄位與 FinMind API 回傳相同），
快取沒有的股票或缺少的日期才向 API 抓。
"""

import csv
import os
from datetime import datetime, timedelta

import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
PRICE_DATASET = "TaiwanStockPrice"

# Windows 用「全部解壓縮」時常多一層資料夾，兩種位置都找
DEFAULT_CACHE_DIRS = ["cache", os.path.join("finmind_cache", "cache")]


def fetch_finmind_raw(dataset, symbol, start_date, end_date):
    """向 FinMind API 抓原始資料，回傳 list of dict（欄位與 API 相同）"""
    params = {"dataset": dataset, "data_id": symbol, "start_date": start_date, "end_date": end_date}
    token = os.environ.get("FINMIND_TOKEN", "")
    if token:
        params["token"] = token
    r = requests.get(FINMIND_URL, params=params, timeout=30)
    data = r.json()
    if data.get("status") not in (200, None) and not data.get("data"):
        raise RuntimeError("FinMind 回傳錯誤：" + str(data.get("msg")))
    return data.get("data", [])


def find_cache_file(dataset, symbol, cache_dirs=None):
    for d in cache_dirs or DEFAULT_CACHE_DIRS:
        path = os.path.join(d, dataset, str(symbol) + ".csv")
        if os.path.exists(path):
            return path
    return None


def load_cached_rows(dataset, symbol, cache_dirs=None):
    """讀快取 CSV，找不到回傳 None"""
    path = find_cache_file(dataset, symbol, cache_dirs)
    if not path:
        return None
    # utf-8-sig：相容 Excel 存檔時加上的 BOM
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rows_to_bars(rows):
    """FinMind 原始資料 → 由舊到新的日K {"date", "open", "close"}，同一天只留一筆"""
    by_date = {}
    for row in rows:
        try:
            o, c = float(row["open"]), float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        # 停牌日開收盤可能是 0，略過
        if o > 0 and c > 0:
            by_date[str(row["date"])[:10]] = {"date": str(row["date"])[:10], "open": o, "close": c}
    return [by_date[d] for d in sorted(by_date)]


def _day(text, offset):
    return (datetime.strptime(text, "%Y-%m-%d") + timedelta(days=offset)).strftime("%Y-%m-%d")


def fetch_daily_bars(symbol, start_date, end_date=None, cache_dirs=None, log=print):
    """
    優先讀快取，缺的部分才打 API。
    回傳由舊到新的日K list，每筆為 {"date", "open", "close"}；start_date / end_date 格式 YYYY-MM-DD
    """
    end_date = end_date or datetime.today().strftime("%Y-%m-%d")
    cached = load_cached_rows(PRICE_DATASET, symbol, cache_dirs)
    if cached is None:
        log("  {}：快取沒有這檔，從 FinMind API 抓取".format(symbol))
        return [b for b in rows_to_bars(fetch_finmind_raw(PRICE_DATASET, symbol, start_date, end_date))
                if start_date <= b["date"] <= end_date]

    rows = [r for r in cached if start_date <= str(r.get("date", ""))[:10] <= end_date]
    dates = sorted(str(r["date"])[:10] for r in cached if r.get("date"))
    gaps = []
    if not dates:
        gaps.append((start_date, end_date))
    else:
        # 只補頭尾缺少的區間；中間沒資料的日子視為休市
        if start_date < dates[0]:
            gaps.append((start_date, _day(dates[0], -1)))
        if dates[-1] < end_date:
            gaps.append((_day(dates[-1], 1), end_date))

    for gap_start, gap_end in gaps:
        if gap_start > gap_end:
            continue
        try:
            fetched = fetch_finmind_raw(PRICE_DATASET, symbol, gap_start, gap_end)
            log("  {}：快取缺 {} ~ {}，從 API 補了 {} 筆".format(symbol, gap_start, gap_end, len(fetched)))
            rows.extend(fetched)
        except Exception as e:
            log("  {}：快取缺 {} ~ {}，API 補抓失敗，只用快取（{}）".format(symbol, gap_start, gap_end, e))

    if not gaps:
        log("  {}：全部使用快取".format(symbol))
    return [b for b in rows_to_bars(rows) if start_date <= b["date"] <= end_date]


def fetch_daily_bars_finmind(symbol, start_date, end_date=None):
    """直接從 API 抓（不讀快取），回傳由舊到新的日K"""
    end_date = end_date or datetime.today().strftime("%Y-%m-%d")
    return rows_to_bars(fetch_finmind_raw(PRICE_DATASET, symbol, start_date, end_date))


def fetch_daily_closes_finmind(symbol, days=60):
    """回傳由舊到新的收盤價 list"""
    # 抓多一點日曆日，扣掉假日後才夠 days 個交易日
    start = datetime.today() - timedelta(days=int(days * 1.6) + 10)
    bars = fetch_daily_bars_finmind(symbol, start.strftime("%Y-%m-%d"))
    return [b["close"] for b in bars][-days:]
