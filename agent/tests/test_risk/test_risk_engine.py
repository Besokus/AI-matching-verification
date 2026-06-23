"""风控引擎测试"""

import pytest

from agent.graph.state import OrderDecision
from agent.risk.engine import RiskEngine, RiskConfig
from agent.risk.rules import (
    MaxPositionRule, ConcentrationRule, LimitPriceRule,
    MinVolumeRule, FrequencyRule,
    DailyLossRule, ConsecutiveLossRule, ConfidenceRule, DataAnomalyRule,
)


class TestRiskRules:
    """风控规则测试"""

    def test_max_position_rule_pass(self):
        """测试仓位限制 - 通过"""
        rule = MaxPositionRule(max_pct=0.10)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {"total_capital": 1_000_000}
        result = rule.evaluate(decision, context)
        assert result.passed

    def test_max_position_rule_fail(self):
        """测试仓位限制 - 超限"""
        rule = MaxPositionRule(max_pct=0.10)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=2000, confidence=0.8,
        )
        context = {"total_capital": 1_000_000}
        result = rule.evaluate(decision, context)
        # 应该调整到最大允许值
        assert result.passed
        assert result.adjusted_order is not None
        assert result.adjusted_order.volume == 1000

    def test_concentration_rule_pass(self):
        """测试集中度限制 - 通过"""
        rule = ConcentrationRule(max_pct=0.30)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {
            "total_capital": 1_000_000,
            "position": {"volume": 0, "avg_price": 0},
        }
        result = rule.evaluate(decision, context)
        assert result.passed

    def test_limit_price_rule_buy_limit(self):
        """测试涨停追买禁止"""
        rule = LimitPriceRule(limit_pct=0.10)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=110.0, volume=100, confidence=0.8,
        )
        context = {"last_close": 100.0}
        result = rule.evaluate(decision, context)
        assert not result.passed
        assert "涨停追买" in result.reason

    def test_min_volume_rule_pass(self):
        """测试最小交易量 - 通过"""
        rule = MinVolumeRule(min_volume=100)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        result = rule.evaluate(decision, {})
        assert result.passed

    def test_min_volume_rule_fail(self):
        """测试最小交易量 - 不足"""
        rule = MinVolumeRule(min_volume=100)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=50, confidence=0.8,
        )
        result = rule.evaluate(decision, {})
        assert not result.passed

    def test_frequency_rule_pass(self):
        """测试交易频率 - 通过"""
        rule = FrequencyRule(max_per_minute=3)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {"recent_trades_count": 2}
        result = rule.evaluate(decision, context)
        assert result.passed

    def test_frequency_rule_fail(self):
        """测试交易频率 - 超限"""
        rule = FrequencyRule(max_per_minute=3)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {"recent_trades_count": 3}
        result = rule.evaluate(decision, context)
        assert not result.passed

    def test_daily_loss_rule_pass(self):
        """测试日亏损限制 - 通过"""
        rule = DailyLossRule(max_loss_pct=0.05)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {"daily_pnl": -1000, "total_capital": 1_000_000}
        result = rule.evaluate(decision, context)
        assert result.passed

    def test_daily_loss_rule_fail(self):
        """测试日亏损限制 - 超限"""
        rule = DailyLossRule(max_loss_pct=0.05)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {"daily_pnl": -60000, "total_capital": 1_000_000}
        result = rule.evaluate(decision, context)
        assert not result.passed

    def test_confidence_rule_pass(self):
        """测试置信度限制 - 通过"""
        rule = ConfidenceRule(min_confidence=0.3)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.5,
        )
        result = rule.evaluate(decision, {})
        assert result.passed

    def test_confidence_rule_fail(self):
        """测试置信度限制 - 不足"""
        rule = ConfidenceRule(min_confidence=0.3)
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.2,
        )
        result = rule.evaluate(decision, {})
        assert not result.passed

    def test_data_anomaly_rule_price(self):
        """测试数据异常 - 价格异常"""
        rule = DataAnomalyRule()
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=-100.0, volume=100, confidence=0.8,
        )
        result = rule.evaluate(decision, {})
        assert not result.passed

    def test_hold_always_passes(self):
        """测试 HOLD 指令总是通过"""
        rule = MaxPositionRule()
        decision = OrderDecision(action="HOLD")
        result = rule.evaluate(decision, {})
        assert result.passed


class TestRiskEngine:
    """风控引擎测试"""

    @pytest.fixture
    def engine(self):
        return RiskEngine(RiskConfig())

    def test_hold_decision(self, engine):
        """测试 HOLD 决策"""
        decision = OrderDecision(action="HOLD")
        result = engine.check(decision, {})
        assert result.approved

    def test_valid_buy(self, engine):
        """测试有效买入"""
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.8,
        )
        context = {
            "total_capital": 1_000_000,
            "position": {"volume": 0, "avg_price": 0},
            "daily_pnl": 0,
            "consecutive_losses": 0,
            "recent_trades_count": 0,
            "last_close": 100.0,
        }
        result = engine.check(decision, context)
        assert result.approved

    def test_rejected_by_confidence(self, engine):
        """测试因置信度不足被拒绝"""
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.1,
        )
        context = {
            "total_capital": 1_000_000,
            "position": {"volume": 0, "avg_price": 0},
            "daily_pnl": 0,
            "consecutive_losses": 0,
            "recent_trades_count": 0,
            "last_close": 100.0,
        }
        result = engine.check(decision, context)
        assert not result.approved
        assert "置信度" in result.reason

    def test_adjusted_order(self, engine):
        """测试订单调整"""
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=2000, confidence=0.8,
        )
        context = {
            "total_capital": 1_000_000,
            "position": {"volume": 0, "avg_price": 0},
            "daily_pnl": 0,
            "consecutive_losses": 0,
            "recent_trades_count": 0,
            "last_close": 100.0,
        }
        result = engine.check(decision, context)
        assert result.approved
        assert result.adjusted_order is not None
        assert result.adjusted_order.volume == 1000
