"""
FinMind API 測試程式
測試免費方案可以拿到哪些籌碼資料
"""

import os
import requests
from datetime import datetime, timedelta

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")

def test_finmind(dataset, stock_id="2330", days_back=3):
    """測試特定資料集"""
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
        "token": FINMIND_TOKEN
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        status = data.get("status", "unknown")
        records = len(data.get("data", []))
        print(f"  {dataset}: 狀態={status} 筆數={records}")
        if data.get("data") and records > 0:
            print(f"  第一筆: {data['data'][0]}")
        elif data.get("msg"):
            print(f"  訊息: {data['msg']}")
        return data
    except Exception as e:
        print(f"  {dataset} 失敗: {e}")
        return {}

print("=== FinMind API 測試 ===")
print()

print("【基本行情】")
test_finmind("TaiwanStockPrice", "2330")

print()
print("【籌碼面】")
# 主力券商買賣
test_finmind("TaiwanStockPurchaseSell", "2330")
# 三大法人
test_finmind("TaiwanStockInstitutionalInvestorsBuySell", "2330")
# 融資融券
test_finmind("TaiwanStockMarginPurchaseShortSale", "2330")
# 外資持股
test_finmind("TaiwanStockShareholding", "2330")

print()
print("【ETF 相關】")
test_finmind("TaiwanETFStockInfo", "00981A")
test_finmind("TaiwanStockPrice", "00981A")

print()
print("=== 測試完成 ===")
