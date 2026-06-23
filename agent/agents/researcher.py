"""研究员 Agent - Bull/Bear 多轮辩论

参考 TradingAgents 的辩论机制，实现：
- BullResearcher: 看多研究员，构建看多论据
- BearResearcher: 看空研究员，构建看空论据
- 多轮辩论：每轮引用对方论据进行反驳
"""

import json
from typing import Any

from .base import BaseAgent
from ..graph.state import (
    TechnicalReport, FundamentalReport, SentimentReport, NewsReport,
    DebateState,
)


class BullResearcher(BaseAgent):
    """看多研究员

    基于分析师报告构建看多论据，反驳看空观点。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="BullResearcher")

    async def run(self, **kwargs) -> Any:
        """运行（BaseAgent 接口兼容）"""
        return await self.argue(**kwargs)

    async def argue(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bear_argument: str = "",
        round_num: int = 1,
    ) -> str:
        """构建看多论据

        Args:
            security_id: 股票代码
            technical: 技术面报告
            fundamental: 基本面报告
            sentiment: 情绪面报告
            news: 新闻报告
            bear_argument: 看空论据（用于反驳）
            round_num: 当前轮次

        Returns:
            看多论据文本
        """
        if self.llm:
            return await self._argue_with_llm(
                security_id, technical, fundamental, sentiment, news,
                bear_argument, round_num,
            )

        return self._argue_with_rules(
            technical, fundamental, sentiment, news, bear_argument, round_num,
        )

    def _argue_with_rules(
        self,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bear_argument: str,
        round_num: int,
    ) -> str:
        """使用规则构建看多论据"""
        points = []

        # 技术面看多点
        if technical.signal == "buy":
            points.append(f"技术面发出买入信号（置信度 {technical.confidence:.0%}）")
        if technical.trend == "bullish":
            points.append("技术趋势看多")

        # 基本面看多点
        if fundamental.valuation == "undervalued":
            points.append("估值偏低，具备投资价值")
        if fundamental.quality == "strong":
            points.append("基本面质量优秀")
        if fundamental.growth == "high":
            points.append("成长性突出")

        # 情绪面看多点
        if sentiment.money_flow == "inflow":
            points.append("主力资金净流入")
        if sentiment.institutional_activity == "active_buy":
            points.append("机构积极买入")

        # 新闻面看多点
        if news.sentiment_score > 0.2:
            points.append("新闻情绪偏正面")

        # 反驳看空论据
        if bear_argument and round_num > 1:
            rebuttal = self._rebut(bear_argument)
            if rebuttal:
                points.append(f"反驳: {rebuttal}")

        if not points:
            points.append("当前无明显看多信号，但市场存在反弹机会")

        return "；".join(points)

    def _rebut(self, bear_argument: str) -> str:
        """反驳看空论据"""
        rebuttals = []
        if "高估" in bear_argument or "PE" in bear_argument:
            rebuttals.append("高 PE 可能反映市场对成长性的预期")
        if "资金流出" in bear_argument or "流出" in bear_argument:
            rebuttals.append("资金流出可能是短期调整，不改变长期趋势")
        if "利空" in bear_argument or "减持" in bear_argument:
            rebuttals.append("利空消息可能已被市场消化")
        if "技术" in bear_argument or "下跌" in bear_argument:
            rebuttals.append("技术面回调可能是买入机会")

        return "；".join(rebuttals) if rebuttals else ""

    async def _argue_with_llm(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bear_argument: str,
        round_num: int,
    ) -> str:
        """使用 LLM 构建看多论据"""
        system_prompt = """你是一位专业的 A 股看多研究员。
基于分析师报告构建有力的看多论据。
如果提供了看空论据，需要针对性反驳。

要求：
1. 论据要有数据支撑
2. 逻辑清晰，有说服力
3. 反驳要有理有据"""

        user_prompt = f"""股票代码: {security_id}
辩论轮次: 第 {round_num} 轮

分析师报告:
- 技术面: {technical.summary} (信号: {technical.signal}, 趋势: {technical.trend})
- 基本面: {fundamental.summary} (估值: {fundamental.valuation}, 质量: {fundamental.quality})
- 情绪面: {sentiment.summary} (资金: {sentiment.money_flow}, 机构: {sentiment.institutional_activity})
- 新闻: {news.summary} (情绪: {news.sentiment_score:.2f})

