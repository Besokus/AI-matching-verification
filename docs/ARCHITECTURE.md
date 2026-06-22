# TradeAgent-Veritas 技术架构文档

> **版本：** v1.0
> **日期：** 2026-06-22
> **参考：** TradingAgents (LangGraph StateGraph), TradingAgents-CN (A 股适配)

---

## 一、架构总览

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户入口层                                │
│   CLI (Phase 1)  │  Python SDK  │  Web Dashboard (Phase 2)     │
└─────────────────────────────┼───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 编排层                                │
│                   LangGraph StateGraph                          │
│                                                                 │
│   ┌─────────────────────────────────────────────┐              │
│   │  Analyst Team (并行)                         │              │
│   │  TechnicalAnalyst  │  FundamentalAnalyst    │              │
│   │  SentimentAnalyst  │  NewsAnalyst           │              │
│   └───────────────────┼─────────────────────────┘              │
│                       ↓                                         │
│   ┌─────────────────────────────────────────────┐              │
│   │  Researcher Team (多轮辩论)                  │              │
│   │  BullResearcher  ←→  BearResearcher         │              │
│   └───────────────────┼─────────────────────────┘              │
│                       ↓                                         │
│   ┌─────────────────────────────────────────────┐              │
│   │  TraderAgent → OrderDecision                 │              │
│   └───────────────────┼─────────────────────────┘              │
│                       ↓                                         │
│   ┌─────────────────────────────────────────────┐              │
│   │  RiskControlAgent → Approved/Rejected        │              │
│   └───────────────────┼─────────────────────────┘              │
└───────────────────────┼─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                      数据服务层                                  │
│                                                                 │
│   MarketDataProvider  │  FundamentalProvider  │  NewsProvider   │
│   (AKShare 分钟线/日线)  (AKShare 财务)        (AKShare 新闻)   │
└───────────────────────┼─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                      仿真引擎层                                  │
│                                                                 │
│   ┌─────────────────────┐   ┌─────────────────────┐            │
│   │  TickSynthesizer    │   │  gRPC Bridge         │            │
│   │  分钟线→合成tick     │   │  Python ↔ C++        │            │
│   └─────────────────────┘   └─────────────────────┘            │
│                                                                 │
│   ┌─────────────────────┐   ┌─────────────────────┐            │
│   │  Engine A (历史回放) │   │  Engine B (Agent仿真)│            │
│   │  RTAuction C++17    │   │  RTAuction C++17     │            │
│   └─────────────────────┘   └─────────────────────┘            │
└───────────────────────┼─────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                      绩效统计层                                  │
│   PnL / Sharpe / MaxDD / 交易明细 / Markdown 报告               │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **StateGraph 驱动** | 所有 Agent 编排通过 LangGraph StateGraph，节点可独立测试 |
| **双 LLM 分层** | `deep_think_llm`（辩论/决策）+ `quick_think_llm`（分析/信号）|
| **确定性风控** | 风控用纯规则引擎，不依赖 LLM |
| **两本 OrderBook** | 引擎 A 看真实历史，引擎 B 跑 Agent 仿真，互不干扰 |
| **数据源统一** | AKShare 作为唯一数据源，所有数据通过 Provider 抽象层获取 |

---

## 二、目录结构

