"""LangGraph StateGraph 主编排图

参考 TradingAgents 的 GraphSetup 模式，实现：
- 分析师并行执行
- 研究员多轮辩论
- 交易员综合决策
- 风控规则检查
"""

import asyncio
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
from ..agents.researcher import BullResearcher, BearResearcher, DebateModerator
from ..agents.trader import TraderAgent
from ..risk.engine import RiskEngine, RiskConfig


_CONSENSUS_THRESHOLD = 0.3  # 辩论共识阈值


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
        data_provider: Any = None,
    ):
        """
        Args:
            llm_deep: 深度思考 LLM（用于辩论、决策）
            llm_quick: 快速思考 LLM（用于分析）
            risk_config: 风控配置
            max_debate_rounds: 最大辩论轮次
            data_provider: 数据 Provider（AKShareProvider）
        """
        self.llm_deep = llm_deep
        self.llm_quick = llm_quick
        self.max_debate_rounds = max_debate_rounds

        # 初始化 Agent
        self.technical_analyst = TechnicalAnalystAgent(llm_quick)
        self.fundamental_analyst = FundamentalAnalystAgent(llm_quick, data_provider)
        self.sentiment_analyst = SentimentAnalystAgent(llm_quick, data_provider)
        self.news_analyst = NewsAnalystAgent(llm_quick, data_provider)
        self.trader = TraderAgent(llm_deep)

        # 初始化研究员和辩论主持人
        self.bull_researcher = BullResearcher(llm_deep)
        self.bear_researcher = BearResearcher(llm_deep)
        self.debate_moderator = DebateModerator(
            self.bull_researcher,
            self.bear_researcher,
            max_rounds=max_debate_rounds,
        )

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
        analyst_start = time.time()
        technical_report, fundamental_report, sentiment_report, news_report = await asyncio.gather(
            self.technical_analyst.run(
                security_id=state["security_id"],
                snapshot=state["market_snapshot"],
                klines=state["recent_klines"],
            ),
            self.fundamental_analyst.run(security_id=state["security_id"]),
            self.sentiment_analyst.run(security_id=state["security_id"]),
            self.news_analyst.run(security_id=state["security_id"]),
        )
        node_timings["analysts"] = time.time() - analyst_start

        # Step 2: Bull/Bear 多轮辩论
        debate_start = time.time()
        debate_state = await self._run_debate(
            state["security_id"],
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
        position = state.get("position", {})
        risk_context = {
            "total_capital": state.get("total_capital", 1_000_000),
            "position": position,
            "daily_pnl": position.get("pnl", 0),
            "consecutive_losses": state.get("consecutive_losses", 0),
            "recent_trades_count": state.get("recent_trades_count", 0),
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

    async def _run_debate(
        self,
        security_id: str,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        news: NewsReport,
    ) -> DebateState:
        """运行 Bull/Bear 多轮辩论

        Args:
            security_id: 股票代码
            technical: 技术面报告
            fundamental: 基本面报告
            sentiment: 情绪面报告
            news: 新闻报告

        Returns:
            DebateState
        """
        return await self.debate_moderator.debate(
            security_id, technical, fundamental, sentiment, news,
        )
