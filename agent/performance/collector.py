"""交易记录收集器

从撮合引擎收集 Agent 成交记录。
"""

from datetime import datetime

from .calculator import TradeRecord
from ..bridge.engine_client import EngineClient


class TradeCollector:
    """交易记录收集器"""

    def __init__(self, engine_client: EngineClient):
        self.engine_client = engine_client
        self.trades: list[TradeRecord] = []

    def collect(self, security_id: str = "", agent_id: str = "") -> list[TradeRecord]:
        """从引擎收集交易记录

        Args:
            security_id: 股票代码（可选）
            agent_id: Agent ID（可选）

        Returns:
            交易记录列表
        """
        raw_trades = self.engine_client.get_agent_trades(
            security_id=security_id,
            agent_id=agent_id,
        )

        trades = []
        for t in raw_trades:
            trades.append(TradeRecord(
                trade_id=t.get("trade_id", 0),
                security_id=t.get("security_id", ""),
                price=t.get("price", 0.0),
                volume=t.get("volume", 0),
                side=t.get("side", "BUY"),
                timestamp=datetime.fromtimestamp(t.get("timestamp", 0)),
                agent_id=t.get("agent_id", ""),
                commission=t.get("commission", 0.0),
            ))

        self.trades.extend(trades)
        return trades

    def add_trade(self, trade: TradeRecord):
        """手动添加交易记录（用于测试）"""
        self.trades.append(trade)

    def get_trades(self) -> list[TradeRecord]:
        """获取所有交易记录"""
        return self.trades.copy()

    def clear(self):
        """清空交易记录"""
        self.trades.clear()
