"""端到端集成测试

验证完整回测链路：
AKShare 数据 → Tick 合成 → Agent 决策 → 风控 → 绩效统计
"""

import pytest
import asyncio
from datetime import datetime

from agent.config import AppConfig
from agent.data.providers.akshare_provider import AKShareProvider
from agent.synthesizer.tick_synthesizer import TickSynthesizer, SynthesizerConfig
from agent.synthesizer.validator import SynthesisValidator
from agent.graph.trading_graph import TradingGraph
from agent.graph.state import AgentState
from agent.risk.engine import RiskEngine, RiskConfig
from agent.performance.calculator import PerformanceCalculator, TradeRecord
from agent.performance.reporter import PerformanceReporter


@pytest.fixture
def config():
    """测试配置"""
    cfg = AppConfig()
    cfg.backtest.security_id = "600519"
    cfg.backtest.start_date = "2026-06-16"
    cfg.backtest.end_date = "2026-06-20"
    cfg.backtest.initial_capital = 1_000_000
    return cfg


@pytest.fixture
def synthesizer():
    """Tick 合成器"""
    return TickSynthesizer(SynthesizerConfig(seed=42))


@pytest.fixture
def graph():
    """Agent 编排图"""
    return TradingGraph(risk_config=RiskConfig(), max_debate_rounds=1)


@pytest.fixture
def calculator():
    """绩效计算器"""
    return PerformanceCalculator(initial_capital=1_000_000)


class TestTickSynthesis:
    """Tick 合成测试"""

    def test_synthesize_minute_klines(self, synthesizer):
        """测试从分钟线合成 tick 事件"""
        from agent.data.models.market import KLine

        klines = [
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 30),
                open=1800.0, high=1810.0, low=1795.0,
                close=1805.0, volume=10000,
            ),
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 31),
                open=1805.0, high=1812.0, low=1800.0,
                close=1808.0, volume=8000,
            ),
        ]

        events = synthesizer.synthesize(klines)
        assert len(events) > 0

        # 验证事件类型
        event_types = set(e.event_type for e in events)
        assert "ORDER_ADD" in event_types
        assert "TRADE" in event_types

    def test_synthesis_validator(self, synthesizer):
        """测试合成质量验证"""
        from agent.data.models.market import KLine

        klines = [
            KLine(
                security_id="600519",
                timestamp=datetime(2026, 6, 20, 9, 30),
                open=100.0, high=105.0, low=98.0,
                close=103.0, volume=1000,
            ),
        ]

        events = synthesizer.synthesize(klines)
        validator = SynthesisValidator(price_tolerance=0.1, volume_tolerance=0.2)
        result = validator.validate(klines, events)

        # 基本验证应通过
        assert result.checks.get("time_causality", False)
        assert result.checks.get("event_completeness", False)


class TestAgentDecision:
    """Agent 决策测试"""

    @pytest.mark.asyncio
    async def test_agent_run(self, graph):
        """测试 Agent 运行"""
        state: AgentState = {
            "security_id": "600519",
            "security_name": "贵州茅台",
            "trade_date": "2026-06-20",
            "market_snapshot": {
                "security_id": "600519",
                "last_price": 1800.0,
                "bids": [(1799.0, 100), (1798.0, 200)],
                "asks": [(1801.0, 100), (1802.0, 200)],
                "total_volume": 10000,
                "total_amount": 18000000,
            },
            "recent_klines": [
                {"timestamp": "2026-06-20 09:30", "open": 1800, "high": 1810, "low": 1795, "close": 1805, "volume": 10000},
                {"timestamp": "2026-06-20 09:31", "open": 1805, "high": 1812, "low": 1800, "close": 1808, "volume": 8000},
            ],
            "daily_klines": [],
            "technical_report": None,
            "fundamental_report": None,
            "sentiment_report": None,
            "news_report": None,
            "debate_state": None,
            "order_decision": None,
            "risk_decision": None,
            "position": {"volume": 0, "avg_price": 0, "pnl": 0},
            "final_decision": "",
            "node_timings": {},
        }

        result = await graph.run(state)

        # 验证输出
        assert result["technical_report"] is not None
        assert result["order_decision"] is not None
        assert result["risk_decision"] is not None
        assert result["final_decision"] in ["EXECUTE", "REJECT", "HOLD"]
        assert result["node_timings"]["total"] > 0