```
agent/
├── __init__.py
├── main.py                    # CLI 入口
├── config.py                  # 全局配置（LLM、数据源、风控参数）
│
├── graph/                     # LangGraph 编排层
│   ├── __init__.py
│   ├── trading_graph.py       # 主图：TradingGraph 类
│   ├── state.py               # State 定义（AgentState, DebateState, ...）
│   ├── nodes/                 # 图节点实现
│   │   ├── __init__.py
│   │   ├── analyst_nodes.py   # 分析师节点（技术/基本面/情绪/新闻）
│   │   ├── researcher_nodes.py# 研究员节点（看多/看空辩论）
│   │   ├── trader_node.py     # 交易员节点
│   │   └── risk_node.py       # 风控节点
│   ├── edges/                 # 条件路由
│   │   ├── __init__.py
│   │   └── conditional.py     # 辩论轮次、风控决策路由
│   └── tools/                 # Agent 工具（数据获取）
│       ├── __init__.py
│       ├── market_tools.py    # 行情工具（K线、深度、成交）
│       ├── fundamental_tools.py# 基本面工具（财报、估值）
│       ├── sentiment_tools.py # 情绪工具（资金流、龙虎榜）
│       └── news_tools.py      # 新闻工具（公告、新闻）
│
├── agents/                    # Agent 定义（Prompt + LLM 配置）
│   ├── __init__.py
│   ├── base.py                # 基类：BaseAgent
│   ├── analyst.py             # 分析师 Agent（4 种）
│   ├── researcher.py          # 研究员 Agent（看多/看空）
│   ├── trader.py              # 交易员 Agent
│   └── risk_control.py        # 风控 Agent（规则引擎）
│
├── synthesizer/               # Tick 合成器
│   ├── __init__.py
│   ├── tick_synthesizer.py    # 主类：TickSynthesizer
│   ├── price_path.py          # 价格路径生成（布朗运动）
│   ├── order_generator.py     # 订单事件生成
│   └── validator.py           # 合成质量验证
│
├── bridge/                    # gRPC 通信层
│   ├── __init__.py
│   ├── proto/                 # Protobuf 定义
│   │   ├── matching_engine.proto
│   │   ├── matching_engine_pb2.py
│   │   └── matching_engine_pb2_grpc.py
│   ├── engine_client.py       # Python 侧 gRPC client
│   └── engine_service.py      # C++ 侧 gRPC server（在 RTAuction 中实现）
│
├── data/                      # 数据层
│   ├── __init__.py
│   ├── providers/             # 数据 Provider
│   │   ├── __init__.py
│   │   ├── base.py            # 基类：BaseProvider
│   │   ├── akshare_provider.py# AKShare 数据接入
│   │   └── cache.py           # 本地缓存（SQLite）
│   └── models/                # 数据模型
│       ├── __init__.py
│       ├── market.py          # MarketSnapshot, KLine, Trade
│       ├── order.py           # OrderDecision, ApprovedOrder
│       └── report.py          # AnalysisReport, DebateResult
│
├── risk/                      # 风控规则引擎
│   ├── __init__.py
│   ├── rules.py               # 风控规则定义
│   ├── engine.py              # 规则引擎执行器
│   └── config.py              # 风控参数配置
│
├── performance/               # 绩效统计
│   ├── __init__.py
│   ├── calculator.py          # PnL/Sharpe/MaxDD 计算
│   ├── collector.py           # 交易记录收集
│   └── reporter.py            # 报告生成（Markdown）
│
├── llm/                       # LLM 客户端层
│   ├── __init__.py
│   ├── client.py              # LLM 客户端工厂
│   ├── providers/             # 各 LLM Provider 适配
│   │   ├── __init__.py
│   │   ├── deepseek.py
│   │   ├── qwen.py
│   │   └── openai_compat.py
│   └── prompts/               # Prompt 模板
│       ├── __init__.py
│       ├── analyst_prompts.py
│       ├── researcher_prompts.py
│       └── trader_prompts.py
│
└── tests/                     # 测试
    ├── test_synthesizer/
    ├── test_agents/
    ├── test_risk/
    ├── test_bridge/
    └── test_integration/
```

---

## 三、LangGraph StateGraph 设计

### 3.1 State 定义

