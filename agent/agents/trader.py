"""交易员 Agent

综合分析师报告和辩论结论，输出具体交易决策。
"""

import json
from typing import Any

from .base import BaseAgent
from ..graph.state import (
    TechnicalReport, FundamentalReport, SentimentReport, NewsReport,
    DebateState, OrderDecision,
)


class TraderAgent(BaseAgent):
    """交易员 Agent

    综合所有分析师报告和辩论结论，输出 OrderDecision。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="Trader")

    async def run(
        self,
        security_id: str,
        snapshot: dict,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        debate: DebateState,
        position: dict,
        **kwargs,
    ) -> OrderDecision:
        """运行交易决策

        Args:
            security_id: 股票代码
            snapshot: 市场快照
            technical: 技术面报告
            fundamental: 基本面报告
            sentiment: 情绪面报告
            news: 新闻报告
            debate: 辩论结论
            position: 当前持仓

        Returns:
            OrderDecision
        """
        if self.llm:
            return await self._decide_with_llm(
                security_id, snapshot, technical, fundamental,
                sentiment, news, debate, position,
            )

        return self._decide_with_rules(
            security_id, snapshot, technical, fundamental,
            sentiment, news, debate, position,
        )

    def _decide_with_rules(
        self,
        security_id: str,
        snapshot: dict,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        debate: DebateState,
        position: dict,
    ) -> OrderDecision:
        """使用规则进行交易决策"""
        # 计算综合得分
        score = 0.0
        reasons = []

        # 技术面权重 40%
        tech_score = self._score_technical(technical)
        score += tech_score * 0.4
        reasons.append(f"技术面: {technical.signal} (得分 {tech_score:.2f})")

        # 辩论结论权重 30%
        debate_score = self._score_debate(debate)
        score += debate_score * 0.3
        reasons.append(f"辩论结论: {debate.consensus} (得分 {debate_score:.2f})")

        # 基本面权重 20%
        fund_score = self._score_fundamental(fundamental)
        score += fund_score * 0.2
        reasons.append(f"基本面: {fundamental.valuation} (得分 {fund_score:.2f})")

        # 情绪面权重 10%
        sent_score = self._score_sentiment(sentiment)
        score += sent_score * 0.1
        reasons.append(f"情绪面: {sentiment.money_flow} (得分 {sent_score:.2f})")

        # 决策
        last_price = snapshot.get("last_price", 0)
        current_volume = position.get("volume", 0)

        if score > 0.15 and current_volume == 0:
            # 买入（按 20% 仓位限制计算，取整到 100 股）
            action = "BUY"
            max_amount = 200_000
            if last_price > 0:
                volume = int(max_amount / last_price / 100) * 100
                volume = max(100, volume)
            else:
                volume = 100
            confidence = min(0.9, score)
        elif score < -0.15 and current_volume > 0:
            # 卖出
            action = "SELL"
            volume = current_volume
            confidence = min(0.9, abs(score))
        else:
            # 持有
            action = "HOLD"
            volume = 0
            confidence = 0.5

        return OrderDecision(
            action=action,
            security_id=security_id,
            price=last_price,
            volume=volume,
            order_type="LIMIT",
            confidence=confidence,
            reason="; ".join(reasons),
        )

    async def _decide_with_llm(
        self,
        security_id: str,
        snapshot: dict,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        debate: DebateState,
        position: dict,
    ) -> OrderDecision:
        """使用 LLM 进行交易决策"""
        system_prompt = """你是一位专业的 A 股交易员。
综合分析师报告和辩论结论，做出交易决策。

输出格式（JSON）：
{
    "action": "BUY" | "SELL" | "HOLD",
    "price": 价格,
    "volume": 数量（必须是100的倍数）,
    "confidence": 0.0 ~ 1.0,
    "reason": "决策理由"
}"""

        user_prompt = f"""股票代码: {security_id}

市场快照:
{self._format_snapshot(snapshot)}

当前持仓:
{json.dumps(position, ensure_ascii=False)}

分析师报告:
- 技术面: {technical.summary} (信号: {technical.signal}, 置信度: {technical.confidence})
- 基本面: {fundamental.summary} (估值: {fundamental.valuation})
- 情绪面: {sentiment.summary} (资金流: {sentiment.money_flow})
- 新闻: {news.summary} (情绪得分: {news.sentiment_score})

辩论结论:
- 看多论据: {debate.bull_argument}
- 看空论据: {debate.bear_argument}
- 共识: {debate.consensus}
- 置信度: {debate.confidence}

请做出交易决策。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            result = json.loads(response)
            return OrderDecision(
                action=result.get("action", "HOLD"),
                security_id=security_id,
                price=result.get("price", snapshot.get("last_price", 0)),
                volume=result.get("volume", 0),
                order_type="LIMIT",
                confidence=result.get("confidence", 0.5),
                reason=result.get("reason", ""),
            )
        except Exception as e:
            print(f"[Trader] LLM 决策失败: {e}")
            return self._decide_with_rules(
                security_id, snapshot, technical, fundamental,
                sentiment, news, debate, position,
            )

    def _score_technical(self, report: TechnicalReport) -> float:
        """技术面得分"""
        if report.signal == "buy":
            return report.confidence
        elif report.signal == "sell":
            return -report.confidence
        return 0.0

    def _score_fundamental(self, report: FundamentalReport) -> float:
        """基本面得分"""
        valuation_scores = {"undervalued": 0.5, "fair": 0.0, "overvalued": -0.5}
        return valuation_scores.get(report.valuation, 0.0)

    def _score_sentiment(self, report: SentimentReport) -> float:
        """情绪面得分"""
        flow_scores = {"inflow": 0.3, "outflow": -0.3, "neutral": 0.0}
        return flow_scores.get(report.money_flow, 0.0)

    def _score_debate(self, debate: DebateState) -> float:
        """辩论得分"""
        if "多" in debate.consensus or "bull" in debate.consensus.lower():
            return debate.confidence
        elif "空" in debate.consensus or "bear" in debate.consensus.lower():
            return -debate.confidence
        return 0.0
