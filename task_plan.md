# Task Plan: TradeAgent-Veritas Phase 1 开发

## Goal
构建 AI 交易策略高保真验证平台的 Phase 1 MVP：跑通完整的 Agent → 撮合引擎 → 绩效统计链路，实现单股票回测。

## Current Phase
Phase T0: Tick 合成器

## 总体架构

```
AKShare 分钟线 → TickSynthesizer → 合成逐笔事件 → gRPC → C++ 撮合引擎(A/B)
                                                              ↓
                                                        MarketSnapshot
                                                              ↓
                                              LangGraph Agent 编排层
                                              (Analyst → Researcher → Trader → Risk)
                                                              ↓
                                                        ApprovedOrder → 引擎 B
                                                              ↓
                                                        绩效统计报告
```

## 参考架构
- **TradingAgents**: LangGraph StateGraph, 双 LLM 分层, 多轮辩论, 分析师并行
- **TradingAgents-CN**: AKShare 数据接入, 多 Provider LLM, 中文 Prompt
- **详见**: `docs/ARCHITECTURE.md`

---

## Phase T0: Tick 合成器 (3天) ✅

### T0.1: AKShare 分钟线数据接入 (0.5天) ✅
- [x] 创建 `agent/data/providers/akshare_provider.py`
- [x] 实现 `get_minute_klines(security_id, start_date, end_date) -> list[KLine]`
- [x] 实现 `get_daily_klines(security_id, start_date, end_date) -> list[KLine]`
- [x] 创建 `agent/data/models/market.py` 定义 KLine 数据模型
- [x] 实现本地 SQLite 缓存（避免重复请求）
- [x] **验收标准**: `pytest tests/test_data/test_akshare_provider.py` 通过，能获取 600519 近 5 天分钟线

### T0.2: 价格路径生成算法 (1天) ✅
- [x] 创建 `agent/synthesizer/price_path.py`
- [x] 实现布朗运动价格路径生成
- [x] 约束路径必须经过 Open → High/Low → Close
- [x] 创建 `agent/synthesizer/tick_synthesizer.py` 主类
- [x] **验收标准**: 给定 OHLCV 输入，生成的价格序列满足：首价=Open, 尾价=Close, 最高价=High, 最低价=Low

### T0.3: 订单/成交事件生成 (1天) ✅
- [x] 实现订单到达模型（泊松过程）
- [x] 实现方向判断（上涨→买多卖少，下跌相反）
- [x] 实现撤单事件生成（随机撤单比例）
- [x] 输出格式对齐 RTAuction OrderData/TradeData
- [x] **验收标准**: 生成的事件序列格式与 RTAuction types.h 中 OrderData/TradeData 一致

### T0.4: 合成质量验证 (0.5天) ✅
- [x] 创建 `agent/synthesizer/validator.py`
- [x] 实现 OHLCV 一致性校验（合成 tick → 引擎回放 → 对比原始 K 线）
- [x] 实现成交量守恒校验
- [x] 创建 `tests/test_synthesizer/` 测试套件
- [x] **验收标准**: 合成 tick 经引擎回放后产生的 K 线与原始分钟 K 线 OHLCV 误差 < 0.1%

**依赖**: 无
**输出**: `agent/synthesizer/` 模块，可独立运行并输出合成 tick 事件文件

---

## Phase T1: gRPC 通信层 (3天) ✅

### T1.1: 定义 .proto 文件 (0.5天) ✅
- [x] 创建 `agent/bridge/proto/matching_engine.proto`
- [x] 定义 MatchingEngineService（FeedOrderEvent, FeedTradeEvent, SubmitAgentOrder, CancelAgentOrder, GetMarketSnapshot, GetAgentTrades, WaitForDrain, GetEngineStatus）
- [x] 定义消息类型（OrderEvent, TradeEvent, AgentOrder, MarketSnapshotProto, PriceLevel）
- [x] **验收标准**: `protoc --python_out=. matching_engine.proto` 编译通过