{"看空论据: " + bear_argument if bear_argument else "（第一轮，无看空论据）"}

请构建看多论据。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            return response
        except Exception as e:
            print(f"[BullResearcher] LLM 调用失败: {e}")
            return self._argue_with_rules(
                technical, fundamental, sentiment, news, bear_argument, round_num,
            )


class BearResearcher(BaseAgent):
    """看空研究员

    基于分析师报告构建看空论据，反驳看多观点。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm, name="BearResearcher")

    async def run(self, **kwargs) -> Any:
        """运行（BaseAgent 接口兼容）"""
        return await self.argue(**kwargs)

    async def argue(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bull_argument: str = "",
        round_num: int = 1,
    ) -> str:
        """构建看空论据

        Args:
            security_id: 股票代码
            technical: 技术面报告
            fundamental: 基本面报告
            sentiment: 情绪面报告
            news: 新闻报告
            bull_argument: 看多论据（用于反驳）
            round_num: 当前轮次

        Returns:
            看空论据文本
        """
        if self.llm:
            return await self._argue_with_llm(
                security_id, technical, fundamental, sentiment, news,
                bull_argument, round_num,
            )

        return self._argue_with_rules(
            technical, fundamental, sentiment, news, bull_argument, round_num,
        )

    def _argue_with_rules(
        self,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bull_argument: str,
        round_num: int,
    ) -> str:
        """使用规则构建看空论据"""
        points = []

        # 技术面看空点
        if technical.signal == "sell":
            points.append(f"技术面发出卖出信号（置信度 {technical.confidence:.0%}）")
        if technical.trend == "bearish":
            points.append("技术趋势看空")

        # 基本面看空点
        if fundamental.valuation == "overvalued":
            points.append("估值偏高，存在回调风险")
        if fundamental.quality == "weak":
            points.append("基本面质量较弱")
        if fundamental.growth == "low":
            points.append("成长性不足")
        if fundamental.risk_factors:
            points.append(f"风险因素: {fundamental.risk_factors[0]}")

        # 情绪面看空点
        if sentiment.money_flow == "outflow":
            points.append("主力资金净流出")
        if sentiment.institutional_activity == "active_sell":
            points.append("机构积极卖出")

        # 新闻面看空点
        if news.sentiment_score < -0.2:
            points.append("新闻情绪偏负面")

        # 反驳看多论据
        if bull_argument and round_num > 1:
            rebuttal = self._rebut(bull_argument)
            if rebuttal:
                points.append(f"反驳: {rebuttal}")

        if not points:
            points.append("当前无明显看空信号，但需警惕高位风险")

        return "；".join(points)

    def _rebut(self, bull_argument: str) -> str:
        """反驳看多论据"""
        rebuttals = []
        if "低估" in bull_argument or "价值" in bull_argument:
            rebuttals.append("低估值可能是市场对基本面恶化的合理定价")
        if "资金流入" in bull_argument or "流入" in bull_argument:
            rebuttals.append("资金流入可能是短期炒作，持续性存疑")
        if "利好" in bull_argument or "增长" in bull_argument:
            rebuttals.append("利好可能已被市场充分预期")
        if "技术" in bull_argument or "反弹" in bull_argument:
            rebuttals.append("技术反弹可能是下跌中继")

        return "；".join(rebuttals) if rebuttals else ""

    async def _argue_with_llm(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
        bull_argument: str,
        round_num: int,
    ) -> str:
        """使用 LLM 构建看空论据"""
        system_prompt = """你是一位专业的 A 股看空研究员。
基于分析师报告构建有力的看空论据。
如果提供了看多论据，需要针对性反驳。

要求：
1. 论据要有数据支撑
2. 逻辑清晰，有说服力
3. 反驳要有理有据"""

        user_prompt = f"""股票代码: {security_id}
辩论轮次: 第 {round_num} 轮

分析师报告:
- 技术面: {technical.summary} (信号: {technical.signal}, 趋势: {technical.trend})
- 基本面: {fundamental.summary} (估值: {fundamental.valuation}, 质量: {fundamental.quality})
- 情绪面: {sentiment.summary} (资金: {sentiment.money_flow}, 机构: {sentiment.institutional_activity})
- 新闻: {news.summary} (情绪: {news.sentiment_score:.2f})

