"""
ETF持股日報機器人
每日自動抓取大盤資料與主動式ETF持股明細，產生HTML報表並透過LINE推播
"""

import os
import requests
from datetime import datetime, timedelta
import time

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
REPO_NAME = os.environ.get("REPO_NAME", "taiwan-stock-bot")

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


def pflt(s):
    try:
        return float(str(s).replace(",", "").replace("+", ""))
    except:
        return 0.0



def fetch_etf_finmind(etf_code, date):
    """
    用 FinMind 抓取 ETF 的三大法人和外資持股比例
    """
    FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
    if not FINMIND_TOKEN:
        print("  FINMIND_TOKEN 未設定")
        return {}

    headers = {"User-Agent": "Mozilla/5.0"}
    base_url = "https://api.finmindtrade.com/api/v4/data"
    result = {}

    # 日期格式轉換 YYYYMMDD -> YYYY-MM-DD
    start = date[:4] + "-" + date[4:6] + "-" + date[6:]
    end = start

    # 三大法人
    try:
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": etf_code,
            "start_date": start,
            "end_date": end,
            "token": FINMIND_TOKEN
        }
        r = requests.get(base_url, params=params, headers=headers, timeout=15)
        data = r.json()
        if data.get("status") == 200 and data.get("data"):
            inst = {}
            for row in data["data"]:
                name = row.get("name", "")
                buy = int(row.get("buy", 0))
                sell = int(row.get("sell", 0))
                net = buy - sell
                if "Foreign_Dealer_Self" in name:
                    inst["foreign"] = net
                elif "Investment_Trust" in name:
                    inst["investment_trust"] = net
                elif "Dealer" in name and "Foreign" not in name:
                    inst["dealer"] = net
            if inst:
                result["institutional"] = inst
                print("  " + etf_code + " 三大法人: " + str(inst))
    except Exception as e:
        print("  三大法人失敗: " + str(e))

    # 外資持股比例
    try:
        params2 = {
            "dataset": "TaiwanStockShareholding",
            "data_id": etf_code,
            "start_date": start,
            "end_date": end,
            "token": FINMIND_TOKEN
        }
        r2 = requests.get(base_url, params=params2, headers=headers, timeout=15)
        data2 = r2.json()
        if data2.get("status") == 200 and data2.get("data"):
            row = data2["data"][-1]
            result["foreign_ratio"] = pflt(row.get("ForeignInvestmentSharesRatio", 0))
            print("  " + etf_code + " 外資持股比例: " + str(result["foreign_ratio"]) + "%")
    except Exception as e:
        print("  外資持股失敗: " + str(e))

    return result


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