```python
# agent/graph/state.py

from typing import TypedDict, Annotated, Sequence
from operator import add
from dataclasses import dataclass, field

@dataclass
class TechnicalReport:
    trend: str                    # "bullish" | "bearish" | "neutral"
    signal: str                   # "buy" | "sell" | "hold"
    confidence: float             # 0.0 ~ 1.0
    indicators: dict              # {"macd": ..., "rsi": ..., "kdj": ...}
    summary: str

@dataclass
class FundamentalReport:
    valuation: str                # "undervalued" | "fair" | "overvalued"
    quality: str                  # "strong" | "moderate" | "weak"
    growth: str                   # "high" | "moderate" | "low"
    risk_factors: list[str]
    summary: str

@dataclass
class SentimentReport:
    money_flow: str               # "inflow" | "outflow" | "neutral"
    institutional_activity: str   # "active_buy" | "active_sell" | "neutral"
    retail_sentiment: str         # "bullish" | "bearish" | "neutral"
    summary: str

@dataclass
class NewsReport:
    events: list[dict]            # [{"title": ..., "impact": ...}]
    sentiment_score: float        # -1.0 ~ 1.0
    summary: str

@dataclass
class DebateState:
    bull_argument: str
    bear_argument: str
    bull_history: list[str] = field(default_factory=list)
    bear_history: list[str] = field(default_factory=list)
    round: int = 0
    consensus: str = ""
    confidence: float = 0.0

@dataclass
class OrderDecision:
    action: str                   # "BUY" | "SELL" | "HOLD"
    security_id: str
    price: float
    volume: int
    order_type: str               # "LIMIT" | "MARKET"
    confidence: float
    reason: str

@dataclass
class RiskDecision:
    approved: bool
    reason: str
    adjusted_order: OrderDecision | None = None

class AgentState(TypedDict):
    # 标的信息
    security_id: str
    security_name: str
    trade_date: str

    # 市场数据（从引擎 A 获取）
    market_snapshot: dict          # MarketSnapshot 序列化
    recent_klines: list[dict]      # 最近 N 根分钟 K 线
    daily_klines: list[dict]       # 日 K 线

    # 分析师报告（并行生成，用 Annotated[list, add] 累加）
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
    position: dict                 # {"volume": 0, "avg_price": 0, "pnl": 0}

    # 最终输出
    final_decision: str            # "EXECUTE" | "REJECT" | "HOLD"

    # 性能追踪
    node_timings: dict             # {"analyst_technical": 1.23, ...}
```

### 3.2 图拓扑

```python
# agent/graph/trading_graph.py

from langgraph.graph import StateGraph, END

class TradingGraph:
    """主编排图，参考 TradingAgents 的 GraphSetup 模式"""

    def __init__(self, config):
        self.config = config
        self.llm_deep = create_llm(config.deep_think_llm)
        self.llm_quick = create_llm(config.quick_think_llm)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        # ── 分析师层（并行） ──
        graph.add_node("technical_analyst", self._technical_analyst_node)
        graph.add_node("fundamental_analyst", self._fundamental_analyst_node)
        graph.add_node("sentiment_analyst", self._sentiment_analyst_node)
        graph.add_node("news_analyst", self._news_analyst_node)

        # ── 汇总分析师输出 ──
        graph.add_node("analyst_aggregator", self._analyst_aggregator)

        # ── 研究员辩论层 ──
        graph.add_node("bull_researcher", self._bull_researcher_node)
        graph.add_node("bear_researcher", self._bear_researcher_node)
        graph.add_node("debate_judge", self._debate_judge_node)

        # ── 交易员层 ──
        graph.add_node("trader", self._trader_node)

        # ── 风控层 ──
        graph.add_node("risk_control", self._risk_control_node)

        # ── 边定义 ──
        # 分析师 → 汇总（并行 fan-in）
        graph.add_edge("technical_analyst", "analyst_aggregator")
        graph.add_edge("fundamental_analyst", "analyst_aggregator")
        graph.add_edge("sentiment_analyst", "analyst_aggregator")
        graph.add_edge("news_analyst", "analyst_aggregator")

        # 汇总 → 辩论
        graph.add_edge("analyst_aggregator", "bull_researcher")
        graph.add_edge("bull_researcher", "bear_researcher")

        # 辩论 → 条件路由（继续辩论 or 结束）
        graph.add_conditional_edges(
            "bear_researcher",
            self._should_continue_debate,
            {
                "continue": "bull_researcher",
                "end": "debate_judge"
            }
        )

        # 辩论结束 → 交易员 → 风控 → END
        graph.add_edge("debate_judge", "trader")
        graph.add_edge("trader", "risk_control")

        # 风控 → 条件路由（执行 or 拒绝）
        graph.add_conditional_edges(
            "risk_control",
            self._risk_decision,
            {
                "execute": END,
                "reject": END,
                "adjust": "trader"  # 风控要求调整后重新决策
            }
        )

        # 入口
        graph.set_entry_point("technical_analyst")

        return graph

    def _should_continue_debate(self, state: AgentState) -> str:
        """辩论轮次控制"""
        if state["debate_state"].round >= self.config.max_debate_rounds:
            return "end"
        return "continue"

    def _risk_decision(self, state: AgentState) -> str:
        """风控决策路由"""
        risk = state["risk_decision"]
        if risk.approved:
            return "execute"
        if risk.adjusted_order:
            return "adjust"
        return "reject"
```

