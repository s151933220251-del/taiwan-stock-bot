"""
歷史日K資料（FinMind），模擬模式與實盤模式在券商行情不可用時都用這個
"""

import os
from datetime import datetime, timedelta

import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def fetch_daily_closes_finmind(symbol, days=60):
    """回傳由舊到新的收盤價 list"""
    end = datetime.today()
    # 抓多一點日曆日，扣掉假日後才夠 days 個交易日
    start = end - timedelta(days=int(days * 1.6) + 10)
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": symbol,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
    }
    token = os.environ.get("FINMIND_TOKEN", "")
    if token:
        params["token"] = token
    r = requests.get(FINMIND_URL, params=params, timeout=15)
    data = r.json()
    rows = sorted(data.get("data", []), key=lambda x: x["date"])
    return [float(row["close"]) for row in rows if row.get("close")][-days:]