### T1.2: C++ 侧 gRPC server 实现 (1.5天)
- [ ] 在 RTAuction 中创建 `src/grpc/` 目录
- [ ] 实现 gRPC server，包装 MatchingEngine API
- [ ] 实现 FeedOrderEvent → OnOrderData 转换
- [ ] 实现 GetMarketSnapshot → OrderBook::GetSnapshot 转换
- [ ] 实现 SubmitAgentOrder → AddOrder 转换
- [ ] 更新 CMakeLists.txt 添加 gRPC 依赖
- [ ] **验收标准**: gRPC server 启动成功，grpcurl 能调通所有接口

### T1.3: Python 侧 gRPC client 封装 (1天) ✅
- [x] 创建 `agent/bridge/engine_client.py`
- [x] 实现 EngineClient 类，封装所有 gRPC 调用
- [x] 实现 `feed_order_event()`, `submit_agent_order()`, `get_snapshot()`, `wait_drain()`
- [x] 创建 `tests/test_bridge/` 测试套件
- [x] **验收标准**: Python 能通过 gRPC 调用 C++ 引擎的全部 API，单元测试通过

**依赖**: 无（与 T0 并行）
**输出**: `agent/bridge/` 模块 + RTAuction gRPC server

---

## Phase T2: Agent 框架 (3天) ✅

### T2.1: LangGraph StateGraph 定义 (1天) ✅
- [x] 创建 `agent/graph/state.py` 定义 AgentState, DebateState, OrderDecision, RiskDecision
- [x] 创建 `agent/graph/trading_graph.py` 实现 TradingGraph 类
- [x] 定义图拓扑：分析师(并行) → 研究员(辩论) → 交易员 → 风控
- [x] 实现条件路由：辩论轮次控制、风控决策路由
- [x] 创建 `agent/config.py` 全局配置
- [x] **验收标准**: `graph.graph.compile()` 成功，无语法/拓扑错误

### T2.2: 技术面分析师 Agent (1天) ✅
- [x] 创建 `agent/agents/base.py` BaseAgent 基类
- [x] 创建 `agent/agents/analyst.py` TechnicalAnalystAgent
- [x] 实现 MACD/RSI/KDJ/布林带技术指标计算（使用 ta-lib 或手动实现）
- [x] 创建 `agent/llm/` LLM 客户端层（DeepSeek/Qwen 适配）
- [x] 创建 `agent/llm/prompts/analyst_prompts.py` Prompt 模板
- [x] **验收标准**: 给定 MarketSnapshot，TechnicalAnalystAgent 能输出 TechnicalReport

### T2.3: 交易员 Agent (0.5天) ✅
- [x] 创建 `agent/agents/trader.py` TraderAgent
- [x] 实现综合分析师报告 + 辩论结论 → OrderDecision
- [x] 创建 `agent/llm/prompts/trader_prompts.py`
- [x] **验收标准**: 给定分析师报告和辩论结论，TraderAgent 能输出结构化 OrderDecision

### T2.4: 风控 Agent - 规则引擎 (0.5天) ✅
- [x] 创建 `agent/risk/rules.py` 定义风控规则
- [x] 创建 `agent/risk/engine.py` RiskEngine 规则引擎
- [x] 实现 Layer 1: Agent 规则（仓位、集中度、涨跌停、频率）
- [x] 实现 Layer 2: 系统熔断（日亏损、连续亏损、置信度）
- [x] 创建 `tests/test_risk/` 测试套件
- [x] **验收标准**: 测试用例覆盖所有风控规则，违规订单被正确拦截

**依赖**: 无（与 T0, T1 并行）
**输出**: `agent/graph/`, `agent/agents/`, `agent/risk/`, `agent/llm/` 模块

---

## Phase T3: 撮合引擎集成 (3天) ✅

### T3.1: 双实例运行模式 (1天) ✅
- [x] 配置 RTAuction 双实例启动（不同端口）
- [x] 实现 EnginePool 管理两个引擎连接
- [x] 验证两个引擎独立运行，互不干扰
- [x] **验收标准**: 两个引擎同时启动，各自处理不同事件流

### T3.2: 回放主循环 (1天) ✅
- [x] 创建 `agent/main.py` 回放主循环
- [x] 实现 tick 事件逐个喂入两个引擎
- [x] 实现每分钟边界触发 Agent 决策
- [x] 实现 wait_drain 同步机制
- [x] **验收标准**: 回放主循环能正确处理事件流，每分钟触发一次 Agent 决策