### 3.3 节点实现示例

```python
# agent/graph/nodes/analyst_nodes.py

async def technical_analyst_node(state: AgentState) -> dict:
    """技术面分析师节点"""
    from ..agents.analyst import TechnicalAnalystAgent

    agent = TechnicalAnalystAgent(llm=self.llm_quick)

    # 获取市场数据
    snapshot = state["market_snapshot"]
    klines = state["recent_klines"]

    # 调用 Agent
    report = await agent.analyze(snapshot, klines)

    return {"technical_report": report}

async def trader_node(state: AgentState) -> dict:
    """交易员节点"""
    from ..agents.trader import TraderAgent

    agent = TraderAgent(llm=self.llm_deep)

    decision = await agent.decide(
        technical=state["technical_report"],
        fundamental=state["fundamental_report"],
        sentiment=state["sentiment_report"],
        news=state["news_report"],
        debate=state["debate_state"],
        position=state["position"],
        snapshot=state["market_snapshot"],
    )

    return {"order_decision": decision}
```

---

## 四、数据流详解

### 4.1 回测主循环

```python
# agent/main.py（简化伪代码）

async def run_backtest(security_id: str, start_date: str, end_date: str):
    # 1. 获取 AKShare 分钟线数据
    klines = akshare_provider.get_minute_klines(security_id, start_date, end_date)

    # 2. Tick 合成：分钟线 → 合成逐笔事件
    tick_events = TickSynthesizer().synthesize(klines)

    # 3. 初始化两本 OrderBook（通过 gRPC 连接 C++ 引擎）
    engine_a = EngineClient("localhost:50051")  # 历史回放
    engine_b = EngineClient("localhost:50052")  # Agent 仿真

    # 4. 初始化 Agent 图
    graph = TradingGraph(config)

    # 5. 回放主循环
    current_minute = None
    for event in tick_events:
        # 喂事件到两个引擎
        engine_a.feed_event(event)
        engine_b.feed_event(event)

        # 每分钟边界触发 Agent 决策
        if event.timestamp.minute != current_minute:
            current_minute = event.timestamp.minute

            # 等引擎排空
            engine_a.wait_drain()
            engine_b.wait_drain()

            # 从引擎 A 获取快照（真实历史）
            snapshot = engine_a.get_snapshot(security_id)

            # 构建 Agent 输入状态
            state = build_agent_state(
                security_id=security_id,
                snapshot=snapshot,
                klines=get_recent_klines(klines, current_minute),
                position=get_current_position(),
            )

            # 运行 Agent 图
            result = await graph.ainvoke(state)

            # 如果决策通过风控，注入引擎 B
            if result["final_decision"] == "EXECUTE":
                order = result["risk_decision"].adjusted_order or result["order_decision"]
                engine_b.submit_agent_order(order)

    # 6. 绩效统计
    trades = engine_b.get_agent_trades()
    report = PerformanceReporter.generate(trades)
    print(report)
```

### 4.2 数据获取流程

```
Agent 节点
    ↓ 调用工具
market_tools.get_stock_data(security_id, period)
    ↓
AKShareProvider.get_klines(security_id, period)
    ↓ 检查缓存
SQLiteCache.get(key) → 命中则返回
    ↓ 未命中
ak.stock_zh_a_hist(symbol=security_id, period="1m")
    ↓ 写入缓存
SQLiteCache.set(key, data)
    ↓ 返回
返回 KLine[] 给 Agent
```

