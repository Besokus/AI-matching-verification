# Findings & Decisions

## Requirements
- 构建 AI 交易策略高保真验证平台 Phase 1 MVP
- 跑通完整链路：Agent → 撮合引擎 → 绩效统计
- 参考 TradingAgents/CN 架构，但用真实撮合引擎替代假设成交
- 使用 AKShare 免费数据源，不依赖付费 tick 数据
- 单股票回测作为 Phase 1 验收标准

## Research Findings

### TradingAgents 架构分析
- **编排方式**: LangGraph StateGraph，节点化设计
- **Agent 角色**: 4 分析师(并行) → 2 研究员(辩论) → 1 交易员 → 风控团队
- **LLM 策略**: 双 LLM 分层 - `deep_think_llm`(辩论/决策) + `quick_think_llm`(分析/信号)
- **数据源**: Yahoo Finance (美股)，日线级别
- **回测方式**: 假设全部成交（`price = current_price`），无真实撮合
- **关键模块**:
  - `trading_graph.py` - 主编排图
  - `default_config.py` - 配置管理
  - `GraphSetup` - 图拓扑构建
  - `ConditionalLogic` - 条件路由（辩论轮次控制）
  - `Propagator` - 状态初始化
  - `Reflector` - 事后反思（Phase 2）
  - `SignalProcessor` - 信号解析

### TradingAgents-CN 架构分析
- **A 股适配**: 集成 AKShare/Tushare/BaoStock 数据源
- **多 Provider LLM**: 支持 DeepSeek/Qwen/智谱AI/阿里百炼等 10+ Provider
- **混合模式**: quick_think 和 deep_think 可来自不同 Provider
- **前端**: FastAPI + Vue 3 + Element Plus
- **数据库**: MongoDB + Redis 双数据库
- **中文优化**: 所有 Prompt 和日志使用中文
- **记忆系统**: ChromaDB 向量数据库

### RTAuction 撮合引擎 API
- `OnOrderData(OrderData)` - 喂入订单事件
- `OnTradeData(TradeData)` - 喂入成交事件
- `OrderBook::GetSnapshot(MarketSnapshot&)` - 获取 10 档深度快照
- `AddOrder(Order, TradingPhase)` - 添加订单并撮合
- `CancelOrder(OrderID)` - 撤单
- `SetMatchResultCallback(fn)` - 注册成交回调
- **性能**: 0.002ms 单笔撮合，34K events/s 吞吐

## Technical Decisions

| 决策 | 理由 |
|------|------|
| LangGraph StateGraph | 参考 TradingAgents，节点化可测试，支持 checkpoint |
| 双 LLM 分层 | deep_think(辩论/决策) + quick_think(分析/信号) |
| 确定性风控 | 风控不能依赖 LLM 概率性输出，必须用规则引擎 |
| 两本 OrderBook | A 看真实历史，B 跑 Agent 仿真，互不干扰 |
| AKShare 唯一数据源 | 免费、A 股数据全面，不依赖付费数据 |
| gRPC 通信 | 跨语言、跨平台、接口定义清晰 |
| SQLite 缓存 | 轻量级本地缓存，避免重复请求 AKShare |
| DeepSeek/Qwen | 中文金融场景优化，成本低，可本地部署 |

## Issues Encountered
<!-- 暂无 -->

## Resources
- TradingAgents 源码: https://github.com/TauricResearch/TradingAgents
- TradingAgents-CN 源码: https://github.com/hsliuping/TradingAgents-CN
- LangGraph 文档: https://langchain-ai.github.io/langgraph/
- AKShare 文档: https://akshare.akfamily.xyz/
- RTAuction 撮合引擎: `RTAuction/CLAUDE.md`
- 项目 PRD: `docs/PRD_AI_Trading_Agent_Platform.md`
- 技术架构: `docs/ARCHITECTURE.md`
