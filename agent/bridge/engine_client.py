"""撮合引擎 gRPC 客户端封装

提供 Python 侧的撮合引擎访问接口，隐藏 gRPC 细节。
"""

import time
from dataclasses import dataclass
from typing import Optional

import grpc

from ..data.models.market import MarketSnapshot, TickEvent


@dataclass
class EngineConfig:
    """引擎连接配置"""
    host: str = "localhost"
    port: int = 50051
    timeout: float = 30.0  # 默认超时 30 秒
    max_retries: int = 3


class EngineClient:
    """撮合引擎 gRPC 客户端

    使用示例:
        client = EngineClient(host="localhost", port=50051)
        client.connect()

        # 喂入历史事件
        client.feed_order_event(order_event)

        # 获取市场快照
        snapshot = client.get_snapshot("600519")

        # 提交 Agent 订单
        result = client.submit_agent_order(
            security_id="600519",
            price=1800.0,
            volume=100,
            side="BUY",
            agent_id="trader_01",
        )

        client.disconnect()
    """

    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()
        self._channel: Optional[grpc.Channel] = None
        self._stub = None
        self._connected = False

    def connect(self) -> bool:
        """连接到撮合引擎 gRPC server

        Returns:
            是否连接成功
        """
        try:
            # 延迟导入（proto 文件需要先编译）
            from .proto import matching_engine_pb2_grpc

            address = f"{self.config.host}:{self.config.port}"
            self._channel = grpc.insecure_channel(address)
            self._stub = matching_engine_pb2_grpc.MatchingEngineServiceStub(self._channel)

            # 测试连接
            self._channel.channel_ready()
            self._connected = True
            return True
        except grpc.RpcError as e:
            print(f"[EngineClient] 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None
            self._connected = False

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected

    def feed_order_event(self, event: TickEvent) -> bool:
        """喂入订单事件（历史回放）

        Args:
            event: 订单事件

        Returns:
            是否成功
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        # 将 TickEvent 转换为 protobuf OrderEvent
        order_event = matching_engine_pb2.OrderEvent(
            security_id=event.security_id,
            order_id=event.order_id,
            price=event.price,
            volume=event.volume,
            side=matching_engine_pb2.ORDER_SIDE_BUY if event.side == "BUY" else matching_engine_pb2.ORDER_SIDE_SELL,
            order_type=matching_engine_pb2.ORDER_TYPE_LIMIT,
            timestamp_ns=int(event.timestamp.timestamp() * 1e9),
            event_kind=self._map_event_type(event.event_type),
        )

        try:
            result = self._stub.FeedOrderEvent(order_event, timeout=self.config.timeout)
            return result.success
        except grpc.RpcError as e:
            print(f"[EngineClient] FeedOrderEvent 失败: {e}")
            return False

    def feed_trade_event(self, event: TickEvent) -> bool:
        """喂入成交事件（历史回放）

        Args:
            event: 成交事件

        Returns:
            是否成功
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        trade_event = matching_engine_pb2.TradeEvent(
            security_id=event.security_id,
            trade_id=event.trade_id,
            price=event.price,
            volume=event.volume,
            buy_order_id=event.order_id,
            sell_order_id=0,
            timestamp_ns=int(event.timestamp.timestamp() * 1e9),
        )

        try:
            result = self._stub.FeedTradeEvent(trade_event, timeout=self.config.timeout)
            return result.success
        except grpc.RpcError as e:
            print(f"[EngineClient] FeedTradeEvent 失败: {e}")
            return False

    def submit_agent_order(
        self,
        security_id: str,
        price: float,
        volume: int,
        side: str,
        agent_id: str,
        reason: str = "",
    ) -> dict:
        """提交 Agent 订单

        Args:
            security_id: 股票代码
            price: 价格
            volume: 数量
            side: 方向 ("BUY" / "SELL")
            agent_id: Agent ID
            reason: 下单理由

        Returns:
            {"success": bool, "order_id": int, "status": str}
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        agent_order = matching_engine_pb2.AgentOrder(
            security_id=security_id,
            price=price,
            volume=volume,
            side=matching_engine_pb2.ORDER_SIDE_BUY if side == "BUY" else matching_engine_pb2.ORDER_SIDE_SELL,
            order_type=matching_engine_pb2.ORDER_TYPE_LIMIT,
            agent_id=agent_id,
            reason=reason,
        )

        try:
            result = self._stub.SubmitAgentOrder(agent_order, timeout=self.config.timeout)
            return {
                "success": result.success,
                "order_id": result.order_id,
                "status": self._map_order_status(result.status),
                "error": result.error_message if not result.success else None,
            }
        except grpc.RpcError as e:
            print(f"[EngineClient] SubmitAgentOrder 失败: {e}")
            return {"success": False, "order_id": 0, "status": "REJECTED", "error": str(e)}

    def cancel_agent_order(self, security_id: str, order_id: int) -> bool:
        """取消 Agent 订单

        Args:
            security_id: 股票代码
            order_id: 订单 ID

        Returns:
            是否成功
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        cancel_request = matching_engine_pb2.CancelRequest(
            security_id=security_id,
            order_id=order_id,
        )

        try:
            result = self._stub.CancelAgentOrder(cancel_request, timeout=self.config.timeout)
            return result.success
        except grpc.RpcError as e:
            print(f"[EngineClient] CancelAgentOrder 失败: {e}")
            return False

    def get_snapshot(self, security_id: str) -> Optional[MarketSnapshot]:
        """获取市场快照

        Args:
            security_id: 股票代码

        Returns:
            MarketSnapshot 或 None
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        request = matching_engine_pb2.SnapshotRequest(security_id=security_id)

        try:
            result = self._stub.GetMarketSnapshot(request, timeout=self.config.timeout)

            # 转换为 MarketSnapshot
            bids = [(level.price, level.volume) for level in result.bids]
            asks = [(level.price, level.volume) for level in result.asks]

            from datetime import datetime
            return MarketSnapshot(
                security_id=result.security_id,
                timestamp=datetime.fromtimestamp(result.timestamp_ns / 1e9),
                last_price=result.last_price,
                bids=bids,
                asks=asks,
                total_volume=result.total_volume,
                total_amount=result.total_amount,
            )
        except grpc.RpcError as e:
            print(f"[EngineClient] GetMarketSnapshot 失败: {e}")
            return None

    def get_agent_trades(
        self,
        security_id: str = "",
        agent_id: str = "",
    ) -> list[dict]:
        """获取 Agent 成交记录

        Args:
            security_id: 股票代码（可选）
            agent_id: Agent ID（可选）

        Returns:
            成交记录列表
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        request = matching_engine_pb2.TradeQuery(
            security_id=security_id,
            agent_id=agent_id,
        )

        try:
            result = self._stub.GetAgentTrades(request, timeout=self.config.timeout)
            trades = []
            for trade in result.trades:
                trades.append({
                    "trade_id": trade.trade_id,
                    "security_id": trade.security_id,
                    "price": trade.price,
                    "volume": trade.volume,
                    "side": "BUY" if trade.side == 0 else "SELL",
                    "timestamp": trade.timestamp_ns / 1e9,
                    "agent_id": trade.agent_id,
                    "commission": trade.commission,
                })
            return trades
        except grpc.RpcError as e:
            print(f"[EngineClient] GetAgentTrades 失败: {e}")
            return []

    def wait_for_drain(self, security_id: str = "", timeout_ms: int = 5000) -> bool:
        """等待引擎排空

        Args:
            security_id: 股票代码（可选）
            timeout_ms: 超时毫秒数

        Returns:
            是否成功排空
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        request = matching_engine_pb2.DrainRequest(
            security_id=security_id,
            timeout_ms=timeout_ms,
        )

        try:
            result = self._stub.WaitForDrain(request, timeout=timeout_ms / 1000 + 5)
            return result.success
        except grpc.RpcError as e:
            print(f"[EngineClient] WaitForDrain 失败: {e}")
            return False

    def get_engine_status(self, detailed: bool = False) -> dict:
        """获取引擎状态

        Args:
            detailed: 是否获取详细状态

        Returns:
            状态字典
        """
        self._ensure_connected()

        from .proto import matching_engine_pb2

        request = matching_engine_pb2.StatusRequest(detailed=detailed)

        try:
            result = self._stub.GetEngineStatus(request, timeout=self.config.timeout)
            return {
                "state": self._map_engine_state(result.state),
                "total_orders": result.total_orders,
                "total_trades": result.total_trades,
                "pending_orders": result.pending_orders,
                "uptime": result.uptime,
            }
        except grpc.RpcError as e:
            print(f"[EngineClient] GetEngineStatus 失败: {e}")
            return {}

    def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            raise RuntimeError("未连接到撮合引擎，请先调用 connect()")

    def _map_event_type(self, event_type: str):
        """映射事件类型到 protobuf 枚举"""
        from .proto import matching_engine_pb2
        mapping = {
            "ORDER_ADD": matching_engine_pb2.ORDER_EVENT_ADD,
            "ORDER_CANCEL": matching_engine_pb2.ORDER_EVENT_CANCEL,
            "ORDER_MODIFY": matching_engine_pb2.ORDER_EVENT_MODIFY,
        }
        return mapping.get(event_type, matching_engine_pb2.ORDER_EVENT_ADD)

    def _map_order_status(self, status) -> str:
        """映射 protobuf 枚举到字符串"""
        from .proto import matching_engine_pb2
        mapping = {
            matching_engine_pb2.ORDER_STATUS_NEW: "NEW",
            matching_engine_pb2.ORDER_STATUS_PARTIAL: "PARTIAL",
            matching_engine_pb2.ORDER_STATUS_FILLED: "FILLED",
            matching_engine_pb2.ORDER_STATUS_CANCELLED: "CANCELLED",
            matching_engine_pb2.ORDER_STATUS_REJECTED: "REJECTED",
        }
        return mapping.get(status, "UNKNOWN")

    def _map_engine_state(self, state) -> str:
        """映射引擎状态"""
        from .proto import matching_engine_pb2
        mapping = {
            matching_engine_pb2.ENGINE_STATE_IDLE: "IDLE",
            matching_engine_pb2.ENGINE_STATE_RUNNING: "RUNNING",
            matching_engine_pb2.ENGINE_STATE_PAUSED: "PAUSED",
            matching_engine_pb2.ENGINE_STATE_STOPPED: "STOPPED",
        }
        return mapping.get(state, "UNKNOWN")
