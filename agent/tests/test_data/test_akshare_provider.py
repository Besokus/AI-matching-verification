"""AKShare Provider 测试"""

import pytest
from datetime import datetime

from agent.data.providers.akshare_provider import AKShareProvider


class TestAKShareProvider:
    """AKShare Provider 测试"""

    @pytest.fixture
    def provider(self, tmp_path):
        """创建临时目录的 Provider"""
        return AKShareProvider(cache_dir=str(tmp_path / "cache"))

    def test_get_minute_klines(self, provider):
        """测试获取分钟线数据"""
        klines = provider.get_minute_klines(
            security_id="600519",
            start_date="2026-06-16",
            end_date="2026-06-20",
            use_cache=False,
        )
        # 验证返回列表
        assert isinstance(klines, list)
        if klines:  # 如果有数据
            kline = klines[0]
            assert kline.security_id == "600519"
            assert kline.open > 0
            assert kline.high >= kline.low
            assert kline.volume >= 0
            assert isinstance(kline.timestamp, datetime)

    def test_get_daily_klines(self, provider):
        """测试获取日线数据"""
        klines = provider.get_daily_klines(
            security_id="600519",
            start_date="2026-01-01",
            end_date="2026-06-20",
            use_cache=False,
        )
        assert isinstance(klines, list)
        if klines:
            kline = klines[0]
            assert kline.security_id == "600519"
            assert kline.open > 0
            assert kline.high >= kline.low

    def test_cache_minute_klines(self, provider):
        """测试分钟线缓存"""
        # 第一次获取
        klines1 = provider.get_minute_klines(
            security_id="600519",
            start_date="2026-06-16",
            end_date="2026-06-20",
            use_cache=False,
        )
        # 第二次从缓存获取
        klines2 = provider.get_minute_klines(
            security_id="600519",
            start_date="2026-06-16",
            end_date="2026-06-20",
            use_cache=True,
        )
        # 应该相等
        assert len(klines1) == len(klines2)

    def test_cache_daily_klines(self, provider):
        """测试日线缓存"""
        klines1 = provider.get_daily_klines(
            security_id="600519",
            start_date="2026-01-01",
            end_date="2026-06-20",
            use_cache=False,
        )
        klines2 = provider.get_daily_klines(
            security_id="600519",
            start_date="2026-01-01",
            end_date="2026-06-20",
            use_cache=True,
        )
        assert len(klines1) == len(klines2)
