"""共用資料結構"""

from dataclasses import dataclass, field, asdict
from datetime import datetime

SHARES_PER_LOT = 1000  # 1 張 = 1000 股


def shares_for_amount(amount, price, allow_odd_lot):
    """用指定金額最多能買幾股。不允許零股時只取整張"""
    if amount <= 0 or price <= 0:
        return 0
    shares = int(amount // price)
    if not allow_odd_lot:
        shares = (shares // SHARES_PER_LOT) * SHARES_PER_LOT
    return shares


def split_lots(quantity):
    """把股數拆成 [整股部分, 零股部分]，例如 2350 -> [2000, 350]（0 的部分會省略）"""
    whole = (quantity // SHARES_PER_LOT) * SHARES_PER_LOT
    return [q for q in (whole, quantity - whole) if q > 0]


@dataclass
class Signal:
    symbol: str
    action: str        # "BUY" / "SELL" / "HOLD"
    reason: str = ""


@dataclass
class OrderRequest:
    symbol: str
    action: str        # "BUY" / "SELL"
    quantity: int      # 股數：整股是 1000 的倍數，零股是 1~999
    price: float       # 限價
    reason: str = ""

    @property
    def is_odd_lot(self):
        return self.quantity < SHARES_PER_LOT

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
