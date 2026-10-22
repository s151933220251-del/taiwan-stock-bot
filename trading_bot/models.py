"""共用資料結構"""

from dataclasses import dataclass, field, asdict
from datetime import datetime

SHARES_PER_LOT = 1000  # 1 張 = 1000 股


@dataclass
class Signal:
    symbol: str
    action: str        # "BUY" / "SELL" / "HOLD"
    reason: str = ""


@dataclass
class OrderRequest:
    symbol: str
    action: str        # "BUY" / "SELL"
    quantity: int      # 股數（整股必須是 1000 的倍數）
    price: float       # 限價
    reason: str = ""

    @property
    def value(self):
        return self.quantity * self.price


@dataclass
class OrderResult:
    success: bool
    order_no: str = ""
    message: str = ""
    request: OrderRequest = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class Position:
    symbol: str
    quantity: int      # 股數
    avg_price: float = 0.0