def fetch_etf_top_holdings(fund_id, date):
    """抓取主動式 ETF 今日與前日前十大持股，計算差異"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cmoney.tw/etf/tw/{}/fundholding".format(fund_id),
    }
    url = "https://www.cmoney.tw/api/cm/MobileService/ashx/GetDtnoData.ashx"
    params = {
        "action": "getdtnodata",
        "DtNo": "59449513",
        "ParamStr": "AssignID={};MTPeriod=0;DTMode=0;DTRange=2;MajorTable=M722;".format(fund_id),
        "FilterNo": "0"
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print("  CMoney持股API 狀態:" + str(r.status_code) + " 長度:" + str(len(r.text)))

        if r.status_code != 200 or len(r.text) < 50:
            return []

        data = r.json()
        title = data.get("Title", [])
        rows = data.get("Data", [])
        print("  資料筆數:" + str(len(rows)))

        if not rows:
            return []

        name_idx = next((i for i, t in enumerate(title) if "名稱" in t), 2)
        ratio_idx = next((i for i, t in enumerate(title) if "權重" in t or "比重" in t), 3)
        code_idx = next((i for i, t in enumerate(title) if "代號" in t), 1)

        # 找所有日期
        all_dates = []
        for row in rows:
            d = str(row[0]).replace("/", "").replace("-", "").strip()
            if d not in all_dates:
                all_dates.append(d)
        all_dates.sort(reverse=True)
        print("  資料中的日期: " + str(all_dates[:3]))

        latest_date = all_dates[0] if all_dates else ""
        second_date = all_dates[1] if len(all_dates) > 1 else ""
        print("  latest_date: " + latest_date + " second_date: " + second_date)

        # 整理今日和前日持股
        today_holdings = {}
        prev_holdings = {}
        for row in rows:
            if len(row) <= max(name_idx, ratio_idx):
                continue
            row_date = str(row[0]).replace("/", "").replace("-", "").strip()
            code = str(row[code_idx]).strip()
            name = str(row[name_idx]).strip()
            try:
                ratio = float(str(row[ratio_idx]).replace(",", ""))
            except:
                continue
            if not name or ratio <= 0 or ratio >= 50:
                continue
            if row_date == latest_date:
                today_holdings[name] = {"code": code, "ratio": ratio}
            elif row_date == second_date:
                prev_holdings[name] = {"code": code, "ratio": ratio}

        print("  today_holdings: " + str(len(today_holdings)) + " prev_holdings: " + str(len(prev_holdings)))

        # 取前十大（按今日比重排序）
        top10 = sorted(today_holdings.items(), key=lambda x: x[1]["ratio"], reverse=True)[:10]

        holdings = []
        for i, (name, info) in enumerate(top10):
            today_ratio = info["ratio"]
            prev_ratio = prev_holdings.get(name, {}).get("ratio", None)
            if prev_ratio is not None:
                diff = round(today_ratio - prev_ratio, 2)
            else:
                diff = None
            holdings.append({
                "rank": i + 1,
                "code": info["code"],
                "name": name,
                "ratio": today_ratio,
                "prev_ratio": prev_ratio,
                "diff": diff
            })

        print("  成功抓到 " + str(len(holdings)) + " 筆持股（含前日比較）")
        return holdings

    except Exception as e:
        print("  CMoney持股API失敗:" + str(e))
    return []


def build_html_report(date, market, etf_holdings=None):
    date_fmt = "{}/{}/{}".format(date[:4], date[4:6], date[6:])

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

    etf_html = ""
    if etf_holdings:
        for code, name, link in ACTIVE_ETF_LIST:
            info = etf_holdings.get(code)
            if info and info.get("holdings"):
                rows = ""
                for h in info["holdings"]:
                    diff = h.get("diff")
                    if diff is None:
                        diff_str = '<span class="badge-new">NEW</span>'
                    elif diff > 0:
                        diff_str = '<span class="badge-up">▲{:.2f}%</span>'.format(diff)
                    elif diff < 0:
                        diff_str = '<span class="badge-down">▼{:.2f}%</span>'.format(abs(diff))
                    else:
                        diff_str = '<span class="badge-flat">─</span>'
                    rows += '<tr><td class="rank">{}</td><td class="sname">{}</td><td class="ratio">{:.2f}%</td><td class="diff">{}</td></tr>'.format(
                        h["rank"], h["name"], h["ratio"], diff_str)
                etf_html += """
                <div class="etf-card">
                    <div class="etf-header">📋 {} {}</div>
                    <table class="etf-table">
                        <thead><tr><th>#</th><th>股票</th><th>佔比</th><th>較前日</th></tr></thead>
                        <tbody>{}</tbody>
                    </table>
                    <a href="{}" target="_blank" class="etf-link-btn">查看完整持股明細</a>
                </div>""".format(code, name, rows, link)
            else:
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
<title>ETF持股日報</title>
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
  .etf-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin-bottom: 12px;
  }}
  .etf-table th {{
    background: #f0f0f0;
    padding: 7px 8px;
    text-align: left;
    font-weight: 600;
    color: #555;
    border-bottom: 2px solid #ddd;
    font-size: 12px;
  }}
  .etf-table td {{
    padding: 8px 8px;
    border-bottom: 1px solid #f0f0f0;
    vertical-align: middle;
  }}
  .etf-table td.rank {{
    color: #999;
    font-size: 12px;
    width: 24px;
    text-align: center;
  }}
  .etf-table td.sname {{
    font-weight: 500;
    color: #1a1a2e;
  }}
  .etf-table td.ratio {{
    text-align: right;
    font-weight: 600;
    color: #333;
    white-space: nowrap;
  }}
  .etf-table td.diff {{
    text-align: right;
    white-space: nowrap;
    width: 70px;
  }}
  .badge-up {{
    background: #fff0f0;
    color: #e53e3e;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
  }}
  .badge-down {{
    background: #f0fff4;
    color: #38a169;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
  }}
  .badge-flat {{
    color: #bbb;
    font-size: 12px;
  }}
  .badge-new {{
    background: #EEF2FF;
    color: #5A67D8;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }}
  .etf-link-btn {{
    display: block;
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    color: white;
    text-align: center;
    padding: 10px;
    border-radius: 8px;
    text-decoration: none;
    font-size: 14px;
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
    <h1>📊 ETF持股日報</h1>
    <div class="date">📅 {date_fmt}</div>
  </div>
  {market_html}
  {etf_html}
  <div class="footer">⚡ ETF持股日報機器人自動產生</div>
</body>
</html>""".format(date_fmt=date_fmt, market_html=market_html, etf_html=etf_html)

    return html


