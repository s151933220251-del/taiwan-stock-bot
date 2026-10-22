"""
交易通知：用 LINE 推播給 LINE_USER_ID（只發給自己，不發給日報訂閱者）
"""

import os

import requests


def notify(message):
    print(message)
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        return
    try:
        requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
            json={"to": user_id, "messages": [{"type": "text", "text": message[:4900]}]},
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        print("LINE 通知失敗：" + str(e))
