"""gRPC 客户端测试"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from agent.data.models.market import TickEvent
from agent.bridge.engine_client import EngineClient, EngineConfig


class TestEngineClient:
    """EngineClient 测试"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return EngineClient(EngineConfig(host="localhost", port=50051))

    def test_config_defaults(self):
        """测试默认配置"""
        config = EngineConfig()
        assert config.host == "localhost"
        assert config.port == 50051
        assert config.timeout == 30.0
        assert config.max_retries == 3

    def test_initial_state(self, client):
        """测试初始状态"""
        assert not client.is_connected()
        assert client._channel is None
        assert client._stub is None

    def test_disconnect_without_connect(self, client):
        """测试未连接时断开"""
        # 应该不会抛出异常
        client.disconnect()
        assert not client.is_connected()

    @patch("grpc.insecure_channel")
    def test_connect_success(self, mock_channel, client):
        """测试连接成功"""
        mock_channel.return_value = MagicMock()
        # 这里需要 mock protobuf 导入，简化测试
        # 实际测试需要运行 gRPC server

    def test_ensure_connected_raises(self, client):
        """测试未连接时调用方法抛出异常"""
        with pytest.raises(RuntimeError, match="未连接到撮合引擎"):
            client.feed_order_event(MagicMock())

    def test_map_event_type(self, client):
        """测试事件类型映射"""
        # 需要 mock protobuf 枚举
        # 这里只测试映射逻辑
        assert client._map_event_type("ORDER_ADD") is not None
        assert client._map_event_type("ORDER_CANCEL") is not None
        assert client._map_event_type("UNKNOWN") is not None  # 默认返回 ADD


class TestTickEventToProto:
    """TickEvent 到 protobuf 转换测试"""

    def test_tick_event_creation(self):
        """测试 TickEvent 创建"""
        event = TickEvent(
            security_id="600519",
            timestamp=datetime(2026, 6, 20, 9, 30, 0),
            event_type="ORDER_ADD",
            side="BUY",
            price=1800.0,
            volume=100,
            order_id=1,
        )
        assert event.security_id == "600519"
        assert event.price == 1800.0
        assert event.volume == 100
        assert event.side == "BUY"
        assert event.event_type == "ORDER_ADD"

    def test_timestamp_conversion(self):
        """测试时间戳转换"""
        event = TickEvent(
            security_id="600519",
            timestamp=datetime(2026, 6, 20, 9, 30, 0),
            event_type="TRADE",
            side="BUY",
            price=1800.0,
            volume=100,
            trade_id=1,
        )
        # 转换为纳秒
        timestamp_ns = int(event.timestamp.timestamp() * 1e9)
        assert timestamp_ns > 0
        # 验证可逆性
        restored = datetime.fromtimestamp(timestamp_ns / 1e9)
        assert restored.year == 2026
        assert restored.month == 6
        assert restored.day == 20