{"看多论据: " + bull_argument if bull_argument else "（第一轮，无看多论据）"}

请构建看空论据。"""

        try:
            response = await self._call_llm(user_prompt, system_prompt)
            return response
        except Exception as e:
            print(f"[BearResearcher] LLM 调用失败: {e}")
            return self._argue_with_rules(
                technical, fundamental, sentiment, news, bull_argument, round_num,
            )


class DebateModerator:
    """辩论主持人

    管理 Bull/Bear 辩论流程，提取共识。
    """

    def __init__(
        self,
        bull: BullResearcher,
        bear: BearResearcher,
        max_rounds: int = 2,
        consensus_threshold: float = 0.7,
    ):
        """
        Args:
            bull: 看多研究员
            bear: 看空研究员
            max_rounds: 最大辩论轮次
            consensus_threshold: 共识阈值
        """
        self.bull = bull
        self.bear = bear
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold

    async def debate(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
    ) -> DebateState:
        """运行辩论

        Args:
            security_id: 股票代码
            technical: 技术面报告
            fundamental: 基本面报告
            sentiment: 情绪面报告
            news: 新闻报告

        Returns:
            DebateState
        """
        bull_history = []
        bear_history = []
        bull_argument = ""
        bear_argument = ""

        for round_num in range(1, self.max_rounds + 1):
            # Bull 发言
            bull_argument = await self.bull.argue(
                security_id, technical, fundamental, sentiment, news,
                bear_argument, round_num,
            )
            bull_history.append(bull_argument)

            # Bear 发言
            bear_argument = await self.bear.argue(
                security_id, technical, fundamental, sentiment, news,
                bull_argument, round_num,
            )
            bear_history.append(bear_argument)

            # 检查是否达成共识
            consensus, confidence = self._extract_consensus(
                bull_argument, bear_argument, technical, fundamental, sentiment,
            )

            if confidence >= self.consensus_threshold:
                return DebateState(
                    bull_argument=bull_argument,
                    bear_argument=bear_argument,
                    bull_history=bull_history,
                    bear_history=bear_history,
                    round=round_num,
                    consensus=consensus,
                    confidence=confidence,
                )

        # 达到最大轮次，提取最终共识
        consensus, confidence = self._extract_consensus(
            bull_argument, bear_argument, technical, fundamental, sentiment,
        )

        return DebateState(
            bull_argument=bull_argument,
            bear_argument=bear_argument,
            bull_history=bull_history,
            bear_history=bear_history,
            round=self.max_rounds,
            consensus=consensus,
            confidence=confidence,
        )

    def _extract_consensus(
        self,
        bull_argument: str,
        bear_argument: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
    ) -> tuple[str, float]:
        """从辩论中提取共识

        Returns:
            (共识方向, 置信度)
        """
        # 计算多空信号强度
        bull_score = 0.0
        bear_score = 0.0

        # 技术面
        if technical.signal == "buy":
            bull_score += technical.confidence
        elif technical.signal == "sell":
            bear_score += technical.confidence

        # 基本面
        if fundamental.valuation == "undervalued":
            bull_score += 0.3
        elif fundamental.valuation == "overvalued":
            bear_score += 0.3

        # 情绪面
        if sentiment.money_flow == "inflow":
            bull_score += 0.2
        elif sentiment.money_flow == "outflow":
            bear_score += 0.2

        # 辩论论据关键词
        bull_keywords = ["看多", "买入", "低估", "增长", "流入", "利好", "反弹"]
        bear_keywords = ["看空", "卖出", "高估", "下滑", "流出", "利空", "回调"]

        for kw in bull_keywords:
            if kw in bull_argument:
                bull_score += 0.1
        for kw in bear_keywords:
            if kw in bear_argument:
                bear_score += 0.1

        # 计算共识
        total = bull_score + bear_score
        if total == 0:
            return "中性", 0.5

        if bull_score > bear_score * 1.5:
            confidence = min(0.9, bull_score / total)
            return "偏多", confidence
        elif bear_score > bull_score * 1.5:
            confidence = min(0.9, bear_score / total)
            return "偏空", confidence
        else:
            return "中性", 0.5
