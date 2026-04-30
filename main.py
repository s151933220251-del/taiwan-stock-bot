"""
台股主力籌碼分析機器人
每日自動抓取三大法人、融資融券資料，產生 HTML 報表並透過 LINE 推播
"""

import os
import requests
from datetime import datetime, timedelta
import time
import json

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
REPO_NAME = os.environ.get("REPO_NAME", "taiwan-stock-bot")
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




def fetch_etf_holdings(fund_id, date):
    """
    抓取主動式 ETF 每日持股明細
    資料來源：集保結算所公開資料
    比較今日與昨日持股，找出變動
    """
    headers = {"User-Agent": "Mozilla/5.0"}

    def get_holdings_by_date(target_date):
        # 集保結算所 ETF 持股 API
        url = "https://openapi.tdcc.com.tw/v1/opendata/2-30"
        params = {"fundId": fund_id, "dataDate": target_date}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data:
                    holdings = {}
                    for item in data:
                        code = item.get("StockCode", "").strip()
                        name = item.get("StockName", "").strip()
                        shares = pint(item.get("HoldingShares", 0))
                        ratio = pflt(item.get("HoldingRatio", 0))
                        if code:
                            holdings[code] = {
                                "name": name,
                                "shares": shares,
                                "ratio": ratio
                            }
                    return holdings
        except Exception as e:
            print(f"  持股API失敗: {e}")
        return {}

    # 計算前一個交易日
    d = datetime.strptime(date, "%Y%m%d")
    prev = d - timedelta(days=1)
    if prev.weekday() == 5:
        prev -= timedelta(days=1)
    elif prev.weekday() == 6:
        prev -= timedelta(days=2)
    prev_date = prev.strftime("%Y%m%d")

    today_holdings = get_holdings_by_date(date)
    prev_holdings = get_holdings_by_date(prev_date)

    print(f"  {fund_id} 今日持股: {len(today_holdings)} 檔, 昨日: {len(prev_holdings)} 檔")

    if not today_holdings:
        return None

    # 分析變動
    added = []      # 新增持股
    removed = []    # 清倉
    increased = []  # 加碼
    decreased = []  # 減碼
    unchanged = []  # 無變動

    all_codes = set(list(today_holdings.keys()) + list(prev_holdings.keys()))

    for code in all_codes:
        today = today_holdings.get(code)
        prev = prev_holdings.get(code)

        if today and not prev:
            added.append({
                "code": code,
                "name": today["name"],
                "shares": today["shares"],
                "ratio": today["ratio"],
                "change": today["shares"]
            })
        elif prev and not today:
            removed.append({
                "code": code,
                "name": prev["name"],
                "shares": 0,
                "ratio": 0,
                "change": -prev["shares"]
            })
        elif today and prev:
            change = today["shares"] - prev["shares"]
            if change > 0:
                increased.append({
                    "code": code,
                    "name": today["name"],
                    "shares": today["shares"],
                    "ratio": today["ratio"],
                    "change": change
                })
            elif change < 0:
                decreased.append({
                    "code": code,
                    "name": today["name"],
                    "shares": today["shares"],
                    "ratio": today["ratio"],
                    "change": change
                })
            else:
                unchanged.append({
                    "code": code,
                    "name": today["name"],
                    "shares": today["shares"],
                    "ratio": today["ratio"],
                    "change": 0
                })

    # 按變動量排序
    added.sort(key=lambda x: x["shares"], reverse=True)
    removed.sort(key=lambda x: abs(x["change"]), reverse=True)
    increased.sort(key=lambda x: x["change"], reverse=True)
    decreased.sort(key=lambda x: x["change"])

    # 前10大持股
    top10 = sorted(today_holdings.items(), key=lambda x: x[1]["ratio"], reverse=True)[:10]

    return {
        "fund_id": fund_id,
        "date": date,
        "total": len(today_holdings),
        "added": added,
        "removed": removed,
        "increased": increased[:5],
        "decreased": decreased[:5],
        "top10": top10,
        "unchanged_count": len(unchanged)
    }

def fmt_n(n):
    if n > 0:
        return "+{:,}".format(n)
    elif n < 0:
        return "{:,}".format(n)
    return "0"


def fmt_color(n):
    if n > 0:
        return "up"
    elif n < 0:
        return "down"
    return "flat"


def get_signal(n):
    if n >= 3000: return ("🔥", "強力買超", "up")
    if n >= 1000: return ("📈", "買超", "up")
    if n >= 0:    return ("➡️", "小幅買超", "flat")
    if n >= -1000: return ("📉", "賣超", "down")
    return ("❄️", "強力賣超", "down")


