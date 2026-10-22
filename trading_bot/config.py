"""
設定讀取
- 敏感資料（身分證、密碼、憑證）一律從環境變數讀取，不寫進檔案
- 策略與風控參數從 JSON 設定檔讀取（預設 trading_config.json）
"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class FubonCredentials:
    personal_id: str = ""
    password: str = ""
    cert_path: str = ""
    cert_password: str = ""
    account_no: str = ""   # 有多個帳號時指定要用哪一個，空白則用第一個

    @classmethod
    def from_env(cls):
        return cls(
            personal_id=os.environ.get("FUBON_ID", ""),
            password=os.environ.get("FUBON_PASSWORD", ""),
            cert_path=os.environ.get("FUBON_CERT_PATH", ""),
            cert_password=os.environ.get("FUBON_CERT_PASSWORD", ""),
            account_no=os.environ.get("FUBON_ACCOUNT_NO", ""),
        )

    def missing(self):
        return [k for k in ("personal_id", "password", "cert_path", "cert_password")
                if not getattr(self, k)]


@dataclass
class StrategyConfig:
    short_window: int = 5
    long_window: int = 20
    lots_per_trade: int = 1          # 每次買進幾張


@dataclass
class RiskConfig:
    max_order_value: float = 100000.0        # 單筆委託金額上限（元）
    max_position_value: float = 200000.0     # 單一個股持有市值上限（元）
    max_daily_orders: int = 10               # 每日最多委託筆數
    max_price_deviation: float = 0.05        # 委託價與參考價最大偏離（5%）
    kill_switch_file: str = "STOP_TRADING"   # 這個檔案存在就停止一切下單


@dataclass
class BotConfig:
    symbols: list = field(default_factory=lambda: ["2330", "2317"])
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    paper_cash: float = 1000000.0
    log_dir: str = "logs"

    @classmethod
    def load(cls, path="trading_config.json"):
        if not os.path.exists(path):
            print("⚠️ 找不到設定檔 " + path + "，使用預設值")
            return cls()
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            symbols=[str(s) for s in raw.get("symbols", ["2330"])],
            strategy=StrategyConfig(**raw.get("strategy", {})),
            risk=RiskConfig(**raw.get("risk", {})),
            paper_cash=float(raw.get("paper_cash", 1000000.0)),
            log_dir=raw.get("log_dir", "logs"),
        )
