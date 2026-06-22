"""市场数据模型定义"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class KLine:
    """K 线数据"""
    security_id: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float = 0.0
    turnover_rate: float = 0.0


@dataclass
class TickEvent:
    """逐笔事件（合成 tick）"""
    security_id: str
    timestamp: datetime
    event_type: str  # "ORDER_ADD", "ORDER_CANCEL", "TRADE"
    side: str  # "BUY", "SELL"
    price: float
    volume: int
    order_id: int = 0
    trade_id: int = 0


@dataclass
class MarketSnapshot:
    """市场深度快照"""
    security_id: str
    timestamp: datetime
    last_price: float
    bids: list[tuple[float, int]]  # [(price, volume), ...] 10 档买盘
    asks: list[tuple[float, int]]  # [(price, volume), ...] 10 档卖盘
    total_volume: int
    total_amount: float


@dataclass
class DailyKLine:
    """日 K 线数据"""
    security_id: str
    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float = 0.0
    turnover_rate: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
