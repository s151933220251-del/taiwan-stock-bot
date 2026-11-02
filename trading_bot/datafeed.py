"""
歷史日K資料（FinMind），模擬模式、回測，以及實盤模式在券商行情不可用時都用這個
"""

import os
from datetime import datetime, timedelta

import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def fetch_daily_bars_finmind(symbol, start_date, end_date=None):
    """
    回傳由舊到新的日K list，每筆為 {"date", "open", "close"}
    start_date / end_date 格式 YYYY-MM-DD
    """
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date or datetime.today().strftime("%Y-%m-%d"),
    }
    token = os.environ.get("FINMIND_TOKEN", "")
    if token:
        params["token"] = token
    r = requests.get(FINMIND_URL, params=params, timeout=30)
    data = r.json()
    if data.get("status") not in (200, None) and not data.get("data"):
        raise RuntimeError("FinMind 回傳錯誤：" + str(data.get("msg")))
    bars = []
    for row in sorted(data.get("data", []), key=lambda x: x["date"]):
        # 停牌日開收盤可能是 0，略過
        if row.get("close") and row.get("open"):
            bars.append({"date": row["date"], "open": float(row["open"]), "close": float(row["close"])})
    return bars


def fetch_daily_closes_finmind(symbol, days=60):
    """回傳由舊到新的收盤價 list"""
    # 抓多一點日曆日，扣掉假日後才夠 days 個交易日
    start = datetime.today() - timedelta(days=int(days * 1.6) + 10)
    bars = fetch_daily_bars_finmind(symbol, start.strftime("%Y-%m-%d"))
    return [b["close"] for b in bars][-days:]
