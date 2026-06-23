"""分析师 Agent 实现

包含：
- TechnicalAnalyst: 技术面分析师
- FundamentalAnalyst: 基本面分析师
- SentimentAnalyst: 情绪面分析师
- NewsAnalyst: 新闻分析师
"""

import json
from typing import Any

import numpy as np

from .base import BaseAgent
from ..graph.state import TechnicalReport, FundamentalReport, SentimentReport, NewsReport

_RSI_OVERSOLD = 30
_RSI_OVERBOUGHT = 70


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

        # 单次遍历提取所有列
        closes, highs, lows, volumes = [], [], [], []
        for k in klines:
            closes.append(k.get("close", 0))
            highs.append(k.get("high", 0))
            lows.append(k.get("low", 0))
            volumes.append(k.get("volume", 0))

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
                "signal": "oversold" if rsi < _RSI_OVERSOLD else "overbought" if rsi > _RSI_OVERBOUGHT else "neutral",
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

        recent = np.array(data[-period:])
        middle = recent.mean()
        std = recent.std()

        return {
            "upper": middle + std_dev * std,
            "middle": middle,
            "lower": middle - std_dev * std,
        }


class FundamentalAnalystAgent(BaseAgent):
    """基本面分析师

    基于 AKShare 财务数据分析股票估值、质量和成长性。
    """

    def __init__(self, llm: Any = None, data_provider: Any = None):
        super().__init__(llm, name="FundamentalAnalyst")
        self.data_provider = data_provider

    async def run(self, security_id: str, **kwargs) -> FundamentalReport:
        """运行基本面分析

        Args:
            security_id: 股票代码

        Returns:
            FundamentalReport
        """
        # 获取财务数据
        financial_data = {}
        if self.data_provider:
            try:
                financial_data = self.data_provider.get_financial_indicator(security_id)
            except Exception as e:
                print(f"[FundamentalAnalyst] 获取财务数据失败: {e}")

        # 如果有 LLM，使用 LLM 分析
        if self.llm and financial_data:
            return await self._analyze_with_llm(security_id, financial_data)

        # 否则使用规则判断
        return self._analyze_with_rules(security_id, financial_data)

    def _analyze_with_rules(self, security_id: str, data: dict) -> FundamentalReport:
        """使用规则进行基本面分析"""
        risk_factors = []

        # 估值维度
        pe = data.get("pe_ttm", data.get("pe", 0))
        pb = data.get("pb", 0)

        if pe > 0:
            if pe < 15:
                valuation = "undervalued"
            elif pe < 30:
                valuation = "fair"
            else:
                valuation = "overvalued"
                risk_factors.append(f"PE={pe:.1f} 偏高")
        else:
            valuation = "fair"
            if pe < 0:
                risk_factors.append("PE 为负（亏损）")

        if pb > 10:
            risk_factors.append(f"PB={pb:.1f} 过高")

        # 质量维度
        roe = data.get("roe", 0)
        gross_margin = data.get("gross_margin", 0)
        debt_ratio = data.get("debt_ratio", 0)

        if roe >= 20:
            quality = "strong"
        elif roe >= 10:
            quality = "moderate"
        else:
            quality = "weak"
            if roe > 0:
                risk_factors.append(f"ROE={roe:.1f}% 偏低")

        if gross_margin < 10:
            risk_factors.append(f"毛利率={gross_margin:.1f}% 过低")

        if debt_ratio > 70:
            risk_factors.append(f"资产负债率={debt_ratio:.1f}% 过高")

        # 成长维度
        revenue_growth = data.get("revenue_growth", 0)
        net_profit_growth = data.get("net_profit_growth", 0)

        if revenue_growth > 20:
            growth = "high"
        elif revenue_growth > 5:
            growth = "moderate"
        else:
            growth = "low"
            if revenue_growth < 0:
                risk_factors.append(f"营收增长={revenue_growth:.1f}% 为负")

        if net_profit_growth < -10:
            risk_factors.append(f"净利润增长={net_profit_growth:.1f}% 大幅下滑")

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"估值: {valuation} (PE={pe:.1f}, PB={pb:.1f})")
        summary_parts.append(f"质量: {quality} (ROE={roe:.1f}%, 毛利率={gross_margin:.1f}%)")
        summary_parts.append(f"成长: {growth} (营收增长={revenue_growth:.1f}%, 净利润增长={net_profit_growth:.1f}%)")
        if risk_factors:
            summary_parts.append(f"风险: {', '.join(risk_factors)}")

        return FundamentalReport(
            valuation=valuation,
            quality=quality,
            growth=growth,
            risk_factors=risk_factors,
            summary="; ".join(summary_parts),
        )

    async def _analyze_with_llm(self, security_id: str, data: dict) -> FundamentalReport:
        """使用 LLM 进行基本面分析"""
        system_prompt = """你是一位专业的 A 股基本面分析师。
基于提供的财务数据分析股票的估值、质量和成长性。

输出格式（JSON）：
{
    "valuation": "undervalued" | "fair" | "overvalued",
    "quality": "strong" | "moderate" | "weak",
    "growth": "high" | "moderate" | "low",
    "risk_factors": ["风险因子1", "风险因子2"],
    "summary": "分析摘要"
}"""

        user_prompt = f"""股票代码: {security_id}

财务指标:
- PE(TTM): {data.get('pe_ttm', 'N/A')}
- PB: {data.get('pb', 'N/A')}
- ROE: {data.get('roe', 'N/A')}%
- 毛利率: {data.get('gross_margin', 'N/A')}%
- 资产负债率: {data.get('debt_ratio', 'N/A')}%
- 营收增长率: {data.get('revenue_growth', 'N/A')}%
- 净利润增长率: {data.get('net_profit_growth', 'N/A')}%
- 股息率: {data.get('dv_ttm', 'N/A')}%
- 总市值: {data.get('total_mv', 'N/A')} 万元

请分析基本面并给出投资建议。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            result = json.loads(response)
            return FundamentalReport(
                valuation=result.get("valuation", "fair"),
                quality=result.get("quality", "moderate"),
                growth=result.get("growth", "moderate"),
                risk_factors=result.get("risk_factors", []),
                summary=result.get("summary", ""),
            )
        except Exception as e:
            print(f"[FundamentalAnalyst] LLM 分析失败: {e}")
            return self._analyze_with_rules(security_id, data)


class SentimentAnalystAgent(BaseAgent):
    """情绪面分析师

    基于 AKShare 资金流向数据分析市场情绪。
    """

    def __init__(self, llm: Any = None, data_provider: Any = None):
        super().__init__(llm, name="SentimentAnalyst")
        self.data_provider = data_provider

    async def run(self, security_id: str, **kwargs) -> SentimentReport:
        """运行情绪面分析

        Args:
            security_id: 股票代码

        Returns:
            SentimentReport
        """
        # 获取资金流向数据
        money_flow = {}
        if self.data_provider:
            try:
                money_flow = self.data_provider.get_money_flow(security_id)
            except Exception as e:
                print(f"[SentimentAnalyst] 获取资金流向失败: {e}")

        # 如果有 LLM，使用 LLM 分析
        if self.llm and money_flow:
            return await self._analyze_with_llm(security_id, money_flow)

        # 否则使用规则判断
        return self._analyze_with_rules(security_id, money_flow)

    def _analyze_with_rules(self, security_id: str, data: dict) -> SentimentReport:
        """使用规则进行情绪面分析"""
        # 资金流向判断
        main_inflow = data.get("main_net_inflow", 0)
        total_amount = data.get("total_amount", 0)

        # 主力资金方向
        if total_amount > 0:
            inflow_pct = (main_inflow / total_amount) * 100
            if inflow_pct > 5:
                money_flow = "inflow"
            elif inflow_pct < -5:
                money_flow = "outflow"
            else:
                money_flow = "neutral"
        else:
            money_flow = "neutral"
            inflow_pct = 0

        # 机构动向（基于大单占比）
        main_net_inflow_pct = data.get("main_net_inflow_pct", 0)
        if main_net_inflow_pct >= 10:
            institutional_activity = "active_buy"
        elif main_net_inflow_pct <= -10:
            institutional_activity = "active_sell"
        else:
            institutional_activity = "neutral"

        # 散户情绪（与主力方向相反）
        retail_net_inflow_pct = data.get("retail_net_inflow_pct", 0)
        if retail_net_inflow_pct >= 5:
            retail_sentiment = "bullish"
        elif retail_net_inflow_pct <= -5:
            retail_sentiment = "bearish"
        else:
            retail_sentiment = "neutral"

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"主力净流入: {main_inflow/10000:.1f}万 ({inflow_pct:.1f}%)")
        summary_parts.append(f"资金方向: {money_flow}")
        summary_parts.append(f"机构动向: {institutional_activity}")

        return SentimentReport(
            money_flow=money_flow,
            institutional_activity=institutional_activity,
            retail_sentiment=retail_sentiment,
            summary="; ".join(summary_parts),
        )

    async def _analyze_with_llm(self, security_id: str, data: dict) -> SentimentReport:
        """使用 LLM 进行情绪面分析"""
        system_prompt = """你是一位专业的 A 股情绪面分析师。