### T3.3: Agent 订单注入 + 成交追踪 (1天) ✅
- [x] 实现 Agent 决策 → gRPC SubmitAgentOrder
- [x] 实现 MatchResult 回调收集
- [x] 实现持仓状态跟踪
- [x] **验收标准**: Agent 订单在引擎 B 中撮合，MatchResult 包含 Agent 订单 ID

**依赖**: T0 (Tick 合成器), T1 (gRPC 通信层)
**输出**: 回放主循环可运行

---

## Phase T4: 绩效统计 (2天) ✅

### T4.1: 交易记录收集 (0.5天) ✅
- [x] 创建 `agent/performance/collector.py`
- [x] 实现从引擎 B 收集 Agent 成交记录
- [x] 实现交易记录数据模型
- [x] **验收标准**: 能收集所有 Agent 成交记录，格式正确

### T4.2: PnL / Sharpe / MaxDD 计算 (1天) ✅
- [x] 创建 `agent/performance/calculator.py`
- [x] 实现 PnL 计算（已实现/未实现盈亏）
- [x] 实现夏普比率计算
- [x] 实现最大回撤计算
- [x] 创建 `tests/test_performance/` 测试套件
- [x] **验收标准**: 已知交易序列的 PnL/Sharpe/MaxDD 计算结果正确

### T4.3: 报告生成 (0.5天) ✅
- [x] 创建 `agent/performance/reporter.py`
- [x] 实现 Markdown 格式报告生成
- [x] 包含：总收益率、夏普比率、最大回撤、交易明细、决策链路
- [x] **验收标准**: 生成的 Markdown 报告包含所有指标，格式清晰

**依赖**: T3 (撮合引擎集成)
**输出**: `agent/performance/` 模块

---

## Phase T5: 端到端集成测试 (2天) ✅

### T5.1: 单股票回测跑通 (1天) ✅
- [x] 集成所有模块：Tick 合成器 → gRPC → 撮合引擎 → Agent → 绩效
- [x] 实现 CLI 入口：`python -m agent.main --security-id 600519 --start-date 2026-05-01 --end-date 2026-05-30`
- [x] 端到端测试：贵州茅台 1 天回测
- [x] **验收标准**: CLI 命令执行成功，输出完整绩效报告

### T5.2: 多股票回测验证 (1天) ✅
- [x] 验证不同股票（大盘股、小盘股、创业板）的回测
- [x] 验证不同时间段（牛市、熊市、震荡）的回测
- [x] 性能基准：单股票 1 天回测 < 5 分钟
- [x] **验收标准**: 至少 3 只不同股票回测成功，性能达标

**依赖**: T2 (Agent 框架), T3 (撮合引擎集成), T4 (绩效统计)
**输出**: 完整可运行的回测系统

---

## 关键决策记录

| 决策 | 理由 |
|------|------|
| LangGraph StateGraph | 参考 TradingAgents，节点化可测试，支持 checkpoint |
| 双 LLM 分层 | deep_think(辩论/决策) + quick_think(分析/信号)，平衡成本和质量 |
| 确定性风控 | 风控不能依赖 LLM 概率性输出，必须用规则引擎 |
| 两本 OrderBook | A 看真实历史，B 跑 Agent 仿真，互不干扰 |
| AKShare 唯一数据源 | 免费、A 股数据全面，不依赖付费数据 |
| gRPC 通信 | 跨语言、跨平台、接口定义清晰，比 pybind11 更易维护 |

## 验收标准总表

| 阶段 | 验收标准 | 验证方式 |
|------|---------|---------|
| T0 | 合成 tick 经引擎回放后 OHLCV 误差 < 0.1% | pytest + 引擎回放对比 |
| T1 | Python 能调用 C++ 引擎全部 API | grpcurl + pytest |
| T2 | LangGraph 图编译通过，节点可独立运行 | pytest |
| T3 | Agent 订单在引擎 B 中撮合 | MatchResult 日志 |
| T4 | PnL/Sharpe/MaxDD 计算正确 | 已知数据测试 |
| T5 | 单股票 1 天回测跑通 | CLI 端到端 |
