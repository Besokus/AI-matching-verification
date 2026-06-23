"""ReflectionGenerator 测试"""

import pytest
import tempfile
from pathlib import Path

from agent.memory.models import MemoryRecord
from agent.memory.memory_store import MemoryStore
from agent.memory.reflection import ReflectionGenerator


class TestReflectionGenerator:
    """ReflectionGenerator 测试"""

    def setup_method(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_reflection.db")
        self.store = MemoryStore(db_path=self.db_path)
        self.generator = ReflectionGenerator(self.store)

    def test_init(self):
        """测试初始化"""
        assert self.generator.store is not None
        assert self.generator.llm is None

    def test_generate_reflection_empty(self):
        """测试空记录生成反思"""
        reflection = self.generator.generate_reflection("600519")
        assert "暂无" in reflection

    def test_generate_reflection_with_records(self):
        """测试有记录生成反思"""
        # 添加记录
        for i in range(5):
            record = MemoryRecord(
                record_id=f"ref-{i}",
                security_id="600519",
                action="BUY",
                confidence=0.7,
                technical_signal="buy",
            )
            self.store.record_decision(record)

        # 更新结果
        self.store.update_result("ref-0", 100, 1800, True)
        self.store.update_result("ref-1", 200, 1900, True)
        self.store.update_result("ref-2", 150, 1850, True)
        self.store.update_result("ref-3", -50, 1750, False)
        self.store.update_result("ref-4", -80, 1720, False)

        reflection = self.generator.generate_reflection("600519")

        assert "胜率" in reflection
        assert "总盈亏" in reflection

    def test_generate_reflection_for_decision(self):
        """测试为特定决策生成反思"""
        # 添加历史记录
        for i in range(3):
            record = MemoryRecord(
                record_id=f"dec-{i}",
                security_id="600519",
                action="BUY",
                confidence=0.8,
                technical_signal="buy",
                fundamental_valuation="undervalued",
                sentiment_flow="inflow",
            )
            self.store.record_decision(record)

        # 更新结果
        self.store.update_result("dec-0", 100, 1800, True)
        self.store.update_result("dec-1", 200, 1900, True)
        self.store.update_result("dec-2", -50, 1750, False)

        reflection = self.generator.generate_reflection_for_decision(
            security_id="600519",
            action="BUY",
            technical_signal="buy",
            fundamental_valuation="undervalued",
            sentiment_flow="inflow",
        )

        assert "相似场景" in reflection
        assert "胜率" in reflection

    def test_generate_reflection_for_decision_no_similar(self):
        """测试无相似场景"""
        # 添加不相似的记录
        record = MemoryRecord(
            record_id="no-sim",
            security_id="600519",
            action="SELL",
            technical_signal="sell",
            fundamental_valuation="overvalued",
            sentiment_flow="outflow",
        )
        self.store.record_decision(record)
        self.store.update_result("no-sim", -100, 1700, False)

        reflection = self.generator.generate_reflection_for_decision(
            security_id="600519",
            action="BUY",
            technical_signal="buy",
            fundamental_valuation="undervalued",
            sentiment_flow="inflow",
        )

        # 应返回通用反思
        assert isinstance(reflection, str)
        assert len(reflection) > 0

    def test_identify_patterns_success(self):
        """测试识别成功模式"""
        records = [
            MemoryRecord(technical_signal="buy", action="BUY", confidence=0.8),
            MemoryRecord(technical_signal="buy", action="BUY", confidence=0.7),
            MemoryRecord(technical_signal="buy", action="BUY", confidence=0.9),
        ]

        patterns = self.generator._identify_patterns(records)

        assert len(patterns) > 0
        assert any("buy" in p for p in patterns)

    def test_identify_patterns_empty(self):
        """测试空记录模式识别"""
        patterns = self.generator._identify_patterns([])
        assert patterns == []

    def test_generate_suggestions_low_win_rate(self):
        """测试低胜率建议"""
        stats = {"win_rate": 30.0, "max_win": 100, "max_loss": -200}
        suggestions = self.generator._generate_suggestions(stats, [], [])

        assert len(suggestions) > 0
        assert any("胜率" in s for s in suggestions)

    def test_generate_suggestions_high_win_rate(self):
        """测试高胜率建议"""
        stats = {"win_rate": 70.0, "max_win": 200, "max_loss": -50}
        suggestions = self.generator._generate_suggestions(stats, [], [])

        assert len(suggestions) > 0
        assert any("胜率" in s for s in suggestions)

    def test_generate_suggestions_poor_profit_factor(self):
        """测试盈亏比不佳建议"""
        stats = {"win_rate": 50.0, "max_win": 50, "max_loss": -200}
        suggestions = self.generator._generate_suggestions(stats, [], [])

        assert len(suggestions) > 0
        assert any("盈亏比" in s or "止损" in s for s in suggestions)
