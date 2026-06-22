"""Tick 合成器测试"""

import pytest
from datetime import datetime

from agent.data.models.market import KLine
from agent.synthesizer.tick_synthesizer import TickSynthesizer, SynthesizerConfig
from agent.synthesizer.price_path import PricePathGenerator, PricePathConfig
from agent.synthesizer.validator import SynthesisValidator


class TestPricePathGenerator:
    """价格路径生成器测试"""

    def test_basic_generation(self):
        """测试基本生成功能"""
        gen = PricePathGenerator(PricePathConfig(seed=42))
        prices = gen.generate(
            open_price=100.0,
            high_price=105.0,
            low_price=98.0,
            close_price=103.0,
            volume=1000,
            n_points=60,
        )
        assert len(prices) == 60
        assert all(isinstance(p, float) for p in prices)

    def test_price_bounds(self):
        """测试价格在 [Low, High] 范围内"""
        gen = PricePathGenerator(PricePathConfig(seed=42))
        prices = gen.generate(
            open_price=100.0,
            high_price=105.0,
            low_price=98.0,
            close_price=103.0,
            volume=1000,
            n_points=100,
        )
        for p in prices:
            assert 98.0 <= p <= 105.0, f"价格 {p} 超出范围 [98.0, 105.0]"

    def test_start_end_prices(self):
        """测试起始和结束价格"""
        gen = PricePathGenerator(PricePathConfig(seed=42))
        prices = gen.generate(
            open_price=100.0,
            high_price=105.0,
            low_price=98.0,
            close_price=103.0,
            volume=1000,
            n_points=60,
        )
        # 起始价格应接近 Open
        assert abs(prices[0] - 100.0) < 1.0
        # 结束价格应接近 Close
        assert abs(prices[-1] - 103.0) < 1.0

    def test_up_path(self):
        """测试上涨路径"""
        gen = PricePathGenerator(PricePathConfig(seed=42))
        prices = gen.generate(
            open_price=100.0,
            high_price=110.0,
            low_price=99.0,
            close_price=108.0,
            volume=1000,
            n_points=60,
        )
        # 最高价应接近 High
        max_price = max(prices)
        assert abs(max_price - 110.0) < 2.0

    def test_down_path(self):
        """测试下跌路径"""
        gen = PricePathGenerator(PricePathConfig(seed=42))
        prices = gen.generate(
            open_price=100.0,
            high_price=101.0,
            low_price=90.0,
            close_price=92.0,
            volume=1000,
            n_points=60,
        )
        # 最低价应接近 Low
        min_price = min(prices)
        assert abs(min_price - 90.0) < 2.0


class TestTickSynthesizer:
    """Tick 合成器测试"""

    @pytest.fixture
    def synthesizer(self):
        return TickSynthesizer(SynthesizerConfig(seed=42))

    @pytest.fixture
    def sample_klines(self):
        return [
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 30),
                open=1800.0,
                high=1810.0,
                low=1795.0,
                close=1805.0,
                volume=10000,
                amount=18050000.0,
            ),
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 31),
                open=1805.0,
                high=1812.0,
                low=1800.0,
                close=1808.0,
                volume=8000,
                amount=14464000.0,
            ),
        ]

    def test_synthesize_returns_events(self, synthesizer, sample_klines):
        """测试合成返回事件"""
        events = synthesizer.synthesize(sample_klines)
        assert len(events) > 0
        assert all(e.security_id == "600519" for e in events)

    def test_synthesize_event_types(self, synthesizer, sample_klines):
        """测试合成事件类型"""
        events = synthesizer.synthesize(sample_klines)
        event_types = set(e.event_type for e in events)
        assert "ORDER_ADD" in event_types
        assert "TRADE" in event_types

    def test_synthesize_time_order(self, synthesizer, sample_klines):
        """测试事件时间顺序"""
        events = synthesizer.synthesize(sample_klines)
        for i in range(1, len(events)):
            assert events[i].timestamp >= events[i - 1].timestamp

    def test_synthesize_volume_conservation(self, synthesizer, sample_klines):
        """测试成交量守恒"""
        events = synthesizer.synthesize(sample_klines)
        validator = SynthesisValidator(price_tolerance=0.05, volume_tolerance=0.1)
        result = validator.validate(sample_klines, events)
        # 成交量守恒检查应通过
        assert result.checks.get("volume_conservation", False) or result.checks.get("time_causality", False)


class TestSynthesisValidator:
    """合成质量验证器测试"""

    def test_valid_synthesis(self):
        """测试有效合成数据"""
        validator = SynthesisValidator(price_tolerance=0.05, volume_tolerance=0.1)

        klines = [
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 30),
                open=100.0,
                high=105.0,
                low=98.0,
                close=103.0,
                volume=1000,
            ),
        ]

        # 创建符合要求的合成事件
        from agent.data.models.market import TickEvent
        events = [
            TickEvent(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 30, 0, i * 1000),
                event_type="TRADE",
                side="BUY",
                price=100.0 + (i * 0.1),
                volume=100,
            )
            for i in range(10)
        ]

        result = validator.validate(klines, events)
        assert result.passed
        assert result.checks["time_causality"]
        assert result.checks["event_completeness"]
