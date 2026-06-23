"""绩效计算器测试"""

import pytest
from datetime import datetime

from agent.performance.calculator import PerformanceCalculator, TradeRecord
from agent.performance.reporter import PerformanceReporter


class TestPerformanceCalculator:
    """绩效计算器测试"""

    @pytest.fixture
    def calculator(self):
        return PerformanceCalculator(initial_capital=1_000_000)

    @pytest.fixture
    def profitable_trades(self):
        """盈利交易序列"""
        return [
            TradeRecord(
                trade_id=1, security_id="600519",
                price=100.0, volume=1000, side="BUY",
                timestamp=datetime(2026, 6, 20, 9, 30),
            ),
            TradeRecord(
                trade_id=2, security_id="600519",
                price=110.0, volume=1000, side="SELL",
                timestamp=datetime(2026, 6, 20, 10, 30),
            ),
        ]

    @pytest.fixture
    def losing_trades(self):
        """亏损交易序列"""
        return [
            TradeRecord(
                trade_id=1, security_id="600519",
                price=100.0, volume=1000, side="BUY",
                timestamp=datetime(2026, 6, 20, 9, 30),
            ),
            TradeRecord(
                trade_id=2, security_id="600519",
                price=90.0, volume=1000, side="SELL",
                timestamp=datetime(2026, 6, 20, 10, 30),
            ),
        ]

    def test_empty_trades(self, calculator):
        """测试空交易列表"""
        metrics = calculator.calculate([])
        assert metrics.total_trades == 0
        assert metrics.total_pnl == 0

    def test_profitable_trade(self, calculator, profitable_trades):
        """测试盈利交易"""
        metrics = calculator.calculate(profitable_trades)
        assert metrics.total_pnl > 0
        assert metrics.realized_pnl > 0
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 0
        assert metrics.win_rate == 1.0

    def test_losing_trade(self, calculator, losing_trades):
        """测试亏损交易"""
        metrics = calculator.calculate(losing_trades)
        assert metrics.total_pnl < 0
        assert metrics.realized_pnl < 0
        assert metrics.winning_trades == 0
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 0.0

    def test_max_drawdown(self, calculator):
        """测试最大回撤"""
        trades = [
            TradeRecord(
                trade_id=1, security_id="600519",
                price=100.0, volume=1000, side="BUY",
                timestamp=datetime(2026, 6, 20, 9, 30),
            ),
            TradeRecord(
                trade_id=2, security_id="600519",
                price=110.0, volume=1000, side="SELL",
                timestamp=datetime(2026, 6, 20, 10, 30),
            ),
            TradeRecord(
                trade_id=3, security_id="600519",
                price=110.0, volume=1000, side="BUY",
                timestamp=datetime(2026, 6, 20, 11, 30),
            ),
            TradeRecord(
                trade_id=4, security_id="600519",
                price=95.0, volume=1000, side="SELL",
                timestamp=datetime(2026, 6, 20, 12, 30),
            ),
        ]
        metrics = calculator.calculate(trades)
        assert metrics.max_drawdown > 0
        assert metrics.max_drawdown_pct > 0

    def test_total_return(self, calculator, profitable_trades):
        """测试收益率计算"""
        metrics = calculator.calculate(profitable_trades)
        expected_return = metrics.total_pnl / 1_000_000
        assert abs(metrics.total_return - expected_return) < 0.0001


class TestPerformanceReporter:
    """绩效报告生成器测试"""

    def test_generate_markdown(self):
        """测试 Markdown 报告生成"""
        metrics = PerformanceMetrics(
            total_pnl=10000.0,
            realized_pnl=10000.0,
            unrealized_pnl=0.0,
            total_return=0.01,
            sharpe_ratio=1.5,
            max_drawdown=5000.0,
            max_drawdown_pct=0.005,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            profit_factor=1.5,
            start_time=datetime(2026, 6, 20),
            end_time=datetime(2026, 6, 21),
            duration_days=1.0,
        )
        trades = [
            TradeRecord(
                trade_id=1, security_id="600519",
                price=100.0, volume=100, side="BUY",
                timestamp=datetime(2026, 6, 20, 9, 30),
            ),
        ]

        report = PerformanceReporter.generate_markdown(
            metrics, trades, security_id="600519"
        )
        assert "600519" in report
        assert "10,000.00" in report
        assert "1.00%" in report
