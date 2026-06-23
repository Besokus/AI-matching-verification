"""新闻分析师 Agent 测试"""

import pytest
import asyncio
from unittest.mock import MagicMock

from agent.agents.analyst import NewsAnalystAgent
from agent.graph.state import NewsReport


class TestNewsAnalystAgent:
    """新闻分析师测试"""

    def setup_method(self):
        """测试前准备"""
        self.agent = NewsAnalystAgent()

    def test_init(self):
        """测试初始化"""
        assert self.agent.name == "NewsAnalyst"
        assert self.agent.llm is None
        assert self.agent.data_provider is None

    def test_init_with_provider(self):
        """测试带 Provider 初始化"""
        mock_provider = MagicMock()
        agent = NewsAnalystAgent(data_provider=mock_provider)
        assert agent.data_provider is not None

    @pytest.mark.asyncio
    async def test_run_without_provider(self):
        """测试无 Provider 时运行"""
        result = await self.agent.run("600519")
        assert isinstance(result, NewsReport)
        assert result.events == []
        assert result.sentiment_score == 0.0

    @pytest.mark.asyncio
    async def test_run_with_positive_news(self):
        """测试利好新闻场景"""
        mock_provider = MagicMock()
        mock_provider.get_news.return_value = [
            {
                "security_id": "600519",
                "title": "贵州茅台业绩预增30%",
                "source": "东方财富",
                "publish_time": "2026-06-20 10:00:00",
                "sentiment": 0.3,
            },
            {
                "security_id": "600519",
                "title": "茅台回购计划获批",
                "source": "新浪财经",
                "publish_time": "2026-06-20 09:00:00",
                "sentiment": 0.3,
            },
        ]

        agent = NewsAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert isinstance(result, NewsReport)
        assert len(result.events) == 2
        assert result.sentiment_score > 0
        assert result.events[0]["impact"] == "positive"

    @pytest.mark.asyncio
    async def test_run_with_negative_news(self):
        """测试利空新闻场景"""
        mock_provider = MagicMock()
        mock_provider.get_news.return_value = [
            {
                "security_id": "600519",
                "title": "茅台高管减持",
                "source": "东方财富",
                "publish_time": "2026-06-20 10:00:00",
                "sentiment": -0.3,
            },
            {
                "security_id": "600519",
                "title": "白酒行业业绩预减",
                "source": "新浪财经",
                "publish_time": "2026-06-20 09:00:00",
                "sentiment": -0.3,
            },
        ]

        agent = NewsAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert len(result.events) == 2
        assert result.sentiment_score < 0
        assert result.events[0]["impact"] == "negative"

    @pytest.mark.asyncio
    async def test_run_with_mixed_news(self):
        """测试混合新闻场景"""
        mock_provider = MagicMock()
        mock_provider.get_news.return_value = [
            {
                "security_id": "600519",
                "title": "茅台业绩预增",
                "source": "东方财富",
                "publish_time": "2026-06-20 10:00:00",
                "sentiment": 0.3,
            },
            {
                "security_id": "600519",
                "title": "行业竞争加剧",
                "source": "新浪财经",
                "publish_time": "2026-06-20 09:00:00",
                "sentiment": -0.3,
            },
        ]

        agent = NewsAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert len(result.events) == 2
        assert abs(result.sentiment_score) < 0.1  # 正负抵消

    @pytest.mark.asyncio
    async def test_run_empty_news(self):
        """测试无新闻场景"""
        mock_provider = MagicMock()
        mock_provider.get_news.return_value = []

        agent = NewsAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        assert result.events == []
        assert result.sentiment_score == 0.0
        assert "暂无" in result.summary

    @pytest.mark.asyncio
    async def test_provider_exception(self):
        """测试 Provider 异常处理"""
        mock_provider = MagicMock()
        mock_provider.get_news.side_effect = Exception("网络错误")

        agent = NewsAnalystAgent(data_provider=mock_provider)
        result = await agent.run("600519")

        # 应返回默认值
        assert isinstance(result, NewsReport)
        assert result.events == []

    def test_analyze_with_rules_empty_list(self):
        """测试空新闻列表"""
        result = self.agent._analyze_with_rules("600519", [])
        assert result.events == []
        assert result.sentiment_score == 0.0
        assert "暂无" in result.summary

    def test_analyze_with_rules_multiple_news(self):
        """测试多条新闻"""
        news_list = [
            {"title": "利好1", "source": "新浪", "publish_time": "2026-06-20", "sentiment": 0.3},
            {"title": "利好2", "source": "东财", "publish_time": "2026-06-20", "sentiment": 0.3},
            {"title": "利空1", "source": "腾讯", "publish_time": "2026-06-20", "sentiment": -0.3},
        ]
        result = self.agent._analyze_with_rules("600519", news_list)
        assert len(result.events) == 3
        assert result.sentiment_score > 0  # 2利好1利空，整体偏正面
