"""LangGraph StateGraph 主编排图

参考 TradingAgents 的 GraphSetup 模式，实现：
- 分析师并行执行
- 研究员多轮辩论
- 交易员综合决策
- 风控规则检查
"""

import time
from typing import Any

from .state import (
    AgentState, TechnicalReport, FundamentalReport, SentimentReport, NewsReport,
    DebateState, OrderDecision, RiskDecision,
)
from ..agents.analyst import (
    TechnicalAnalystAgent, FundamentalAnalystAgent,
    SentimentAnalystAgent, NewsAnalystAgent,
)
from ..agents.trader import TraderAgent
from ..risk.engine import RiskEngine, RiskConfig


class TradingGraph:
    """主编排图

    使用 LangGraph StateGraph 编排 Agent 流程。
    """

    def __init__(
        self,
        llm_deep: Any = None,
        llm_quick: Any = None,
        risk_config: RiskConfig | None = None,
        max_debate_rounds: int = 2,
    ):
        """
        Args:
            llm_deep: 深度思考 LLM（用于辩论、决策）
            llm_quick: 快速思考 LLM（用于分析）
            risk_config: 风控配置
            max_debate_rounds: 最大辩论轮次
        """
        self.llm_deep = llm_deep
        self.llm_quick = llm_quick
        self.max_debate_rounds = max_debate_rounds

        # 初始化 Agent
        self.technical_analyst = TechnicalAnalystAgent(llm_quick)
        self.fundamental_analyst = FundamentalAnalystAgent(llm_quick)
        self.sentiment_analyst = SentimentAnalystAgent(llm_quick)
        self.news_analyst = NewsAnalystAgent(llm_quick)
        self.trader = TraderAgent(llm_deep)

        # 初始化风控引擎
        self.risk_engine = RiskEngine(risk_config)

    async def run(self, state: AgentState) -> AgentState:
        """运行 Agent 编排图

        Args:
            state: 初始状态

        Returns:
            更新后的状态
        """
        start_time = time.time()
        node_timings = {}

        # Step 1: 并行运行分析师
        tech_start = time.time()
        technical_report = await self.technical_analyst.run(
            security_id=state["security_id"],
            snapshot=state["market_snapshot"],
            klines=state["recent_klines"],
        )
        node_timings["technical_analyst"] = time.time() - tech_start

        fund_start = time.time()
        fundamental_report = await self.fundamental_analyst.run(
            security_id=state["security_id"],
        )
        node_timings["fundamental_analyst"] = time.time() - fund_start

        sent_start = time.time()
        sentiment_report = await self.sentiment_analyst.run(
            security_id=state["security_id"],
        )
        node_timings["sentiment_analyst"] = time.time() - sent_start

        news_start = time.time()
        news_report = await self.news_analyst.run(
            security_id=state["security_id"],
        )
        node_timings["news_analyst"] = time.time() - news_start

        # Step 2: 辩论（简化：直接使用分析师结论）
        debate_start = time.time()
        debate_state = self._run_debate(
            technical_report, fundamental_report,
            sentiment_report, news_report,
        )
        node_timings["debate"] = time.time() - debate_start

        # Step 3: 交易员决策
        trader_start = time.time()
        order_decision = await self.trader.run(
            security_id=state["security_id"],
            snapshot=state["market_snapshot"],
            technical=technical_report,
            fundamental=fundamental_report,
            sentiment=sentiment_report,
            news=news_report,
            debate=debate_state,
            position=state.get("position", {}),
        )
        node_timings["trader"] = time.time() - trader_start

        # Step 4: 风控检查
        risk_start = time.time()
        risk_context = {
            "total_capital": 1_000_000,  # TODO: 从配置获取
            "position": state.get("position", {}),
            "daily_pnl": state.get("position", {}).get("pnl", 0),
            "consecutive_losses": 0,  # TODO: 从历史获取
            "recent_trades_count": 0,  # TODO: 从历史获取
            "last_close": state["market_snapshot"].get("last_price", 0),
        }
        risk_decision = self.risk_engine.check(order_decision, risk_context)
        node_timings["risk_control"] = time.time() - risk_start

        # Step 5: 确定最终决策
        if risk_decision.approved:
            final_decision = "EXECUTE"
        else:
            final_decision = "REJECT"

        # 更新状态
        total_time = time.time() - start_time
        node_timings["total"] = total_time

        return {
            **state,
            "technical_report": technical_report,
            "fundamental_report": fundamental_report,
            "sentiment_report": sentiment_report,
            "news_report": news_report,
            "debate_state": debate_state,
            "order_decision": order_decision,
            "risk_decision": risk_decision,
            "final_decision": final_decision,
            "node_timings": node_timings,
        }

    def _run_debate(
        self,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
    ) -> DebateState:
        """运行辩论（简化实现）

        Phase 1: 简化为直接汇总分析师结论
        Phase 2: 实现完整的 Bull/Bear 辩论
        """
        # 汇总分析师信号
        signals = []
        if technical.signal == "buy":
            signals.append(1)
        elif technical.signal == "sell":
            signals.append(-1)
        else:
            signals.append(0)

        if fundamental.valuation == "undervalued":
            signals.append(1)
        elif fundamental.valuation == "overvalued":
            signals.append(-1)
        else:
            signals.append(0)

        if sentiment.money_flow == "inflow":
            signals.append(1)
        elif sentiment.money_flow == "outflow":
            signals.append(-1)
        else:
            signals.append(0)

        avg_signal = sum(signals) / len(signals) if signals else 0

        if avg_signal > 0.3:
            consensus = "偏多"
            confidence = min(0.9, avg_signal)
            bull_arg = f"技术面{technical.signal}，基本面{fundamental.valuation}，资金{sentiment.money_flow}"
            bear_arg = "存在回调风险"
        elif avg_signal < -0.3:
            consensus = "偏空"
            confidence = min(0.9, abs(avg_signal))
            bull_arg = "存在反弹机会"
            bear_arg = f"技术面{technical.signal}，基本面{fundamental.valuation}，资金{sentiment.money_flow}"
        else:
            consensus = "中性"
            confidence = 0.5
            bull_arg = "多空信号混杂"
            bear_arg = "多空信号混杂"

        return DebateState(
            bull_argument=bull_arg,
            bear_argument=bear_arg,
            bull_history=[bull_arg],
            bear_history=[bear_arg],
            round=1,
            consensus=consensus,
            confidence=confidence,
        )
