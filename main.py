"""
台股主力籌碼分析機器人
每日自動抓取三大法人、融資融券資料，透過 LINE Messaging API 推播通知
"""

import os
import requests
import json
from datetime import datetime, timedelta
import time

# ===========================
# 設定區（使用環境變數）
# ===========================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# 你想追蹤的股票代號列表（可自行修改）
WATCH_LIST = ["2330", "2317", "2454", "2308", "2382"]  # 台積電、鴻海、聯發科、台達電、廣達


# ===========================
# 資料抓取函式
# ===========================

def get_today_date():
    """取得前一個交易日日期（台灣時間 UTC+8），格式為 YYYYMMDD"""
    now_utc = datetime.utcnow()
    tw_offset = timedelta(hours=8)
    today = now_utc + tw_offset
    print(f"  UTC時間: {now_utc.strftime('%Y-%m-%d %H:%M')}")
    print(f"  台灣時間: {today.strftime('%Y-%m-%d %H:%M')}")
    target = today - timedelta(days=1)
    if target.weekday() == 5:
        target -= timedelta(days=1)
    elif target.weekday() == 6:
        target -= timedelta(days=2)
    print(f"  抓取日期: {target.strftime('%Y-%m-%d')}")
    return target.strftime("%Y%m%d")


def fetch_institutional_investors(date: str) -> dict:
    """
    抓取三大法人買賣超資料
    資料來源：證交所公開資訊
    """
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {
        "response": "json",
        "date": date,
        "selectType": "ALL"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("stat") != "OK":
            return {}

        result = {}
        fields = data.get("fields", [])
        rows = data.get("data", [])

        # 欄位索引
        # [0]=證券代號, [1]=證券名稱, [2]=外陸資買進, [3]=外陸資賣出, [4]=外陸資買賣超
        # [5]=外資自營商買超, [6]=投信買進, [7]=投信賣出, [8]=投信買賣超
        # [9]=自營商買賣超, [10]=自營商買進, [11]=自營商賣出, [12]=自營商避險
        # [13]=三大法人買賣超

        for row in rows:
            if len(row) < 14:
                continue
            code = row[0].strip()
            if code not in WATCH_LIST:
                continue

            def parse_num(s):
                try:
                    return int(s.replace(",", "").replace("+", ""))
                except:
                    return 0

            result[code] = {
                "name": row[1].strip(),
                "foreign_net": parse_num(row[4]),      # 外資買賣超（張）
                "investment_trust_net": parse_num(row[8]),  # 投信買賣超（張）
                "dealer_net": parse_num(row[9]),        # 自營商買賣超（張）
                "total_net": parse_num(row[13]),        # 三大法人合計（張）
            }

        return result

    except Exception as e:
        print(f"三大法人資料抓取失敗：{e}")
        return {}


def fetch_margin_trading(date: str) -> dict:
    """
    抓取融資融券資料
    資料來源：證交所公開資訊
    """
    url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    params = {
        "response": "json",
        "date": date,
        "selectType": "ALL"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("stat") != "OK":
            return {}

        result = {}
        # 融資資料在第一個表格
        for table_key in ["tables"]:
            tables = data.get(table_key, [])
            if not tables:
                break
            for table in tables:
                for row in table.get("data", []):
                    if len(row) < 12:
                        continue
                    code = row[0].strip()
                    if code not in WATCH_LIST:
                        continue

                    def parse_num(s):
                        try:
                            return int(s.replace(",", ""))
                        except:
                            return 0

                    result[code] = {
                        "margin_balance": parse_num(row[4]),   # 融資餘額（張）
                        "margin_change": parse_num(row[3]) - parse_num(row[2]),  # 融資增減
                        "short_balance": parse_num(row[9]),    # 融券餘額（張）
                        "short_change": parse_num(row[8]) - parse_num(row[7]),   # 融券增減
                    }

        return result

    except Exception as e:
        print(f"融資融券資料抓取失敗：{e}")
        return {}


def fetch_stock_price(date: str) -> dict:
    """
    抓取個股收盤價資料
    """
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {
        "response": "json",
        "date": date,
        "type": "ALLBUT0999"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        result = {}
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if len(row) < 10:
                    continue
                code = row[0].strip()
                if code not in WATCH_LIST:
                    continue

                def parse_num(s):
                    try:
                        return float(s.replace(",", ""))
                    except:
                        return 0.0

                result[code] = {
                    "close": parse_num(row[8]),   # 收盤價
                    "change": row[9].strip(),      # 漲跌
                    "change_val": parse_num(row[10]) if len(row) > 10 else 0,
                }

        return result

    except Exception as e:
        print(f"股價資料抓取失敗：{e}")
        return {}
def fetch_market_summary(date: str) -> dict:
    """
    抓取大盤加權指數與成交值
    資料來源：證交所每日收盤行情
    """
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {"response": "json", "date": date, "type": "MS"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        def parse_num(s):
            try:
                return float(str(s).replace(",", "").replace("+", ""))
            except:
                return 0.0

        result = {}

        for table in data.get("tables", []):
            fields = table.get("fields", [])
            rows = table.get("data", [])

            # table[7]: 大盤指數，fields=['類型','整體市場','股票']
            if "類型" in fields and "整體市場" in fields:
                for row in rows:
                    if len(row) >= 2 and ("加權" in str(row[0]) or "發行量" in str(row[0])):
                        result["index"] = parse_num(row[1])
                    if len(row) >= 2 and "漲跌點數" in str(row[0]):
                        result["change_val"] = parse_num(row[1])
                    if len(row) >= 2 and "漲跌百分比" in str(row[0]):
                        result["change_pct"] = parse_num(row[1])

            # table[6]: 成交統計，fields=['成交統計','成交金額(元)','成交股數(股)']
            if "成交金額(元)" in fields:
                for row in rows:
                    if len(row) >= 2 and "合計" in str(row[0]):
                        result["volume"] = parse_num(row[1])
                        break
                if "volume" not in result and rows:
                    # 取第一筆
                    result["volume"] = parse_num(rows[0][1]) if len(rows[0]) >= 2 else 0

        return result

    except Exception as e:
        print(f"大盤資料抓取失敗：{e}")
        return {}


def fetch_stock_price(date: str) -> dict:
    """
    抓取個股收盤價資料
    """
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {
        "response": "json",
        "date": date,
        "type": "ALLBUT0999"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        result = {}
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if len(row) < 10:
                    continue
                code = row[0].strip()
                if code not in WATCH_LIST:
                    continue

                def parse_num(s):
                    try:
                        return float(s.replace(",", ""))
                    except:
                        return 0.0

                result[code] = {
                    "close": parse_num(row[8]),   # 收盤價
                    "change": row[9].strip(),      # 漲跌
                    "change_val": parse_num(row[10]) if len(row) > 10 else 0,
                }

        return result

    except Exception as e:
        print(f"股價資料抓取失敗：{e}")
        return {}
def fetch_market_summary(date: str) -> dict:
    """
    抓取大盤加權指數與成交值
    資料來源：證交所每日收盤行情
    """
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {
        "response": "json",
        "date": date,
        "type": "MS"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockBot/1.0)"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        def parse_num(s):
            try:
                return float(str(s).replace(",", "").replace("+", ""))
            except:
                return 0.0

        print(f"  大盤API tables數: {len(data.get('tables', []))}")
        result = {}
        for i, table in enumerate(data.get("tables", [])):
            fields = table.get("fields", [])
            rows = table.get("data", [])
            print(f"  table[{i}] fields={fields[:3]}, rows={len(rows)}")
            for row in rows:
                row_str = str(row)
                if "加權" in row_str or "發行量" in row_str:
                    print(f"  找到大盤row: {row[:5]}")
                    if len(row) >= 2:
                        result["index"] = parse_num(row[1])
                    if len(row) >= 3:
                        result["change_val"] = parse_num(row[2])
                    if len(row) >= 4:
                        result["change_pct"] = parse_num(row[3])
                if "成交金額" in row_str or "成交值" in row_str:
                    print(f"  找到成交row: {row[:5]}")
                    if len(row) >= 2:
                        result["volume"] = parse_num(row[1])

        # 改用另一個 API 抓大盤總覽
        url2 = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
        params2 = {"response": "json", "date": date, "selectType": "MS"}
        r2 = requests.get(url2, params=params2, headers=headers, timeout=15)
        d2 = r2.json()
        print(f"  大盤總覽API stat: {d2.get('stat')}, rows: {len(d2.get('data', []))}")
        for row in d2.get("data", []):
            print(f"  row: {row[:4]}")
            break

        return result

    except Exception as e:
        print(f"大盤資料抓取失敗：{e}")
        return {}




# ===========================
# 訊息格式化
# ===========================

def format_number(n: int) -> str:
    """格式化數字，加上正負號和千分位"""
    if n > 0:
        return f"+{n:,}"
    elif n < 0:
        return f"{n:,}"
    else:
        return "0"


def get_signal(total_net: int) -> str:
    """根據三大法人買賣超給出訊號"""
    if total_net >= 3000:
        return "🔥 強力買超"
    elif total_net >= 1000:
        return "📈 買超"
    elif total_net >= 0:
        return "➡️ 小幅買超"
    elif total_net >= -1000:
        return "📉 賣超"
    else:
        return "❄️ 強力賣超"


def build_line_message(date: str, institutional: dict, margin: dict, prices: dict, market: dict) -> str:
    """組合 LINE 推播訊息"""
    date_fmt = f"{date[:4]}/{date[4:6]}/{date[6:]}"
    
    lines = [
        f"📊 台股籌碼日報",
        f"📅 {date_fmt}",
        f"━━━━━━━━━━━━━━━",
    ]

    # 大盤摘要
    if market:
        idx = market.get("index", 0)
        chg = market.get("change_val", 0)
        pct = market.get("change_pct", 0)
        vol = market.get("volume", 0)
        if chg > 0:
            chg_str = f"▲{chg:,.2f} (+{pct:.2f}%)"
        elif chg < 0:
            chg_str = f"▼{abs(chg):,.2f} ({pct:.2f}%)"
        else:
            chg_str = "─"
        lines.append(f"🏦 加權指數：{idx:,.2f} {chg_str}")
        if vol > 0:
            lines.append(f"💰 成交值：{vol/100000000:.0f} 億")
        lines.append(f"━━━━━━━━━━━━━━━")

    if not institutional:
        lines.append("⚠️ 今日無交易資料（假日或休市）")
        return "\n".join(lines)

    for code in WATCH_LIST:
        inst = institutional.get(code)
        if not inst:
            continue

        name = inst["name"]
        price_info = prices.get(code, {})
        close = price_info.get("close", "-")
        change = price_info.get("change", "")
        change_val = price_info.get("change_val", 0)

        # 漲跌符號
        if change_val > 0:
            price_str = f"▲{change_val:.2f}"
        elif change_val < 0:
            price_str = f"▼{abs(change_val):.2f}"
        else:
            price_str = "─"

        signal = get_signal(inst["total_net"])

        lines.append(f"\n【{code} {name}】")
        lines.append(f"收盤：{close} ({price_str})")
        lines.append(f"訊號：{signal}")
        lines.append(f"外資：{format_number(inst['foreign_net'])} 張")
        lines.append(f"投信：{format_number(inst['investment_trust_net'])} 張")
        lines.append(f"自營：{format_number(inst['dealer_net'])} 張")
        lines.append(f"合計：{format_number(inst['total_net'])} 張")

        # 融資融券
        mg = margin.get(code)
        if mg:
            margin_trend = "↑" if mg["margin_change"] > 0 else "↓" if mg["margin_change"] < 0 else "─"
            short_trend = "↑" if mg["short_change"] > 0 else "↓" if mg["short_change"] < 0 else "─"
            lines.append(f"融資：{mg['margin_balance']:,} 張 {margin_trend}{abs(mg['margin_change']):,}")
            lines.append(f"融券：{mg['short_balance']:,} 張 {short_trend}{abs(mg['short_change']):,}")

        lines.append("─────────────")

    lines.append("\n⚡ 本報告由台股籌碼機器人自動產生")

    return "\n".join(lines)


# ===========================
# LINE 推播
# ===========================

def send_line_message(message: str):
    """透過 LINE Messaging API 推播訊息"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ LINE 環境變數未設定")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        print("✅ LINE 訊息發送成功")
        return True
    except Exception as e:
        print(f"❌ LINE 訊息發送失敗：{e}")
        if hasattr(e, 'response') and e.response:
            print(f"   回應：{e.response.text}")
        return False


# ===========================
# 主程式
# ===========================

def main():
    print("🚀 台股籌碼機器人啟動中...")
    date = get_today_date()
    print(f"📅 分析日期：{date}")

    # 抓取資料（加入小延遲避免被擋）
    print("📡 抓取三大法人資料...")
    institutional = fetch_institutional_investors(date)
    time.sleep(2)

    print("📡 抓取融資融券資料...")
    margin = fetch_margin_trading(date)
    time.sleep(2)

    print("📡 抓取股價資料...")
    prices = fetch_stock_price(date)
    time.sleep(2)

    print("📡 抓取大盤資料...")
    market = fetch_market_summary(date)

    # 組合訊息
    message = build_line_message(date, institutional, margin, prices, market)
    print("\n" + "="*40)
    print("📨 準備發送的訊息：")
    print(message)
    print("="*40 + "\n")

    # 發送 LINE 訊息
    send_line_message(message)


if __name__ == "__main__":
    main()
