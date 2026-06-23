"""分析师 Agent 实现

包含：
- TechnicalAnalyst: 技术面分析师
- FundamentalAnalyst: 基本面分析师
- SentimentAnalyst: 情绪面分析师
- NewsAnalyst: 新闻分析师
"""

import json
from typing import Any

from .base import BaseAgent
from ..graph.state import TechnicalReport, FundamentalReport, SentimentReport, NewsReport


class TechnicalAnalystAgent(BaseAgent):
    """技术面分析师

    基于 MACD/RSI/KDJ/布林带等技术指标判断趋势。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="TechnicalAnalyst")

    async def run(
        self,
        security_id: str,
        snapshot: dict,
        klines: list[dict],
        **kwargs,
    ) -> TechnicalReport:
        """运行技术面分析

        Args:
            security_id: 股票代码
            snapshot: 市场快照
            klines: 分钟 K 线数据

        Returns:
            TechnicalReport
        """
        # 计算技术指标
        indicators = self._calculate_indicators(klines)

        # 如果有 LLM，使用 LLM 分析
        if self.llm:
            return await self._analyze_with_llm(security_id, snapshot, klines, indicators)

        # 否则使用规则判断
        return self._analyze_with_rules(indicators, snapshot)

    def _calculate_indicators(self, klines: list[dict]) -> dict:
        """计算技术指标"""
        if not klines or len(klines) < 5:
            return {}

        closes = [k.get("close", 0) for k in klines]
        highs = [k.get("high", 0) for k in klines]
        lows = [k.get("low", 0) for k in klines]
        volumes = [k.get("volume", 0) for k in klines]

        indicators = {}

        # MACD（简化版）
        if len(closes) >= 26:
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            macd_line = ema12 - ema26
            indicators["macd"] = {
                "macd": macd_line,
                "signal": "bullish" if macd_line > 0 else "bearish",
            }

        # RSI（14 期）
        if len(closes) >= 14:
            rsi = self._rsi(closes, 14)
            indicators["rsi"] = {
                "value": rsi,
                "signal": "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral",
            }

        # 布林带
        if len(closes) >= 20:
            bb = self._bollinger_bands(closes, 20)
            indicators["bollinger"] = bb

        # 成交量变化
        if len(volumes) >= 5:
            avg_vol = sum(volumes[-5:]) / 5
            current_vol = volumes[-1]
            indicators["volume"] = {
                "current": current_vol,
                "average": avg_vol,
                "ratio": current_vol / avg_vol if avg_vol > 0 else 1.0,
            }

        return indicators

    def _analyze_with_rules(
        self, indicators: dict, snapshot: dict
    ) -> TechnicalReport:
        """使用规则进行技术分析"""
        signals = []
        confidence = 0.5

        # MACD 信号
        macd = indicators.get("macd", {})
        if macd.get("signal") == "bullish":
            signals.append("MACD 金叉")
            confidence += 0.1
        elif macd.get("signal") == "bearish":
            signals.append("MACD 死叉")
            confidence -= 0.1

        # RSI 信号
        rsi = indicators.get("rsi", {})
        if rsi.get("signal") == "oversold":
            signals.append("RSI 超卖")
            confidence += 0.1
        elif rsi.get("signal") == "overbought":
            signals.append("RSI 超买")
            confidence -= 0.1

        # 布林带信号
        bb = indicators.get("bollinger", {})
        last_price = snapshot.get("last_price", 0)
        if bb:
            if last_price <= bb.get("lower", 0):
                signals.append("触及布林带下轨")
                confidence += 0.1
            elif last_price >= bb.get("upper", 0):
                signals.append("触及布林带上轨")
                confidence -= 0.1

        # 综合判断
        if confidence > 0.6:
            trend = "bullish"
            signal = "buy"
        elif confidence < 0.4:
            trend = "bearish"
            signal = "sell"
        else:
            trend = "neutral"
            signal = "hold"

        return TechnicalReport(
            trend=trend,
            signal=signal,
            confidence=max(0.0, min(1.0, confidence)),
            indicators=indicators,
            summary=f"技术指标信号: {', '.join(signals) if signals else '无明显信号'}",
        )

    async def _analyze_with_llm(
        self,
        security_id: str,
        snapshot: dict,
        klines: list[dict],
        indicators: dict,
    ) -> TechnicalReport:
        """使用 LLM 进行技术分析"""
        system_prompt = """你是一位专业的 A 股技术分析师。
基于提供的技术指标和市场数据，分析股票趋势并给出交易建议。

输出格式（JSON）：
{
    "trend": "bullish" | "bearish" | "neutral",
    "signal": "buy" | "sell" | "hold",
    "confidence": 0.0 ~ 1.0,
    "summary": "分析摘要"
}"""

        user_prompt = f"""股票代码: {security_id}

市场快照:
{self._format_snapshot(snapshot)}

最近 K 线:
{self._format_klines(klines)}

技术指标:
{json.dumps(indicators, ensure_ascii=False, indent=2)}

请分析技术面趋势并给出交易建议。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            result = json.loads(response)
            return TechnicalReport(
                trend=result.get("trend", "neutral"),
                signal=result.get("signal", "hold"),
                confidence=result.get("confidence", 0.5),
                indicators=indicators,
                summary=result.get("summary", ""),
            )
        except Exception as e:
            print(f"[TechnicalAnalyst] LLM 分析失败: {e}")
            return self._analyze_with_rules(indicators, snapshot)

    def _ema(self, data: list[float], period: int) -> float:
        """计算指数移动平均"""
        if len(data) < period:
            return data[-1] if data else 0
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _rsi(self, data: list[float], period: int = 14) -> float:
        """计算 RSI"""
        if len(data) < period + 1:
            return 50.0

        deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _bollinger_bands(
        self, data: list[float], period: int = 20, std_dev: float = 2.0
    ) -> dict:
        """计算布林带"""
        if len(data) < period:
            return {}

        recent = data[-period:]
        middle = sum(recent) / period
        variance = sum((x - middle) ** 2 for x in recent) / period
        std = variance ** 0.5

        return {
            "upper": middle + std_dev * std,
            "middle": middle,
            "lower": middle - std_dev * std,
        }


class FundamentalAnalystAgent(BaseAgent):
    """基本面分析师"""

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="FundamentalAnalyst")

    async def run(self, security_id: str, **kwargs) -> FundamentalReport:
        """运行基本面分析"""
        # Phase 1: 简化实现，返回默认值
        return FundamentalReport(
            valuation="fair",
            quality="moderate",
            growth="moderate",
            risk_factors=[],
            summary="基本面分析（Phase 1 简化实现）",
        )


class SentimentAnalystAgent(BaseAgent):
    """情绪面分析师"""

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="SentimentAnalyst")

    async def run(self, security_id: str, **kwargs) -> SentimentReport:
        """运行情绪面分析"""
        # Phase 1: 简化实现，返回默认值
        return SentimentReport(
            money_flow="neutral",
            institutional_activity="neutral",
            retail_sentiment="neutral",
            summary="情绪面分析（Phase 1 简化实现）",
        )


class NewsAnalystAgent(BaseAgent):
    """新闻分析师"""

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="NewsAnalyst")

    async def run(self, security_id: str, **kwargs) -> NewsReport:
        """运行新闻分析"""
        # Phase 1: 简化实现，返回默认值
        return NewsReport(
            events=[],
            sentiment_score=0.0,
            summary="新闻分析（Phase 1 简化实现）",
        )