def build_html_report(date, institutional, margin, prices, market, etf_data=None):
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
        market_html = ""

    # 個股區塊
    stocks_html = ""
    if not institutional:
        stocks_html = '<div class="no-data">⚠️ 今日無交易資料（假日或休市）</div>'
    else:
        for code in WATCH_LIST:
            inst = institutional.get(code)
            if not inst:
                continue
            p = prices.get(code, {})
            close = p.get("close", 0)
            cv = p.get("change_val", 0)
            if cv > 0:
                price_str = '<span class="up">▲{:.2f}</span>'.format(cv)
            elif cv < 0:
                price_str = '<span class="down">▼{:.2f}</span>'.format(abs(cv))
            else:
                price_str = '<span class="flat">─</span>'

            icon, label, cls = get_signal(inst["total_net"])
            mg = margin.get(code, {})

            margin_html = ""
            if mg:
                mt_cls = fmt_color(mg["margin_change"])
                st_cls = fmt_color(mg["short_change"])
                mt_str = ("↑" if mg["margin_change"] > 0 else "↓" if mg["margin_change"] < 0 else "─")
                st_str = ("↑" if mg["short_change"] > 0 else "↓" if mg["short_change"] < 0 else "─")
                margin_html = """
                <div class="chip-row">
                    <span class="chip-label">融資餘額</span>
                    <span class="chip-value">{:,} 張 <span class="{}">{}{}</span></span>
                </div>
                <div class="chip-row">
                    <span class="chip-label">融券餘額</span>
                    <span class="chip-value">{:,} 張 <span class="{}">{}{}</span></span>
                </div>""".format(
                    mg["margin_balance"], mt_cls, mt_str, abs(mg["margin_change"]),
                    mg["short_balance"], st_cls, st_str, abs(mg["short_change"])
                )

            stocks_html += """
            <div class="stock-card">
                <div class="stock-header">
                    <span class="stock-code">{}</span>
                    <span class="stock-name">{}</span>
                    <span class="stock-price">{} {}</span>
                </div>
                <div class="signal-badge {}">
                    {} {}
                </div>
                <div class="chip-grid">
                    <div class="chip-row">
                        <span class="chip-label">外資</span>
                        <span class="chip-value {}">{} 張</span>
                    </div>
                    <div class="chip-row">
                        <span class="chip-label">投信</span>
                        <span class="chip-value {}">{} 張</span>
                    </div>
                    <div class="chip-row">
                        <span class="chip-label">自營商</span>
                        <span class="chip-value {}">{} 張</span>
                    </div>
                    <div class="chip-row total-row">
                        <span class="chip-label">三大法人合計</span>
                        <span class="chip-value {}">{} 張</span>
                    </div>
                    {}
                </div>
            </div>""".format(
                code, inst["name"], close, price_str,
                cls, icon, label,
                fmt_color(inst["foreign_net"]), fmt_n(inst["foreign_net"]),
                fmt_color(inst["investment_trust_net"]), fmt_n(inst["investment_trust_net"]),
                fmt_color(inst["dealer_net"]), fmt_n(inst["dealer_net"]),
                fmt_color(inst["total_net"]), fmt_n(inst["total_net"]),
                margin_html
            )

    # ETF 持股區塊
    etf_section_html = ""
    if etf_data:
        for fund_id, data in etf_data.items():
            if not data:
                continue
            rows = ""

            if data["added"]:
                for s in data["added"]:
                    rows += '<tr class="added"><td>🆕 新增</td><td>{} {}</td><td class="up">+{:,}</td><td>{:.2f}%</td></tr>'.format(
                        s["code"], s["name"], s["shares"], s["ratio"])

            if data["removed"]:
                for s in data["removed"]:
                    rows += '<tr class="removed"><td>❌ 清倉</td><td>{} {}</td><td class="down">{:,}</td><td>0%</td></tr>'.format(
                        s["code"], s["name"], s["change"])

            if data["increased"]:
                for s in data["increased"]:
                    rows += '<tr class="increased"><td>📈 加碼</td><td>{} {}</td><td class="up">+{:,}</td><td>{:.2f}%</td></tr>'.format(
                        s["code"], s["name"], s["change"], s["ratio"])

            if data["decreased"]:
                for s in data["decreased"]:
                    rows += '<tr class="decreased"><td>📉 減碼</td><td>{} {}</td><td class="down">{:,}</td><td>{:.2f}%</td></tr>'.format(
                        s["code"], s["name"], s["change"], s["ratio"])

            top10_rows = ""
            for i, (code, info) in enumerate(data["top10"], 1):
                top10_rows += '<tr><td>{}</td><td>{} {}</td><td>{:,}</td><td>{:.2f}%</td></tr>'.format(
                    i, code, info["name"], info["shares"], info["ratio"])

            no_change_msg = ""
            if not data["added"] and not data["removed"] and not data["increased"] and not data["decreased"]:
                no_change_msg = '<p style="text-align:center;color:#888;padding:12px;">今日無持股變動</p>'

            etf_section_html += """
            <div class="etf-card">
                <div class="etf-header">📋 {} 持股變動日報</div>
                <div class="etf-meta">共 {} 檔持股｜不變動 {} 檔</div>
                {}
                {}
                <div class="etf-top10-title">📊 前十大持股</div>
                <table class="etf-table">
                    <thead><tr><th>排名</th><th>股票</th><th>張數</th><th>佔比</th></tr></thead>
                    <tbody>{}</tbody>
                </table>
            </div>""".format(
                fund_id, data["total"], data["unchanged_count"],
                '<table class="etf-table"><thead><tr><th>操作</th><th>股票</th><th>變動張數</th><th>佔比</th></tr></thead><tbody>{}</tbody></table>'.format(rows) if rows else "",
                no_change_msg,
                top10_rows
            )

    etf_html = etf_section_html

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
  .stock-card {{
    background: white;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  .stock-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }}
  .stock-code {{
    background: #1a1a2e;
    color: white;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
  }}
  .stock-name {{ font-size: 15px; font-weight: 600; flex: 1; }}
  .stock-price {{ font-size: 14px; font-weight: 500; }}
  .signal-badge {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 10px;
  }}
  .signal-badge.up {{ background: #fff0f0; color: #e53e3e; }}
  .signal-badge.down {{ background: #f0fff4; color: #38a169; }}
  .signal-badge.flat {{ background: #f7f7f7; color: #666; }}
  .chip-grid {{ display: flex; flex-direction: column; gap: 6px; }}
  .chip-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    border-bottom: 1px solid #f0f0f0;
  }}
  .chip-row:last-child {{ border-bottom: none; }}
  .total-row {{ border-top: 2px solid #eee; padding-top: 8px; margin-top: 2px; }}
  .chip-label {{ font-size: 13px; color: #888; }}
  .chip-value {{ font-size: 14px; font-weight: 600; }}
  .up {{ color: #e53e3e; }}
  .down {{ color: #38a169; }}
  .flat {{ color: #888; }}
  .no-data {{
    background: white;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    color: #888;
    margin-bottom: 12px;
  }}
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
  {stocks_html}
  {etf_html}
  <div class="footer">⚡ 本報告由台股籌碼機器人自動產生</div>
</body>
</html>""".format(date_fmt=date_fmt, market_html=market_html, stocks_html=stocks_html)

    return html


def build_line_message(date, institutional, margin, prices, market, report_url):
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
            chg_str = "▼{:,.2f} ({:.2f}%)".format(abs(chg), abs(pct))
        else:
            chg_str = "─"
        lines.append("🏦 加權指數：{:,.2f} {}".format(idx, chg_str))
        if vol > 0:
            lines.append("💰 成交值：{:.0f} 億".format(vol / 100000000))
        lines.append("━━━━━━━━━━━━━━━")

    if not institutional:
        lines.append("⚠️ 今日無交易資料（假日或休市）")
    else:
        for code in WATCH_LIST:
            inst = institutional.get(code)
            if not inst:
                continue
            p = prices.get(code, {})
            close = p.get("close", 0)
            cv = p.get("change_val", 0)
            price_str = "▲{:.2f}".format(cv) if cv > 0 else "▼{:.2f}".format(abs(cv)) if cv < 0 else "─"
            icon, label, _ = get_signal(inst["total_net"])
            lines.append("\n【{} {}】{} {}".format(code, inst["name"], icon, label))
            lines.append("收盤：{} ({})".format(close, price_str))
            lines.append("外資 {} ｜投信 {} ｜自營 {}".format(
                fmt_n(inst["foreign_net"]),
                fmt_n(inst["investment_trust_net"]),
                fmt_n(inst["dealer_net"])
            ))
            lines.append("合計：{} 張".format(fmt_n(inst["total_net"])))

    lines.append("\n━━━━━━━━━━━━━━━")
    lines.append("👉 完整報表：" + report_url)
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

    print("📡 抓取 ETF 持股明細...")
    etf_data = {}
    etf_data["00981A"] = fetch_etf_holdings("00981A", date)

    # 產生 HTML 報表
    html = build_html_report(date, institutional, margin, prices, market, etf_data)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ HTML 報表已產生：docs/index.html")

    # GitHub Pages 網址
    report_url = "https://{}.github.io/{}/".format(GITHUB_USERNAME, REPO_NAME)

    # 發送 LINE 訊息
    message = build_line_message(date, institutional, margin, prices, market, report_url)
    print("\n" + "=" * 40)
    print(message)
    print("=" * 40)
    send_line_message(message)


if __name__ == "__main__":
    main()