---

## 五、LLM 客户端层

### 5.1 多 Provider 支持

参考 TradingAgents-CN 的多 Provider 架构：

```python
# agent/llm/client.py

def create_llm(provider: str, model: str, **kwargs):
    """LLM 工厂函数"""
    providers = {
        "deepseek": DeepSeekClient,
        "qwen": QwenClient,
        "openai": OpenAICompatClient,
        "ollama": OpenAICompatClient,
    }
    client_cls = providers.get(provider, OpenAICompatClient)
    return client_cls(model=model, **kwargs)
```

### 5.2 双 LLM 策略

| 用途 | LLM | 理由 |
|------|-----|------|
| 分析师（快速推理） | Qwen-2.5-72B / DeepSeek-V3 | 低延迟、中文好 |
| 辩论/决策（深度推理） | DeepSeek-R1 / Qwen-2.5-Max | 推理能力强 |
| 信号处理 | Qwen-2.5-7B (本地) | 零成本、低延迟 |

---

## 六、风控规则引擎

### 6.1 三层架构

```python
# agent/risk/engine.py

class RiskEngine:
    """确定性风控引擎，不使用 LLM"""

    def __init__(self, config: RiskConfig):
        self.rules = [
            # Layer 1: Agent 规则
            MaxPositionRule(config.max_position_pct),
            ConcentrationRule(config.max_concentration_pct),
            LimitPriceRule(),
            MinVolumeRule(config.min_volume),
            FrequencyRule(config.max_trades_per_minute),

            # Layer 2: 系统熔断
            DailyLossRule(config.max_daily_loss_pct),
            ConsecutiveLossRule(config.max_consecutive_losses),
            ConfidenceRule(config.min_confidence),
            DataAnomalyRule(),

            # Layer 3: 人工审批
            LargeTradeRule(config.large_trade_pct),
        ]

    def check(self, decision: OrderDecision, context: RiskContext) -> RiskDecision:
        for rule in self.rules:
            result = rule.evaluate(decision, context)
            if not result.passed:
                return RiskDecision(
                    approved=False,
                    reason=f"[{rule.name}] {result.reason}",
                    adjusted_order=result.adjusted_order,
                )
        return RiskDecision(approved=True, reason="All rules passed")
```

---

## 七、gRPC 通信协议

### 7.1 Proto 定义

```protobuf
// agent/bridge/proto/matching_engine.proto

syntax = "proto3";
package matching_engine;

service MatchingEngineService {
    // 历史事件回放
    rpc FeedOrderEvent(OrderEvent) returns (EventResult);
    rpc FeedTradeEvent(TradeEvent) returns (EventResult);

    // Agent 订单操作
    rpc SubmitAgentOrder(AgentOrder) returns (OrderResult);
    rpc CancelAgentOrder(CancelRequest) returns (CancelResult);

    // 市场状态查询
    rpc GetMarketSnapshot(SnapshotRequest) returns (MarketSnapshotProto);
    rpc GetAgentTrades(TradeQuery) returns (TradeList);

    // 引擎控制
    rpc WaitForDrain(DrainRequest) returns (DrainResult);
    rpc GetEngineStatus(StatusRequest) returns (EngineStatus);
}

message OrderEvent {
    string security_id = 1;
    int64 order_id = 2;
    double price = 3;
    int32 volume = 4;
    int32 side = 5;          // 0=buy, 1=sell
    int32 order_type = 6;    // 0=limit, 1=market
    int64 timestamp_ns = 7;
    int32 event_kind = 8;    // 0=add, 1=cancel, 2=modify
}

message AgentOrder {
    string security_id = 1;
    double price = 2;
    int32 volume = 3;
    int32 side = 4;
    int32 order_type = 5;
    string agent_id = 6;
    string reason = 7;
}

message MarketSnapshotProto {
    string security_id = 1;
    repeated PriceLevel bids = 2;  // 10 档买盘
    repeated PriceLevel asks = 3;  // 10 档卖盘
    double last_price = 4;
    int64 timestamp_ns = 5;
}

message PriceLevel {
    double price = 1;
    int32 volume = 2;
}
```

