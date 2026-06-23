"""研究员 Agent 测试 - Bull/Bear 辩论"""

import pytest
import asyncio

from agent.agents.researcher import BullResearcher, BearResearcher, DebateModerator
from agent.graph.state import (
    TechnicalReport, FundamentalReport, SentimentReport, NewsReport,
    DebateState,
)


class TestBullResearcher:
    """看多研究员测试"""

    def setup_method(self):
        self.researcher = BullResearcher()

    def test_init(self):
        assert self.researcher.name == "BullResearcher"

    @pytest.mark.asyncio
    async def test_argue_basic(self):
        """测试基本论据生成"""
        technical = TechnicalReport(signal="buy", trend="bullish", confidence=0.7)
        fundamental = FundamentalReport(valuation="undervalued", quality="strong")
        sentiment = SentimentReport(money_flow="inflow")
        news = NewsReport(sentiment_score=0.3)

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert "买入" in result or "低估" in result or "流入" in result

    @pytest.mark.asyncio
    async def test_argue_with_rebuttal(self):
        """测试带反驳的论据"""
        technical = TechnicalReport(signal="buy", trend="bullish", confidence=0.7)
        fundamental = FundamentalReport(valuation="undervalued")
        sentiment = SentimentReport(money_flow="inflow")
        news = NewsReport(sentiment_score=0.3)

        bear_argument = "估值偏高，资金流出"

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
            bear_argument=bear_argument, round_num=2,
        )

        assert isinstance(result, str)
        # 应包含反驳内容
        assert "反驳" in result or "高估" in result or "流出" in result

    @pytest.mark.asyncio
    async def test_argue_no_signals(self):
        """测试无信号场景"""
        technical = TechnicalReport(signal="hold", trend="neutral")
        fundamental = FundamentalReport(valuation="fair")
        sentiment = SentimentReport(money_flow="neutral")
        news = NewsReport(sentiment_score=0.0)

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_rebut_high_valuation(self):
        """测试反驳高估论据"""
        result = self.researcher._rebut("估值偏高，PE 超过 50")
        assert "高 PE" in result or "成长性" in result

    def test_rebut_outflow(self):
        """测试反驳资金流出论据"""
        result = self.researcher._rebut("主力资金净流出")
        assert "资金流出" in result or "调整" in result

    def test_rebut_empty(self):
        """测试空论据反驳"""
        result = self.researcher._rebut("")
        assert result == ""


