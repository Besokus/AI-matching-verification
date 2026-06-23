"""基本面分析师 Agent 测试"""

import pytest
import asyncio
from unittest.mock import MagicMock

from agent.agents.analyst import FundamentalAnalystAgent
from agent.graph.state import FundamentalReport


class TestFundamentalAnalystAgent:
    """基本面分析师测试"""

    def setup_method(self):
        """测试前准备"""
        self.agent = FundamentalAnalystAgent()

    def test_init(self):
        """测试初始化"""
        assert self.agent.name == "FundamentalAnalyst"
        assert self.agent.llm is None
        assert self.agent.data_provider is None

    def test_init_with_provider(self):
        """测试带 Provider 初始化"""
        mock_provider = MagicMock()
        agent = FundamentalAnalystAgent(data_provider=mock_provider)
        assert agent.data_provider is not None

    @pytest.mark.asyncio
    async def test_run_without_provider(self):
        """测试无 Provider 时运行"""
        result = await self.agent.run("600519")
        assert isinstance(result, FundamentalReport)
        assert result.valuation in ["undervalued", "fair", "overvalued"]
        assert result.quality in ["strong", "moderate", "weak"]
        assert result.growth in ["high", "moderate", "low"]

    @pytest.mark.asyncio
    async def test_run_with_provider(self):
        """测试有 Provider 时运行"""
        mock_provider = MagicMock()
        mock_provider.get_financial_indicator.return_value = {
            "security_id": "600519",
            "pe_ttm": 25.0,
            "pb": 3.5,
            "roe": 25.0,
            "gross_margin": 90.0,
            "debt_ratio": 30.0,
            "revenue_growth": 15.0,
            "net_profit_growth": 20.0,
        }

        agent = FundamentalAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert isinstance(result, FundamentalReport)
        assert result.valuation == "fair"  # PE=25, 合理区间
        assert result.quality == "strong"  # ROE=25 > 20
        assert result.growth == "moderate"  # 营收增长 15%

    @pytest.mark.asyncio
    async def test_undervalued_stock(self):
        """测试低估股票"""
        mock_provider = MagicMock()
        mock_provider.get_financial_indicator.return_value = {
            "security_id": "600519",
            "pe_ttm": 10.0,
            "pb": 1.0,
            "roe": 20.0,
            "gross_margin": 50.0,
            "debt_ratio": 40.0,
            "revenue_growth": 25.0,
            "net_profit_growth": 30.0,
        }

        agent = FundamentalAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert result.valuation == "undervalued"  # PE=10 < 15
        assert result.quality == "strong"  # ROE=20 > 20

    @pytest.mark.asyncio
    async def test_overvalued_stock(self):
        """测试高估股票"""
        mock_provider = MagicMock()
        mock_provider.get_financial_indicator.return_value = {
            "security_id": "600519",
            "pe_ttm": 50.0,
            "pb": 15.0,
            "roe": 5.0,
            "gross_margin": 20.0,
            "debt_ratio": 80.0,
            "revenue_growth": -10.0,
            "net_profit_growth": -20.0,
        }

        agent = FundamentalAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert result.valuation == "overvalued"  # PE=50 > 30
        assert result.quality == "weak"  # ROE=5 < 10
        assert result.growth == "low"  # 营收增长 -10%
        assert len(result.risk_factors) > 0  # 应有风险因子

    @pytest.mark.asyncio
    async def test_provider_exception(self):
        """测试 Provider 异常处理"""
        mock_provider = MagicMock()
        mock_provider.get_financial_indicator.side_effect = Exception("网络错误")

        agent = FundamentalAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        # 应返回默认值
        assert isinstance(result, FundamentalReport)
        assert result.valuation == "fair"

    def test_analyze_with_rules_high_roe(self):
        """测试高 ROE 评分"""
        data = {
            "pe_ttm": 20.0,
            "pb": 3.0,
            "roe": 25.0,
            "gross_margin": 60.0,
            "debt_ratio": 30.0,
            "revenue_growth": 20.0,
            "net_profit_growth": 25.0,
        }
        result = self.agent._analyze_with_rules("600519", data)
        assert result.quality == "strong"
        assert result.valuation == "fair"

    def test_analyze_with_rules_high_debt(self):
        """测试高负债评分"""
        data = {
            "pe_ttm": 20.0,
            "pb": 3.0,
            "roe": 15.0,
            "gross_margin": 40.0,
            "debt_ratio": 85.0,
            "revenue_growth": 10.0,
            "net_profit_growth": 10.0,
        }
        result = self.agent._analyze_with_rules("600519", data)
        assert "资产负债率" in str(result.risk_factors)

    def test_analyze_with_rules_empty_data(self):
        """测试空数据"""
        result = self.agent._analyze_with_rules("600519", {})
        assert result.valuation == "fair"
        assert result.quality == "weak"  # ROE=0 < 10
        assert result.growth == "low"  # 营收增长=0 < 5
