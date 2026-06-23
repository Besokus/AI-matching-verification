"""记忆数据模型"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryRecord:
    """决策记录

    记录每次 Agent 决策的完整上下文和结果。
    """

    # 基本信息
    record_id: str = ""
    security_id: str = ""
    trade_date: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    # 决策内容
    action: str = "HOLD"  # "BUY" | "SELL" | "HOLD"
    price: float = 0.0
    volume: int = 0
    confidence: float = 0.0
    reason: str = ""

    # 分析师报告摘要
    technical_signal: str = ""
    fundamental_valuation: str = ""
    sentiment_flow: str = ""
    news_sentiment: float = 0.0

    # 辩论结论
    debate_consensus: str = ""
    debate_confidence: float = 0.0

    # 风控决策
    risk_approved: bool = False
    risk_reason: str = ""

    # 结果（事后填写）
    result_pnl: float = 0.0
    result_price: float = 0.0
    result_timestamp: datetime | None = None

    # 反思（事后生成）
    reflection: str = ""
    is_success: bool | None = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "record_id": self.record_id,
            "security_id": self.security_id,
            "trade_date": self.trade_date,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "price": self.price,
            "volume": self.volume,
            "confidence": self.confidence,
            "reason": self.reason,
            "technical_signal": self.technical_signal,
            "fundamental_valuation": self.fundamental_valuation,
            "sentiment_flow": self.sentiment_flow,
            "news_sentiment": self.news_sentiment,
            "debate_consensus": self.debate_consensus,
            "debate_confidence": self.debate_confidence,
            "risk_approved": self.risk_approved,
            "risk_reason": self.risk_reason,
            "result_pnl": self.result_pnl,
            "result_price": self.result_price,
            "result_timestamp": self.result_timestamp.isoformat() if self.result_timestamp else None,
            "reflection": self.reflection,
            "is_success": self.is_success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        """从字典创建"""
        record = cls()
        for key, value in data.items():
            if hasattr(record, key):
                if key == "timestamp" and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                elif key == "result_timestamp" and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                setattr(record, key, value)
        return record
