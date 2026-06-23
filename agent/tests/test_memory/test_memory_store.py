"""MemoryStore 测试"""

import pytest
import tempfile
from pathlib import Path

from agent.memory.models import MemoryRecord
from agent.memory.memory_store import MemoryStore


class TestMemoryStore:
    """MemoryStore 测试"""

    def setup_method(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_memory.db")
        self.store = MemoryStore(db_path=self.db_path)

    def test_init(self):
        """测试初始化"""
        assert self.store.db_path.exists()

    def test_record_decision(self):
        """测试记录决策"""
        record = MemoryRecord(
            security_id="600519",
            trade_date="2026-06-20",
            action="BUY",
            price=1800.0,
            volume=100,
            confidence=0.8,
            reason="技术面看多",
            technical_signal="buy",
            fundamental_valuation="undervalued",
        )

        record_id = self.store.record_decision(record)
        assert record_id is not None
        assert len(record_id) > 0

    def test_record_decision_with_id(self):
        """测试带 ID 记录决策"""
        record = MemoryRecord(
            record_id="test-001",
            security_id="600519",
            action="BUY",
        )

        record_id = self.store.record_decision(record)
        assert record_id == "test-001"

    def test_update_result(self):
        """测试更新结果"""
        record = MemoryRecord(
            record_id="test-002",
            security_id="600519",
            action="BUY",
            price=1800.0,
            volume=100,
        )
        self.store.record_decision(record)

        self.store.update_result("test-002", result_pnl=500.0, result_price=1850.0)

        records = self.store.query_history(security_id="600519")
        assert len(records) == 1
        assert records[0].result_pnl == 500.0
        assert records[0].result_price == 1850.0
        assert records[0].is_success is True

    def test_update_result_loss(self):
        """测试更新亏损结果"""
        record = MemoryRecord(
            record_id="test-003",
            security_id="600519",
            action="BUY",
        )
        self.store.record_decision(record)

        self.store.update_result("test-003", result_pnl=-300.0, result_price=1770.0)

        records = self.store.query_history(security_id="600519")
        assert records[0].is_success is False

    def test_update_reflection(self):
        """测试更新反思"""
        record = MemoryRecord(
            record_id="test-004",
            security_id="600519",
            action="BUY",
        )
        self.store.record_decision(record)

        self.store.update_reflection("test-004", "反思内容")

        records = self.store.query_history(security_id="600519")
        assert records[0].reflection == "反思内容"

    def test_query_history_by_security(self):
        """测试按股票查询"""
        # 记录多条决策
        for i in range(5):
            record = MemoryRecord(
                security_id="600519",
                action="BUY" if i % 2 == 0 else "SELL",
            )
            self.store.record_decision(record)

        # 查询
        records = self.store.query_history(security_id="600519")
        assert len(records) == 5

    def test_query_history_by_action(self):
        """测试按操作查询"""
        record1 = MemoryRecord(security_id="600519", action="BUY")
        record2 = MemoryRecord(security_id="600519", action="SELL")
        record3 = MemoryRecord(security_id="600519", action="BUY")

        self.store.record_decision(record1)
        self.store.record_decision(record2)
        self.store.record_decision(record3)

        records = self.store.query_history(security_id="600519", action="BUY")
        assert len(records) == 2

    def test_query_history_by_success(self):
        """测试按成功查询"""
        record1 = MemoryRecord(record_id="s1", security_id="600519", action="BUY")
        record2 = MemoryRecord(record_id="s2", security_id="600519", action="BUY")

        self.store.record_decision(record1)
        self.store.record_decision(record2)

        self.store.update_result("s1", result_pnl=100, result_price=1800, is_success=True)
        self.store.update_result("s2", result_pnl=-50, result_price=1750, is_success=False)

        records = self.store.query_history(security_id="600519", is_success=True)
        assert len(records) == 1
        assert records[0].record_id == "s1"

    def test_query_history_limit(self):
        """测试查询限制"""
        for i in range(10):
            record = MemoryRecord(security_id="600519", action="BUY")
            self.store.record_decision(record)

        records = self.store.query_history(security_id="600519", limit=5)
        assert len(records) == 5

    def test_get_statistics(self):
        """测试获取统计"""
        # 记录并更新结果
        for i in range(5):
            record = MemoryRecord(
                record_id=f"stat-{i}",
                security_id="600519",
                action="BUY",
            )
            self.store.record_decision(record)

        # 3 笔盈利，2 笔亏损
        self.store.update_result("stat-0", 100, 1800, True)
        self.store.update_result("stat-1", 200, 1900, True)
        self.store.update_result("stat-2", 150, 1850, True)
        self.store.update_result("stat-3", -50, 1750, False)
        self.store.update_result("stat-4", -80, 1720, False)

        stats = self.store.get_statistics(security_id="600519")

        assert stats["total_trades"] == 5
        assert stats["win_count"] == 3
        assert stats["loss_count"] == 2
        assert stats["win_rate"] == 60.0
        assert stats["total_pnl"] == 320.0
        assert stats["max_win"] == 200.0
        assert stats["max_loss"] == -80.0

    def test_get_statistics_empty(self):
        """测试空统计"""
        stats = self.store.get_statistics(security_id="600519")
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0
