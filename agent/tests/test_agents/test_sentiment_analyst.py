"""情绪面分析师 Agent 测试"""

import pytest
import asyncio
from unittest.mock import MagicMock

from agent.agents.analyst import SentimentAnalystAgent
from agent.graph.state import SentimentReport


class TestSentimentAnalystAgent:
    """情绪面分析师测试"""

    def setup_method(self):
        """测试前准备"""
        self.agent = SentimentAnalystAgent()

    def test_init(self):
        """测试初始化"""
        assert self.agent.name == "SentimentAnalyst"
        assert self.agent.llm is None
        assert self.agent.data_provider is None

    def test_init_with_provider(self):
        """测试带 Provider 初始化"""
        mock_provider = MagicMock()
        agent = SentimentAnalystAgent(data_provider=mock_provider)
        assert agent.data_provider is not None

    @pytest.mark.asyncio
    async def test_run_without_provider(self):
        """测试无 Provider 时运行"""
        result = await self.agent.run("600519")
        assert isinstance(result, SentimentReport)
        assert result.money_flow in ["inflow", "outflow", "neutral"]
        assert result.institutional_activity in ["active_buy", "active_sell", "neutral"]
        assert result.retail_sentiment in ["bullish", "bearish", "neutral"]

    @pytest.mark.asyncio
    async def test_run_with_inflow(self):
        """测试资金流入场景"""
        mock_provider = MagicMock()
        mock_provider.get_money_flow.return_value = {
            "security_id": "600519",
            "main_net_inflow": 5000000,  # 500万净流入
            "retail_net_inflow": -2000000,
            "total_amount": 50000000,  # 5000万成交额
            "main_ratio": 10.0,
            "main_net_inflow_pct": 10.0,
            "retail_net_inflow_pct": -4.0,
        }

        agent = SentimentAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert isinstance(result, SentimentReport)
        assert result.money_flow == "inflow"  # 主力净流入 > 5%
        assert result.institutional_activity == "active_buy"  # 主力净流入占比 > 10%

    @pytest.mark.asyncio
    async def test_run_with_outflow(self):
        """测试资金流出场景"""
        mock_provider = MagicMock()
        mock_provider.get_money_flow.return_value = {
            "security_id": "600519",
            "main_net_inflow": -8000000,  # 800万净流出
            "retail_net_inflow": 3000000,
            "total_amount": 60000000,
            "main_ratio": -13.3,
            "main_net_inflow_pct": -13.3,
            "retail_net_inflow_pct": 5.0,
        }

        agent = SentimentAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert result.money_flow == "outflow"  # 主力净流出 > 5%
        assert result.institutional_activity == "active_sell"  # 主力净流出占比 > 10%
        assert result.retail_sentiment == "bullish"  # 散户净流入 > 5%

    @pytest.mark.asyncio
    async def test_run_neutral(self):
        """测试中性场景"""
        mock_provider = MagicMock()
        mock_provider.get_money_flow.return_value = {
            "security_id": "600519",
            "main_net_inflow": 100000,  # 微量流入
            "retail_net_inflow": -50000,
            "total_amount": 100000000,
            "main_ratio": 0.1,
            "main_net_inflow_pct": 0.1,
            "retail_net_inflow_pct": -0.05,
        }

        agent = SentimentAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert result.money_flow == "neutral"
        assert result.institutional_activity == "neutral"
        assert result.retail_sentiment == "neutral"

    @pytest.mark.asyncio
    async def test_provider_exception(self):
        """测试 Provider 异常处理"""
        mock_provider = MagicMock()
        mock_provider.get_money_flow.side_effect = Exception("网络错误")

        agent = SentimentAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        # 应返回默认值
        assert isinstance(result, SentimentReport)
        assert result.money_flow == "neutral"

    def test_analyze_with_rules_empty_data(self):
        """测试空数据"""
        result = self.agent._analyze_with_rules("600519", {})
        assert result.money_flow == "neutral"
        assert result.institutional_activity == "neutral"
        assert result.retail_sentiment == "neutral"

    def test_analyze_with_rules_zero_amount(self):
        """测试零成交额"""
        data = {
            "main_net_inflow": 0,
            "total_amount": 0,
            "main_ratio": 0,
            "main_net_inflow_pct": 0,
            "retail_net_inflow_pct": 0,
        }
        result = self.agent._analyze_with_rules("600519", data)
        assert result.money_flow == "neutral"
