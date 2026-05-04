"""
台股主力籌碼分析機器人
每日自動抓取大盤資料，產生 HTML 報表並透過 LINE 推播
"""

import os
import requests
from datetime import datetime, timedelta
import time

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
REPO_NAME = os.environ.get("REPO_NAME", "taiwan-stock-bot")

WATCH_LIST = []  # 不追蹤個股，只看大盤和 ETF

# 主動式 ETF 清單：(代號, 名稱, 持股查詢連結)
ACTIVE_ETF_LIST = [
    ("00981A", "主動統一台股增長", "https://www.cmoney.tw/etf/tw/00981A/fundholding"),
    ("00992A", "主動群益科技創新", "https://www.cmoney.tw/etf/tw/00992A/fundholding"),
    ("00991A", "主動復華未來50",   "https://www.cmoney.tw/etf/tw/00991A/fundholding"),
    ("00980A", "主動野村臺灣優選", "https://www.cmoney.tw/etf/tw/00980A/fundholding"),
]


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
    print("初始抓取日期: " + target.strftime('%Y-%m-%d'))
    return target.strftime("%Y%m%d")


def find_latest_trading_date(start_date):
    headers = {"User-Agent": "Mozilla/5.0"}
    date = start_date
    for i in range(10):
        d = datetime.strptime(date, "%Y%m%d")
        if d.weekday() == 5:
            d -= timedelta(days=1)
        elif d.weekday() == 6:
            d -= timedelta(days=2)
        date = d.strftime("%Y%m%d")
        try:
            url = "https://www.twse.com.tw/rwd/zh/fund/T86"
            params = {"response": "json", "date": date, "selectType": "ALL"}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            if data.get("stat") == "OK" and data.get("data"):
                print("找到有效交易日: " + date + "（往前找了 " + str(i) + " 天）")
                return date
            else:
                print("日期 " + date + " 無資料（可能是假日），往前一天...")
        except Exception as e:
            print("測試日期 " + date + " 失敗: " + str(e))
        d = datetime.strptime(date, "%Y%m%d") - timedelta(days=1)
        date = d.strftime("%Y%m%d")
    return start_date


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