基于资金流向数据分析市场情绪。

输出格式（JSON）：
{
    "money_flow": "inflow" | "outflow" | "neutral",
    "institutional_activity": "active_buy" | "active_sell" | "neutral",
    "retail_sentiment": "bullish" | "bearish" | "neutral",
    "summary": "分析摘要"
}"""

        user_prompt = f"""股票代码: {security_id}

资金流向数据:
- 主力净流入: {data.get('main_net_inflow', 0)/10000:.1f} 万元
- 散户净流入: {data.get('retail_net_inflow', 0)/10000:.1f} 万元
- 总成交额: {data.get('total_amount', 0)/10000:.1f} 万元
- 主力净流入占比: {data.get('main_net_inflow_pct', 0):.1f}%
- 散户净流入占比: {data.get('retail_net_inflow_pct', 0):.1f}%

请分析市场情绪。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            result = json.loads(response)
            return SentimentReport(
                money_flow=result.get("money_flow", "neutral"),
                institutional_activity=result.get("institutional_activity", "neutral"),
                retail_sentiment=result.get("retail_sentiment", "neutral"),
                summary=result.get("summary", ""),
            )
        except Exception as e:
            print(f"[SentimentAnalyst] LLM 分析失败: {e}")
            return self._analyze_with_rules(security_id, data)


