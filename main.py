"""
台股主力籌碼分析機器人
每日自動抓取三大法人、融資融券資料，透過 LINE Messaging API 推播通知
"""

import os
import requests
from datetime import datetime, timedelta
import time

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
WATCH_LIST = ["2330", "2317", "2454", "2308", "2382"]


def get_today_date():
    now_utc = datetime.utcnow()
    today = now_utc + timedelta(hours=8)
    print("UTC時間: " + now_utc.strftime('%Y-%m-%d %H:%M'))
    print("台灣時間: " + today.strftime('%Y-%m-%d %H:%M'))
    target = today - timedelta(days=1)
    if target.weekday() == 5:
        target -= timedelta(days=1)
    elif target.weekday() == 6:
        target -= timedelta(days=2)
    print("抓取日期: " + target.strftime('%Y-%m-%d'))
    return target.strftime("%Y%m%d")


def pint(s):
    try:
        return int(str(s).replace(",", "").replace("+", ""))
    except:
        return 0


def pflt(s):
    try:
        return float(str(s).replace(",", "").replace("+", ""))
    except:
        return 0.0


def fetch_institutional_investors(date):
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {"response": "json", "date": date, "selectType": "ALL"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        data = requests.get(url, params=params, headers=headers, timeout=15).json()
        if data.get("stat") != "OK":
            return {}
        result = {}
        for row in data.get("data", []):
            if len(row) < 14:
                continue
            code = row[0].strip()
            if code not in WATCH_LIST:
                continue
            result[code] = {
                "name": row[1].strip(),
                "foreign_net": pint(row[4]),
                "investment_trust_net": pint(row[8]),
                "dealer_net": pint(row[9]),
                "total_net": pint(row[13]),
            }
        print("三大法人抓到 " + str(len(result)) + " 筆")
        return result
    except Exception as e:
        print("三大法人失敗：" + str(e))
        return {}


def fetch_margin_trading(date):
    url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    params = {"response": "json", "date": date, "selectType": "ALL"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        data = requests.get(url, params=params, headers=headers, timeout=15).json()
        if data.get("stat") != "OK":
            return {}
        result = {}
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if len(row) < 10:
                    continue
                code = row[0].strip()
                if code not in WATCH_LIST:
                    continue
                result[code] = {
                    "margin_balance": pint(row[4]),
                    "margin_change": pint(row[3]) - pint(row[2]),
                    "short_balance": pint(row[9]),
                    "short_change": pint(row[8]) - pint(row[7]),
                }
        print("融資券抓到 " + str(len(result)) + " 筆")
        return result
    except Exception as e:
        print("融資券失敗：" + str(e))
        return {}


def fetch_stock_price(date):
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {"response": "json", "date": date, "type": "ALLBUT0999"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        data = requests.get(url, params=params, headers=headers, timeout=15).json()
        result = {}
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if len(row) < 10:
                    continue
                code = row[0].strip()
                if code not in WATCH_LIST:
                    continue
                result[code] = {
                    "close": pflt(row[8]),
                    "change_val": pflt(row[10]) if len(row) > 10 else 0,
                }
        print("股價抓到 " + str(len(result)) + " 筆")
        return result
    except Exception as e:
        print("股價失敗：" + str(e))
        return {}


def fetch_market_summary(date):
    """抓取大盤加權指數與成交值"""
    headers = {"User-Agent": "Mozilla/5.0"}
    result = {}

    try:
        # 抓加權指數歷史（含開高低收），取最近兩筆算漲跌
        # 用當月資料，date 格式 YYYYMMDD，取該月份
        ym = date[:6] + "01"  # 該月第一天
        url1 = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
        params1 = {"response": "json", "date": ym}
        data1 = requests.get(url1, params=params1, headers=headers, timeout=15).json()
        rows1 = data1.get("data", [])
        # 找當天那筆（民國日期格式 115/04/29）
        tw_year = str(int(date[:4]) - 1911)
        target_date_tw = tw_year + "/" + date[4:6] + "/" + date[6:]
        today_row = None
        prev_row = None
        for i, row in enumerate(rows1):
            if row[0] == target_date_tw:
                today_row = row
                if i > 0:
                    prev_row = rows1[i-1]
                break
        if today_row and len(today_row) >= 5:
            close = pflt(today_row[4])   # 收盤
            result["index"] = close
            if prev_row and len(prev_row) >= 5:
                prev_close = pflt(prev_row[4])
                change = close - prev_close
                result["change_val"] = round(change, 2)
                result["change_pct"] = round(change / prev_close * 100, 2) if prev_close else 0
        print("指數結果: index=" + str(result.get("index")) + " change=" + str(result.get("change_val")))
    except Exception as e:
        print("指數抓取失敗: " + str(e))

    try:
        # 抓成交值
        url2 = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        params2 = {"response": "json", "date": date, "type": "MS"}
        data2 = requests.get(url2, params=params2, headers=headers, timeout=15).json()
        for table in data2.get("tables", []):
            fields = table.get("fields", [])
            rows = table.get("data", [])
            if "成交金額(元)" in fields:
                for row in rows:
                    if "統計" in str(row[0]) and len(row) >= 2:
                        result["volume"] = pflt(row[1])
                        break
                if "volume" not in result and rows:
                    result["volume"] = pflt(rows[0][1]) if len(rows[0]) >= 2 else 0
    except Exception as e:
        print("成交值抓取失敗: " + str(e))

    print("大盤結果: " + str(result))
    return result


def fmt_n(n):
    if n > 0:
        return "+{:,}".format(n)
    elif n < 0:
        return "{:,}".format(n)
    return "0"


def get_signal(n):
    if n >= 3000: return "🔥 強力買超"
    if n >= 1000: return "📈 買超"
    if n >= 0: return "➡️ 小幅買超"
    if n >= -1000: return "📉 賣超"
    return "❄️ 強力賣超"


def build_line_message(date, institutional, margin, prices, market):
    date_fmt = "{}/{}/{}".format(date[:4], date[4:6], date[6:])
    lines = ["📊 台股籌碼日報", "📅 " + date_fmt, "━━━━━━━━━━━━━━━"]

    if market.get("index"):
        idx = market["index"]
        chg = market.get("change_val", 0)
        pct = market.get("change_pct", 0)
        vol = market.get("volume", 0)
        if chg > 0:
            chg_str = "▲{:,.2f} (+{:.2f}%)".format(chg, pct)
        elif chg < 0:
            chg_str = "▼{:,.2f} ({:.2f}%)".format(abs(chg), pct)
        else:
            chg_str = "─"
        lines.append("🏦 加權指數：{:,.2f} {}".format(idx, chg_str))
        if vol > 0:
            lines.append("💰 成交值：{:.0f} 億".format(vol / 100000000))
        lines.append("━━━━━━━━━━━━━━━")

    if not institutional:
        lines.append("⚠️ 今日無交易資料（假日或休市）")
        return "\n".join(lines)

    for code in WATCH_LIST:
        inst = institutional.get(code)
        if not inst:
            continue
        p = prices.get(code, {})
        close = p.get("close", 0)
        cv = p.get("change_val", 0)
        price_str = "▲{:.2f}".format(cv) if cv > 0 else "▼{:.2f}".format(abs(cv)) if cv < 0 else "─"

        lines.append("\n【{} {}】".format(code, inst["name"]))
        lines.append("收盤：{} ({})".format(close, price_str))
        lines.append("訊號：" + get_signal(inst["total_net"]))
        lines.append("外資：{} 張".format(fmt_n(inst["foreign_net"])))
        lines.append("投信：{} 張".format(fmt_n(inst["investment_trust_net"])))
        lines.append("自營：{} 張".format(fmt_n(inst["dealer_net"])))
        lines.append("合計：{} 張".format(fmt_n(inst["total_net"])))

        mg = margin.get(code)
        if mg:
            mt = "↑" if mg["margin_change"] > 0 else "↓" if mg["margin_change"] < 0 else "─"
            st = "↑" if mg["short_change"] > 0 else "↓" if mg["short_change"] < 0 else "─"
            lines.append("融資：{:,} 張 {}{}".format(mg["margin_balance"], mt, abs(mg["margin_change"])))
            lines.append("融券：{:,} 張 {}{}".format(mg["short_balance"], st, abs(mg["short_change"])))
        lines.append("─────────────")

    lines.append("\n⚡ 本報告由台股籌碼機器人自動產生")
    return "\n".join(lines)


def send_line_message(message):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ LINE 環境變數未設定")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    try:
        requests.post(url, headers=headers, json=payload, timeout=15).raise_for_status()
        print("✅ LINE 訊息發送成功")
    except Exception as e:
        print("❌ LINE 失敗：" + str(e))


def main():
    print("🚀 台股籌碼機器人啟動中...")
    date = get_today_date()
    print("📅 分析日期：" + date)

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

    message = build_line_message(date, institutional, margin, prices, market)
    print("\n" + "=" * 40)
    print(message)
    print("=" * 40)

    send_line_message(message)


if __name__ == "__main__":
    main()
