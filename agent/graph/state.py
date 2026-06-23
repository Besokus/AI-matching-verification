"""LangGraph State 定义

定义 Agent 编排层的状态结构，包括：
- AgentState: 主状态
- DebateState: 辩论状态
- OrderDecision: 订单决策
- RiskDecision: 风控决策
"""

from dataclasses import dataclass, field
from typing import TypedDict, Annotated
from operator import add


@dataclass
class TechnicalReport:
    """技术面分析报告"""
    trend: str = "neutral"  # "bullish" | "bearish" | "neutral"
    signal: str = "hold"  # "buy" | "sell" | "hold"
    confidence: float = 0.5  # 0.0 ~ 1.0
    indicators: dict = field(default_factory=dict)  # {"macd": ..., "rsi": ..., "kdj": ...}
    summary: str = ""


@dataclass
class FundamentalReport:
    """基本面分析报告"""
    valuation: str = "fair"  # "undervalued" | "fair" | "overvalued"
    quality: str = "moderate"  # "strong" | "moderate" | "weak"
    growth: str = "moderate"  # "high" | "moderate" | "low"
    risk_factors: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class SentimentReport:
    """情绪面分析报告"""
    money_flow: str = "neutral"  # "inflow" | "outflow" | "neutral"
    institutional_activity: str = "neutral"  # "active_buy" | "active_sell" | "neutral"
    retail_sentiment: str = "neutral"  # "bullish" | "bearish" | "neutral"
    summary: str = ""


@dataclass
class NewsReport:
    """新闻分析报告"""
    events: list[dict] = field(default_factory=list)  # [{"title": ..., "impact": ...}]
    sentiment_score: float = 0.0  # -1.0 ~ 1.0
    summary: str = ""


@dataclass
class DebateState:
    """辩论状态"""
    bull_argument: str = ""
    bear_argument: str = ""
    bull_history: list[str] = field(default_factory=list)
    bear_history: list[str] = field(default_factory=list)
    round: int = 0
    consensus: str = ""
    confidence: float = 0.0


@dataclass
class OrderDecision:
    """订单决策"""
    action: str = "HOLD"  # "BUY" | "SELL" | "HOLD"
    security_id: str = ""
    price: float = 0.0
    volume: int = 0
    order_type: str = "LIMIT"  # "LIMIT" | "MARKET"
    confidence: float = 0.0
    reason: str = ""


@dataclass
class RiskDecision:
    """风控决策"""
    approved: bool = False
    reason: str = ""
    adjusted_order: OrderDecision | None = None


class AgentState(TypedDict):
    """主状态定义

    这是 LangGraph StateGraph 的核心状态，所有节点共享。
    """
    # 标的信息
    security_id: str
    security_name: str
    trade_date: str

    # 市场数据（从引擎 A 获取）
    market_snapshot: dict  # MarketSnapshot 序列化
    recent_klines: list[dict]  # 最近 N 根分钟 K 线
    daily_klines: list[dict]  # 日 K 线

    # 分析师报告（并行生成）
    technical_report: TechnicalReport
    fundamental_report: FundamentalReport
    sentiment_report: SentimentReport
    news_report: NewsReport

    # 辩论状态
    debate_state: DebateState

    # 交易决策
    order_decision: OrderDecision

    # 风控决策
    risk_decision: RiskDecision

    # 持仓状态
    position: dict  # {"volume": 0, "avg_price": 0, "pnl": 0}

    # 最终输出
    final_decision: str  # "EXECUTE" | "REJECT" | "HOLD"

    # 性能追踪
    node_timings: dict  # {"analyst_technical": 1.23, ...}