class TestRiskControl:
    """风控测试"""

    def test_risk_engine_approve(self):
        """测试风控通过"""
        from agent.graph.state import OrderDecision

        engine = RiskEngine(RiskConfig())
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

    def test_risk_engine_reject(self):
        """测试风控拒绝"""
        from agent.graph.state import OrderDecision

        engine = RiskEngine(RiskConfig())
        decision = OrderDecision(
            action="BUY", security_id="600519",
            price=100.0, volume=100, confidence=0.1,  # 低置信度
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


class TestPerformanceCalculation:
    """绩效计算测试"""

    def test_full_backtest_performance(self, calculator):
        """测试完整回测绩效计算"""
        trades = [
            TradeRecord(trade_id=1, security_id="600519", price=100.0, volume=1000, side="BUY", timestamp=datetime(2026, 6, 20, 9, 30)),
            TradeRecord(trade_id=2, security_id="600519", price=110.0, volume=1000, side="SELL", timestamp=datetime(2026, 6, 20, 10, 30)),
            TradeRecord(trade_id=3, security_id="600519", price=105.0, volume=1000, side="BUY", timestamp=datetime(2026, 6, 20, 11, 30)),
            TradeRecord(trade_id=4, security_id="600519", price=115.0, volume=1000, side="SELL", timestamp=datetime(2026, 6, 20, 14, 30)),
        ]

        metrics = calculator.calculate(trades)

        # 验证指标
        assert metrics.total_trades == 4
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 0
        assert metrics.win_rate == 1.0
        assert metrics.total_pnl > 0
        assert metrics.realized_pnl > 0
        assert metrics.final_position == 0

    def test_report_generation(self, calculator):
        """测试报告生成"""
        trades = [
            TradeRecord(trade_id=1, security_id="600519", price=100.0, volume=1000, side="BUY", timestamp=datetime(2026, 6, 20, 9, 30)),
            TradeRecord(trade_id=2, security_id="600519", price=110.0, volume=1000, side="SELL", timestamp=datetime(2026, 6, 20, 10, 30)),
        ]

        metrics = calculator.calculate(trades)
        report = PerformanceReporter.generate_markdown(metrics, trades, security_id="600519")

        assert "600519" in report
        assert "总盈亏" in report
        assert "夏普比率" in report


class TestEndToEndPipeline:
    """端到端管道测试"""

    @pytest.mark.asyncio
    async def test_full_pipeline_simulation(self, synthesizer, graph, calculator):
        """测试完整管道（模拟模式）"""
        from agent.data.models.market import KLine

        # 1. 准备数据
        klines = [
            KLine(security_id="600519", timestamp=datetime(2026, 6, 20, 9, 30), open=1800.0, high=1810.0, low=1795.0, close=1805.0, volume=10000),
            KLine(security_id="600519", timestamp=datetime(2026, 6, 20, 9, 31), open=1805.0, high=1812.0, low=1800.0, close=1808.0, volume=8000),
        ]

        # 2. 合成 tick
        events = synthesizer.synthesize(klines)
        assert len(events) > 0

        # 3. 模拟 Agent 决策
        trades = []
        for kline in klines:
            state: AgentState = {
                "security_id": "600519",
                "security_name": "贵州茅台",
                "trade_date": "2026-06-20",
                "market_snapshot": {
                    "security_id": "600519",
                    "last_price": kline.close,
                    "bids": [(kline.close - i, 100) for i in range(10)],
                    "asks": [(kline.close + i, 100) for i in range(10)],
                    "total_volume": kline.volume,
                    "total_amount": kline.amount,
                },
                "recent_klines": [
                    {"timestamp": kline.timestamp.isoformat(), "open": kline.open, "high": kline.high, "low": kline.low, "close": kline.close, "volume": kline.volume},
                ],
                "daily_klines": [],
                "technical_report": None,
                "fundamental_report": None,
                "sentiment_report": None,
                "news_report": None,
                "debate_state": None,
                "order_decision": None,
                "risk_decision": None,
                "position": {"volume": 0, "avg_price": 0, "pnl": 0},
                "final_decision": "",
                "node_timings": {},
            }

            result = await graph.run(state)

            if result["final_decision"] == "EXECUTE":
                order = result["order_decision"]
                trades.append(TradeRecord(
                    trade_id=len(trades) + 1,
                    security_id=order.security_id,
                    price=order.price,
                    volume=order.volume,
                    side=order.action,
                    timestamp=kline.timestamp,
                ))

        # 4. 计算绩效
        metrics = calculator.calculate(trades)

        # 5. 生成报告
        report = PerformanceReporter.generate_markdown(metrics, trades, security_id="600519")

        # 验证
        assert metrics.total_trades >= 0
        assert "600519" in report