def build_line_message(date, market, report_url, etf_holdings=None):
    date_fmt = "{}/{}/{}".format(date[:4], date[4:6], date[6:])
    lines = [
        "📊 ETF持股日報",
        "📅 " + date_fmt,
        "📊 完整報表：" + report_url,
        "━━━━━━━━━━━━━━━",
    ]

    if market.get("index"):
        idx = market["index"]
        chg = market.get("change_val", 0)
        pct = market.get("change_pct", 0)
        vol = market.get("volume", 0)
        if chg > 0:
            chg_str = "▲{:,.2f} (+{:.2f}%)".format(chg, pct)
        elif chg < 0:
            chg_str = "▼{:,.2f} ({:.2f}%)".format(abs(chg), abs(pct))
        else:
            chg_str = "─"
        lines.append("🏦 加權指數：{:,.2f} {}".format(idx, chg_str))
        if vol > 0:
            lines.append("💰 成交值：{:.0f} 億".format(vol / 100000000))
    else:
        lines.append("⚠️ 今日無交易資料（假日或休市）")

    if etf_holdings:
        lines.append("\n━━━━━━━━━━━━━━━")
        lines.append("📋 主動式 ETF 前十大持股")
        for code, name, link in ACTIVE_ETF_LIST:
            info = etf_holdings.get(code)
            if not info:
                continue
            lines.append("\n【{} {}】".format(code, name))

            # 三大法人和外資持股
            fm = info.get("finmind", {})
            inst = fm.get("institutional", {})
            foreign_ratio = fm.get("foreign_ratio")
            if inst:
                def fmt_inst(n):
                    if n is None: return "─"
                    return ("+{:,}".format(n) if n > 0 else "{:,}".format(n)) + "張"
                lines.append("外資 {} ｜投信 {} ｜自營 {}".format(
                    fmt_inst(inst.get("foreign")),
                    fmt_inst(inst.get("investment_trust")),
                    fmt_inst(inst.get("dealer"))
                ))
            if foreign_ratio is not None:
                lines.append("外資持股比例：{:.2f}%".format(foreign_ratio))

            if info.get("holdings"):
                for h in info["holdings"]:
                    diff = h.get("diff")
                    if diff is None:
                        diff_str = " 🆕"
                    elif diff > 0:
                        diff_str = " ▲{:.2f}%".format(diff)
                    elif diff < 0:
                        diff_str = " ▼{:.2f}%".format(abs(diff))
                    else:
                        diff_str = ""
                    lines.append("{}. {} {:.2f}%{}".format(
                        h["rank"], h["name"], h["ratio"], diff_str))

    return "\n".join(lines)


def get_subscribers():
    """從 GitHub 讀取訂閱者名單"""
    import base64
    headers = {
        "Authorization": "token " + os.environ.get("MY_GITHUB_TOKEN", ""),
        "Accept": "application/vnd.github.v3+json"
    }
    url = "https://api.github.com/repos/{}/{}/contents/subscribers.json".format(
        GITHUB_USERNAME, REPO_NAME)
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode("utf-8")
            import json
            data = json.loads(content)
            return [s["user_id"] for s in data]
    except Exception as e:
        print("讀取訂閱者失敗: " + str(e))
    return []


def send_line_message(message):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ LINE 環境變數未設定")
        return

    # 取得所有訂閱者
    subscribers = get_subscribers()

    # 如果有訂閱者名單就用名單，否則用預設 User ID
    if subscribers:
        user_ids = subscribers
        print("📨 發送給 " + str(len(user_ids)) + " 位訂閱者")
    elif LINE_USER_ID:
        user_ids = [LINE_USER_ID]
        print("📨 發送給預設用戶")
    else:
        print("❌ 沒有訂閱者也沒有預設 User ID")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN}

    for user_id in user_ids:
        payload = {"to": user_id, "messages": [{"type": "text", "text": message}]}
        try:
            requests.post(url, headers=headers, json=payload, timeout=15).raise_for_status()
            print("  ✅ 發送成功: " + user_id[:8] + "...")
        except Exception as e:
            print("  ❌ 發送失敗 " + user_id[:8] + ": " + str(e))


def main():
    print("🚀 ETF持股日報機器人啟動中...")
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
        holdings = fetch_etf_top_holdings(code, date)
        finmind = fetch_etf_finmind(code, date)
        if holdings:
            etf_holdings[code] = {"name": name, "holdings": holdings, "finmind": finmind}
            print("  " + code + " 成功抓到 " + str(len(holdings)) + " 筆")
        else:
            etf_holdings[code] = {"name": name, "holdings": [], "finmind": finmind}
            print("  " + code + " 持股無資料")
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