def fetch_etf_top_holdings(fund_id):
    """
    抓取主動式 ETF 每日持股明細
    來源：CMoney API
    """
    import re
    import json
    import urllib.parse

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Referer": "https://www.cmoney.tw/etf/tw/{}/fundholding".format(fund_id),
        "authority": "www.cmoney.tw",
    }

    # CMoney ETF 持股明細 API
    # DtNo=59449513 是持股明細的資料表，M722 是持股明細 Major Table
    param_str = "AssignID%3D{}%3BMTPeriod%3D0%3BDTMode%3D0%3BDTRange%3D1%3BMajorTable%3DM722%3B".format(fund_id)
    url = "https://www.cmoney.tw/api/cm/MobileService/ashx/GetDtnoData.ashx"
    params = {
        "action": "getdtnodata",
        "DtNo": "59449513",
        "ParamStr": "AssignID={};MTPeriod=0;DTMode=0;DTRange=1;MajorTable=M722;".format(fund_id),
        "FilterNo": "0"
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print("  CMoney持股API 狀態:" + str(r.status_code) + " 長度:" + str(len(r.text)))

        if r.status_code == 200 and len(r.text) > 50:
            data = r.json()
            title = data.get("Title", [])
            rows = data.get("Data", [])
            print("  欄位:" + str(title))
            print("  資料筆數:" + str(len(rows)))
            if rows:
                print("  第一筆:" + str(rows[0]))

            if not rows:
                return []

            # 找欄位索引
            # Title: ["日期","標的代號","標的名稱","權重(%)","持有數","單位"]
            name_idx = next((i for i, t in enumerate(title) if "名稱" in t), 2)
            ratio_idx = next((i for i, t in enumerate(title) if "權重" in t or "比重" in t), 3)
            code_idx = next((i for i, t in enumerate(title) if "代號" in t), 1)

            holdings = []
            seen = set()
            for row in rows:
                if len(row) <= max(name_idx, ratio_idx):
                    continue
                code = str(row[code_idx]).strip()
                name = str(row[name_idx]).strip()
                try:
                    ratio = float(str(row[ratio_idx]).replace(",", ""))
                except:
                    continue
                if name and name not in seen and 0 < ratio < 50:
                    seen.add(name)
                    holdings.append({
                        "rank": len(holdings) + 1,
                        "code": code,
                        "name": name,
                        "ratio": ratio
                    })
                if len(holdings) >= 10:
                    break

            if holdings:
                print("  成功抓到 " + str(len(holdings)) + " 筆持股")
                return holdings

    except Exception as e:
        print("  CMoney持股API失敗:" + str(e))

    return []


def fetch_market_summary(date):
    headers = {"User-Agent": "Mozilla/5.0"}
    result = {}
    try:
        ym = date[:6] + "01"
        url1 = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
        params1 = {"response": "json", "date": ym}
        data1 = requests.get(url1, params=params1, headers=headers, timeout=15).json()
        rows1 = data1.get("data", [])
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
            close = pflt(today_row[4])
            result["index"] = close
            if prev_row and len(prev_row) >= 5:
                prev_close = pflt(prev_row[4])
                change = close - prev_close
                result["change_val"] = round(change, 2)
                result["change_pct"] = round(change / prev_close * 100, 2) if prev_close else 0
    except Exception as e:
        print("指數抓取失敗: " + str(e))

    try:
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


def build_html_report(date, market, etf_holdings=None):
    date_fmt = "{}/{}/{}".format(date[:4], date[4:6], date[6:])

    # 大盤區塊
    if market.get("index"):
        idx = market["index"]
        chg = market.get("change_val", 0)
        pct = market.get("change_pct", 0)
        vol = market.get("volume", 0)
        if chg > 0:
            chg_html = '<span class="up">▲{:,.2f} (+{:.2f}%)</span>'.format(chg, pct)
        elif chg < 0:
            chg_html = '<span class="down">▼{:,.2f} ({:.2f}%)</span>'.format(abs(chg), abs(pct))
        else:
            chg_html = '<span class="flat">─</span>'
        vol_html = "{:.0f} 億".format(vol / 100000000) if vol > 0 else "─"
        market_html = """
        <div class="market-card">
            <div class="market-row">
                <span class="market-label">🏦 加權指數</span>
                <span class="market-value">{:,.2f} {}</span>
            </div>
            <div class="market-row">
                <span class="market-label">💰 成交值</span>
                <span class="market-value">{}</span>
            </div>
        </div>""".format(idx, chg_html, vol_html)
    else:
        market_html = '<div class="no-data">⚠️ 今日無交易資料（假日或休市）</div>'

    # ETF 持股區塊
    etf_html = ""
    if etf_holdings:
        for code, name, link in ACTIVE_ETF_LIST:
            info = etf_holdings.get(code)
            if info and info.get("holdings"):
                rows = ""
                for h in info["holdings"]:
                    rows += "<tr><td>{}</td><td>{}</td><td>{:.2f}%</td></tr>".format(
                        h["rank"], h["name"], h["ratio"])
                etf_html += """
                <div class="etf-card">
                    <div class="etf-header">📋 {} {} 前十大持股</div>
                    <table class="etf-table">
                        <thead><tr><th>排名</th><th>股票</th><th>佔比</th></tr></thead>
                        <tbody>{}</tbody>
                    </table>
                    <a href="{}" target="_blank" class="etf-link-btn" style="margin-top:10px;">查看完整持股</a>
                </div>""".format(code, name, rows, link)
            else:
                etf_html += """
                <div class="etf-card">
                    <div class="etf-header">📋 {} {}</div>
                    <a href="{}" target="_blank" class="etf-link-btn">👉 點我查看今日持股明細</a>
                </div>""".format(code, name, link)
    else:
        for code, name, link in ACTIVE_ETF_LIST:
            etf_html += """
            <div class="etf-card">
                <div class="etf-header">📋 {} {}</div>
                <a href="{}" target="_blank" class="etf-link-btn">👉 點我查看今日持股明細</a>
            </div>""".format(code, name, link)

    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>台股籌碼日報 {date_fmt}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f0f4f8;
    color: #1a1a2e;
    padding: 16px;
    max-width: 480px;
    margin: 0 auto;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    color: white;
    padding: 20px;
    border-radius: 16px;
    margin-bottom: 16px;
    text-align: center;
  }}
  .header h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .header .date {{ font-size: 14px; opacity: 0.7; }}
  .market-card {{
    background: white;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  .market-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
  }}
  .market-label {{ font-size: 14px; color: #666; }}
  .market-value {{ font-size: 16px; font-weight: 600; }}
  .etf-card {{
    background: white;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  .etf-header {{
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 12px;
    color: #1a1a2e;
  }}
  .etf-link-btn {{
    display: block;
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    color: white;
    text-align: center;
    padding: 12px;
    border-radius: 10px;
    text-decoration: none;
    font-size: 15px;
    font-weight: 500;
  }}
  .no-data {{
    background: white;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    color: #888;
    margin-bottom: 12px;
  }}
  .up {{ color: #e53e3e; }}
  .down {{ color: #38a169; }}
  .flat {{ color: #888; }}
  .footer {{
    text-align: center;
    font-size: 12px;
    color: #aaa;
    padding: 12px 0;
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>📊 台股籌碼日報</h1>
    <div class="date">📅 {date_fmt}</div>
  </div>
  {market_html}
  {etf_html}
  <div class="footer">⚡ 本報告由台股籌碼機器人自動產生</div>
</body>
</html>""".format(date_fmt=date_fmt, market_html=market_html, etf_html=etf_html)

    return html


def build_line_message(date, market, report_url, etf_holdings=None):
    date_fmt = "{}/{}/{}".format(date[:4], date[4:6], date[6:])
    lines = ["\U0001f4ca \u53f0\u80a1\u7c4c\u78bc\u65e5\u5831", "\U0001f4c5 " + date_fmt, "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]

    if market.get("index"):
        idx = market["index"]
        chg = market.get("change_val", 0)
        pct = market.get("change_pct", 0)
        vol = market.get("volume", 0)
        if chg > 0:
            chg_str = "\u25b2{:,.2f} (+{:.2f}%)".format(chg, pct)
        elif chg < 0:
            chg_str = "\u25bc{:,.2f} ({:.2f}%)".format(abs(chg), abs(pct))
        else:
            chg_str = "\u2500"
        lines.append("\U0001f3e6 \u52a0\u6b0a\u6307\u6578\uff1a{:,.2f} {}".format(idx, chg_str))
        if vol > 0:
            lines.append("\U0001f4b0 \u6210\u4ea4\u5024\uff1a{:.0f} \u5104".format(vol / 100000000))
    else:
        lines.append("\u26a0\ufe0f \u4eca\u65e5\u7121\u4ea4\u6613\u8cc7\u6599\uff08\u5047\u65e5\u6216\u4f11\u5e02\uff09")

    if etf_holdings:
        lines.append("\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
        lines.append("\U0001f4cb \u4e3b\u52d5\u5f0f ETF \u524d\u5341\u5927\u6301\u80a1")
        for code, name, link in ACTIVE_ETF_LIST:
            info = etf_holdings.get(code)
            if info and info.get("holdings"):
                lines.append("\n\u3010{} {}\u3011".format(code, name))
                for h in info["holdings"]:
                    lines.append("{}. {} {:.2f}%".format(h["rank"], h["name"], h["ratio"]))

    lines.append("\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
    lines.append("\U0001f4ca \u5b8c\u6574\u5831\u8868\uff1a" + report_url)
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
    print("📅 初始日期：" + date)

    print("🔍 尋找最近有效交易日...")
    date = find_latest_trading_date(date)
    print("📅 分析日期：" + date)

    print("📡 抓取大盤資料...")
    market = fetch_market_summary(date)

    print("📡 抓取 ETF 持股明細...")
    etf_holdings = {}
    for code, name, link in ACTIVE_ETF_LIST:
        print("  抓取 " + code + "...")
        holdings = fetch_etf_top_holdings(code)
        if holdings:
            etf_holdings[code] = {"name": name, "holdings": holdings}
            print("  " + code + " 成功抓到 " + str(len(holdings)) + " 筆")
        else:
            print("  " + code + " 無資料")
        time.sleep(1)

    html = build_html_report(date, market, etf_holdings)
    os.makedirs("docs", exist_ok=True)
    if market.get("index"):
        with open("docs/index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("✅ HTML 報表已產生：docs/index.html")
    else:
        print("⚠️ 今日休市，保留舊報表不覆蓋")

    report_url = "https://{}.github.io/{}/".format(GITHUB_USERNAME, REPO_NAME)
    message = build_line_message(date, market, report_url, etf_holdings)
    print("\n" + "=" * 40)
    print(message)
    print("=" * 40)
    send_line_message(message)


if __name__ == "__main__":
    main()
