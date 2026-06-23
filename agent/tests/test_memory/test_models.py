"""MemoryRecord 模型测试"""

import pytest
from datetime import datetime

from agent.memory.models import MemoryRecord


class TestMemoryRecord:
    """MemoryRecord 测试"""

    def test_init_default(self):
        """测试默认初始化"""
        record = MemoryRecord()
        assert record.security_id == ""
        assert record.action == "HOLD"
        assert record.price == 0.0
        assert record.volume == 0

    def test_init_with_values(self):
        """测试带值初始化"""
        record = MemoryRecord(
            record_id="test-001",
            security_id="600519",
            trade_date="2026-06-20",
            action="BUY",
            price=1800.0,
            volume=100,
            confidence=0.8,
            reason="技术面看多",
        )

        assert record.record_id == "test-001"
        assert record.security_id == "600519"
        assert record.action == "BUY"
        assert record.price == 1800.0
        assert record.volume == 100

    def test_to_dict(self):
        """测试转换为字典"""
        record = MemoryRecord(
            record_id="test-002",
            security_id="600519",
            action="BUY",
            price=1800.0,
        )

        data = record.to_dict()

        assert data["record_id"] == "test-002"
        assert data["security_id"] == "600519"
        assert data["action"] == "BUY"
        assert data["price"] == 1800.0
        assert "timestamp" in data

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "record_id": "test-003",
            "security_id": "600519",
            "action": "SELL",
            "price": 1900.0,
            "volume": 200,
            "timestamp": "2026-06-20T10:30:00",
        }

        record = MemoryRecord.from_dict(data)

        assert record.record_id == "test-003"
        assert record.security_id == "600519"
        assert record.action == "SELL"
        assert record.price == 1900.0
        assert record.volume == 200
        assert isinstance(record.timestamp, datetime)

    def test_from_dict_with_result(self):
        """测试从字典创建（含结果）"""
        data = {
            "record_id": "test-004",
            "security_id": "600519",
            "action": "BUY",
            "result_pnl": 500.0,
            "result_price": 1850.0,
            "result_timestamp": "2026-06-20T11:30:00",
            "is_success": True,
        }

        record = MemoryRecord.from_dict(data)

        assert record.result_pnl == 500.0
        assert record.result_price == 1850.0
        assert record.is_success is True
        assert isinstance(record.result_timestamp, datetime)

    def test_roundtrip(self):
        """测试序列化/反序列化往返"""
        original = MemoryRecord(
            record_id="test-005",
            security_id="600519",
            trade_date="2026-06-20",
            action="BUY",
            price=1800.0,
            volume=100,
            confidence=0.8,
            reason="技术面看多",
            technical_signal="buy",
            fundamental_valuation="undervalued",
            sentiment_flow="inflow",
            news_sentiment=0.3,
            debate_consensus="偏多",
            debate_confidence=0.7,
            risk_approved=True,
            risk_reason="",
        )

        data = original.to_dict()
        restored = MemoryRecord.from_dict(data)

        assert restored.record_id == original.record_id
        assert restored.security_id == original.security_id
        assert restored.action == original.action
        assert restored.price == original.price
        assert restored.confidence == original.confidence
        assert restored.reason == original.reason