---

## 八、配置管理

### 8.1 配置结构

```python
# agent/config.py

from dataclasses import dataclass, field

@dataclass
class LLMConfig:
    provider: str = "deepseek"
    deep_think_model: str = "deepseek-reasoner"
    quick_think_model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096

@dataclass
class RiskConfig:
    max_position_pct: float = 0.10      # 单笔最大仓位 10%
    max_concentration_pct: float = 0.30 # 单股集中度 30%
    max_daily_loss_pct: float = 0.05    # 单日最大亏损 5%
    max_consecutive_losses: int = 3     # 连续亏损次数
    min_confidence: float = 0.3         # 最低置信度
    large_trade_pct: float = 0.05       # 大额交易阈值 5%
    max_trades_per_minute: int = 3      # 每分钟最大交易次数
    min_volume: int = 100               # 最小交易量（1 手）

@dataclass
class SynthesizerConfig:
    volatility: float = 0.02            # 布朗运动波动率
    cancel_ratio: float = 0.15          # 撤单比例
    order_arrival_lambda: float = 5.0   # 订单到达泊松分布参数

@dataclass
class BacktestConfig:
    security_id: str = "600519"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000.0
    max_debate_rounds: int = 2
    decision_interval: str = "1m"       # Agent 决策频率

@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    synthesizer: SynthesizerConfig = field(default_factory=SynthesizerConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    engine_a_host: str = "localhost:50051"
    engine_b_host: str = "localhost:50052"
```

---

## 九、与 TradingAgents 的关键差异

| 维度 | TradingAgents | 本项目 |
|------|--------------|--------|
| **回测引擎** | 假设成交（`price = current_price`） | 真实 OrderBook 撮合（0.002ms） |
| **数据源** | Yahoo Finance（美股） | AKShare（A 股，唯一数据源） |
| **数据粒度** | 日线 | 合成逐笔（从分钟线生成） |
| **订单类型** | 市价单 | 限价单、撤单、集合竞价 |
| **风控** | LLM 辩论（Risky/Safe/Neutral） | 确定性规则引擎（三层） |
| **LLM** | OpenAI 为主 | DeepSeek/Qwen（中文优化） |
| **语言** | English | 中文 |
| **UI** | CLI / Streamlit | CLI (Phase 1) / FastAPI+Vue (Phase 2) |

### 借鉴 TradingAgents 的部分

1. **LangGraph StateGraph 编排模式** — 节点化、可测试、可 checkpoint
2. **双 LLM 分层策略** — deep_think vs quick_think
3. **多轮辩论机制** — Bull/Bear Researcher
4. **分析师并行执行** — fan-out/fan-in 模式
5. **记忆/反思系统** — 历史决策注入（Phase 2）

### 借鉴 TradingAgents-CN 的部分

1. **多 Provider LLM 支持** — DeepSeek/Qwen/Ollama 统一接口
2. **AKShare 数据接入** — A 股分钟线、财务、资金流
3. **中文 Prompt 优化** — 金融术语中文表达
4. **进度回调机制** — 实时输出分析进度

---

## 十、开发阶段与里程碑

### Phase 1: MVP（~16 天）

| 阶段 | 里程碑 | 验收标准 |
|------|--------|---------|
| T0 | Tick 合成器 | 分钟线 → 合成 tick → 引擎回放 → OHLCV 一致 |
| T1 | gRPC 通信层 | Python 能调用 C++ 引擎的全部 API |
| T2 | Agent 框架 | LangGraph 图编译通过，节点可独立运行 |
| T3 | 撮合引擎集成 | 双实例运行，Agent 订单注入引擎 B |
| T4 | 绩效统计 | 输出 PnL/Sharpe/MaxDD/交易明细 |
| T5 | 端到端集成 | 单股票 1 天回测跑通 |

### Phase 2: 增强（~20 天）

- 完整 4 分析师 + 辩论机制
- Web Dashboard（FastAPI + Vue 3）
- 记忆/反思系统
- 多股票回测
- 策略对比功能