class NewsAnalystAgent(BaseAgent):
    """新闻分析师

    基于 AKShare 新闻数据分析新闻事件和情绪。
    """

    def __init__(self, llm: Any = None, data_provider: Any = None):
        super().__init__(llm, name="NewsAnalyst")
        self.data_provider = data_provider

    async def run(self, security_id: str, **kwargs) -> NewsReport:
        """运行新闻分析

        Args:
            security_id: 股票代码

        Returns:
            NewsReport
        """
        # 获取新闻数据
        news_list = []
        if self.data_provider:
            try:
                news_list = self.data_provider.get_news(security_id)
            except Exception as e:
                print(f"[NewsAnalyst] 获取新闻失败: {e}")

        # 如果有 LLM，使用 LLM 分析
        if self.llm and news_list:
            return await self._analyze_with_llm(security_id, news_list)

        # 否则使用规则判断
        return self._analyze_with_rules(security_id, news_list)

    def _analyze_with_rules(self, security_id: str, news_list: list[dict]) -> NewsReport:
        """使用规则进行新闻分析"""
        if not news_list:
            return NewsReport(
                events=[],
                sentiment_score=0.0,
                summary="暂无相关新闻",
            )

        # 单次遍历：提取事件 + 情绪计算 + 重大事件识别
        events = []
        total_sentiment = 0.0
        major_events = []
        recent = news_list[:10]
        for news in recent:
            sentiment = news.get("sentiment", 0)
            events.append({
                "title": news.get("title", ""),
                "source": news.get("source", ""),
                "publish_time": news.get("publish_time", ""),
                "impact": "positive" if sentiment > 0 else "negative" if sentiment < 0 else "neutral",
            })
            total_sentiment += sentiment
            if abs(sentiment) >= 0.6:
                major_events.append(news.get("title", ""))

        # 计算平均情绪得分
        avg_sentiment = total_sentiment / len(recent) if recent else 0.0

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"新闻数量: {len(news_list)} 条")
        summary_parts.append(f"情绪得分: {avg_sentiment:.2f}")

        if avg_sentiment > 0.3:
            summary_parts.append("整体偏正面")
        elif avg_sentiment < -0.3:
            summary_parts.append("整体偏负面")
        else:
            summary_parts.append("整体中性")

        if major_events:
            summary_parts.append(f"重大事件: {major_events[0]}")

        return NewsReport(
            events=events,
            sentiment_score=avg_sentiment,
            summary="; ".join(summary_parts),
        )

    async def _analyze_with_llm(self, security_id: str, news_list: list[dict]) -> NewsReport:
        """使用 LLM 进行新闻分析"""
        system_prompt = """你是一位专业的 A 股新闻分析师。
基于新闻数据分析市场事件和情绪。

输出格式（JSON）：
{
    "events": [{"title": "标题", "impact": "positive/negative/neutral"}],
    "sentiment_score": -1.0 ~ 1.0,
    "summary": "分析摘要"
}"""

        # 格式化新闻列表
        news_text = ""
        for i, news in enumerate(news_list[:10], 1):
            news_text += f"{i}. [{news.get('source', '')}] {news.get('title', '')}\n"
            news_text += f"   时间: {news.get('publish_time', '')}\n"
            news_text += f"   情绪: {news.get('sentiment', 0):.2f}\n\n"

        user_prompt = f"""股票代码: {security_id}

最近新闻:
{news_text}

请分析新闻事件和市场情绪。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            result = json.loads(response)
            return NewsReport(
                events=result.get("events", []),
                sentiment_score=result.get("sentiment_score", 0.0),
                summary=result.get("summary", ""),
            )
        except Exception as e:
            print(f"[NewsAnalyst] LLM 分析失败: {e}")
            return self._analyze_with_rules(security_id, news_list)