class TestBearResearcher:
    """看空研究员测试"""

    def setup_method(self):
        self.researcher = BearResearcher()

    def test_init(self):
        assert self.researcher.name == "BearResearcher"

    @pytest.mark.asyncio
    async def test_argue_basic(self):
        """测试基本论据生成"""
        technical = TechnicalReport(signal="sell", trend="bearish", confidence=0.7)
        fundamental = FundamentalReport(valuation="overvalued", quality="weak")
        sentiment = SentimentReport(money_flow="outflow")
        news = NewsReport(sentiment_score=-0.3)

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert "卖出" in result or "高估" in result or "流出" in result

    @pytest.mark.asyncio
    async def test_argue_with_rebuttal(self):
        """测试带反驳的论据"""
        technical = TechnicalReport(signal="sell", trend="bearish", confidence=0.7)
        fundamental = FundamentalReport(valuation="overvalued")
        sentiment = SentimentReport(money_flow="outflow")
        news = NewsReport(sentiment_score=-0.3)

        bull_argument = "估值偏低，资金流入"

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
            bull_argument=bull_argument, round_num=2,
        )

        assert isinstance(result, str)
        # 应包含反驳内容
        assert "反驳" in result or "低估" in result or "流入" in result

    @pytest.mark.asyncio
    async def test_argue_no_signals(self):
        """测试无信号场景"""
        technical = TechnicalReport(signal="hold", trend="neutral")
        fundamental = FundamentalReport(valuation="fair")
        sentiment = SentimentReport(money_flow="neutral")
        news = NewsReport(sentiment_score=0.0)

        result = await self.researcher.argue(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_rebut_low_valuation(self):
        """测试反驳低估论据"""
        result = self.researcher._rebut("估值偏低，具备投资价值")
        assert "低估值" in result or "基本面" in result

    def test_rebut_inflow(self):
        """测试反驳资金流入论据"""
        result = self.researcher._rebut("主力资金净流入")
        assert "资金流入" in result or "炒作" in result


class TestDebateModerator:
    """辩论主持人测试"""

    def setup_method(self):
        self.bull = BullResearcher()
        self.bear = BearResearcher()
        self.moderator = DebateModerator(self.bull, self.bear, max_rounds=2)

    def test_init(self):
        assert self.moderator.max_rounds == 2
        assert self.moderator.consensus_threshold == 0.7

    @pytest.mark.asyncio
    async def test_debate_basic(self):
        """测试基本辩论流程"""
        technical = TechnicalReport(signal="buy", trend="bullish", confidence=0.7)
        fundamental = FundamentalReport(valuation="undervalued", quality="strong")
        sentiment = SentimentReport(money_flow="inflow")
        news = NewsReport(sentiment_score=0.3)

        result = await self.moderator.debate(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, DebateState)
        assert result.round >= 1
        assert result.round <= 2
        assert len(result.bull_history) >= 1
        assert len(result.bear_history) >= 1
        assert result.consensus in ["偏多", "偏空", "中性"]
        assert 0 <= result.confidence <= 1

    @pytest.mark.asyncio
    async def test_debate_multi_round(self):
        """测试多轮辩论"""
        technical = TechnicalReport(signal="buy", trend="bullish", confidence=0.5)
        fundamental = FundamentalReport(valuation="fair")
        sentiment = SentimentReport(money_flow="neutral")
        news = NewsReport(sentiment_score=0.0)

        moderator = DebateModerator(self.bull, self.bear, max_rounds=3)
        result = await moderator.debate(
            "600519", technical, fundamental, sentiment, news,
        )

        assert isinstance(result, DebateState)
        assert result.round <= 3
        assert len(result.bull_history) == result.round
        assert len(result.bear_history) == result.round

    @pytest.mark.asyncio
    async def test_debate_consensus_bull(self):
        """测试看多共识"""
        technical = TechnicalReport(signal="buy", trend="bullish", confidence=0.9)
        fundamental = FundamentalReport(valuation="undervalued", quality="strong", growth="high")
        sentiment = SentimentReport(money_flow="inflow", institutional_activity="active_buy")
        news = NewsReport(sentiment_score=0.5)

        result = await self.moderator.debate(
            "600519", technical, fundamental, sentiment, news,
        )

        # 强看多信号应导致偏多共识
        assert result.consensus == "偏多"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_debate_consensus_bear(self):
        """测试看空共识"""
        technical = TechnicalReport(signal="sell", trend="bearish", confidence=0.9)
        fundamental = FundamentalReport(valuation="overvalued", quality="weak", growth="low")
        sentiment = SentimentReport(money_flow="outflow", institutional_activity="active_sell")
        news = NewsReport(sentiment_score=-0.5)

        result = await self.moderator.debate(
            "600519", technical, fundamental, sentiment, news,
        )

        # 强看空信号应导致偏空共识
        assert result.consensus == "偏空"
        assert result.confidence > 0.5

    def test_extract_consensus_bull(self):
        """测试提取看多共识"""
        technical = TechnicalReport(signal="buy", confidence=0.8)
        fundamental = FundamentalReport(valuation="undervalued")
        sentiment = SentimentReport(money_flow="inflow")

        consensus, confidence = self.moderator._extract_consensus(
            "看多论据", "看空论据", technical, fundamental, sentiment,
        )

        assert consensus == "偏多"
        assert confidence > 0.5

    def test_extract_consensus_bear(self):
        """测试提取看空共识"""
        technical = TechnicalReport(signal="sell", confidence=0.8)
        fundamental = FundamentalReport(valuation="overvalued")
        sentiment = SentimentReport(money_flow="outflow")

        consensus, confidence = self.moderator._extract_consensus(
            "看多论据", "看空论据", technical, fundamental, sentiment,
        )

        assert consensus == "偏空"
        assert confidence > 0.5

    def test_extract_consensus_neutral(self):
        """测试中性共识"""
        technical = TechnicalReport(signal="hold", confidence=0.5)
        fundamental = FundamentalReport(valuation="fair")
        sentiment = SentimentReport(money_flow="neutral")

        consensus, confidence = self.moderator._extract_consensus(
            "多空混杂", "多空混杂", technical, fundamental, sentiment,
        )

        assert consensus == "中性"
