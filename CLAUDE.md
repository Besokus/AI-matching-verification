# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI 交易策略高保真验证平台（TradeAgent-Veritas）。多 Agent 协作做 A 股交易决策，对接自研 C++17 低延迟撮合引擎作为仿真回测内核。

核心差异点：用真实 OrderBook 撮合（0.002ms）替代简单假设成交，Agent 的订单经历限价单排队、部分成交、撤单、集合竞价等真实市场微观结构。

**PRD 文档：** `docs/PRD_AI_Trading_Agent_Platform.md`

## Project Structure

```
Matching Engine/
├── RTAuction/              ← C++ 撮合引擎（独立子项目，有自己的 CLAUDE.md/AGENTS.md）
│   ├── include/            ← 公共头文件（MatchingEngine, OrderBook, types.h）
│   ├── src/                ← 实现（matching_engine/, order_book/, market_data/, replay/）
│   ├── config/             ← 配置文件和参数参考
│   ├── tests/              ← 单元测试
│   └── CLAUDE.md           ← 撮合引擎专用指南（构建、架构、性能特征）
├── agent/                  ← Python AI Agent 平台（待建）
│   ├── agents/             ← Agent 角色定义（分析师、研究员、交易员、风控）
│   ├── graph/              ← LangGraph StateGraph 编排
│   ├── synthesizer/        ← Tick 合成器（分钟线 → 合成逐笔事件）
│   ├── bridge/             ← gRPC 通信层（Python ↔ C++）
│   ├── risk/               ← 风控规则引擎
│   └── performance/        ← 绩效统计（PnL/Sharpe/MaxDD）
├── docs/                   ← 项目文档
│   └── PRD_AI_Trading_Agent_Platform.md
└── CLAUDE.md               ← 本文件
```

## Build & Run

### 撮合引擎（C++）

```bash
cd RTAuction

# 构建
mkdir -p build && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# 运行测试
cd build && ctest --output-on-failure

# 离线回放
INPUT_FILE=/data/.../tickdata_20260424.txt TRADE_DATE=20260424 bash run-offline-rebuild.sh

# 实盘（需要行情网络）
bash run.sh
```

构建目标：`rtauction`（实盘）、`rtauction_replay`、`rtauction_live_rebuild_test`（离线回放）

### AI Agent 平台（Python）

```bash
cd agent

# 安装依赖
pip install -r requirements.txt

# 运行回测
python -m agent.main --security-id 600519 --start-date 2026-05-01 --end-date 2026-05-30

# 运行单个 Agent 测试
python -m pytest tests/test_technical_analyst.py -v
```

## Architecture

### 两本 OrderBook 设计

回测时运行两个撮合引擎实例：

- **实例 A（历史回放）：** 只回放合成历史事件，Agent 从此处观察 MarketSnapshot
- **实例 B（Agent 仿真）：** 回放历史事件 + 接收 Agent 订单，用于绩效统计

如果只用一本 OrderBook，Agent 的订单会改变市场状态，导致后续历史事件撮合偏离真实。

### 数据流

```
AKShare 分钟线 → Tick 合成器 → 合成逐笔事件 → 撮合引擎 A/B
                                                    ↓
                                              MarketSnapshot → Agent 决策 → 订单注入引擎 B
                                                    ↓
                                              MatchResult → 绩效统计
```

### Agent 决策频率

- **撮合引擎：** tick-by-tick（逐笔，~34,000 事件/秒）
- **Agent 决策：** 分钟级（每分钟一次 LLM 推理）
- **数据源：** AKShare 免费分钟 K 线（唯一数据源，无付费 Level 2 tick 数据）

### Tick 合成器

由于无法获取真实逐笔行情，用算法从分钟 K 线生成合成逐笔事件：
- 布朗运动价格路径（约束经过 OHLCV）
- 订单到达模型（上涨时买多卖少，下跌时相反）
- 输出格式兼容 RTAuction OrderData/TradeData

### 撮合引擎核心 API

RTAuction 撮合引擎对外暴露的关键接口（详见 `RTAuction/CLAUDE.md`）：

| 接口 | 说明 |
|------|------|
| `MatchingEngine::OnOrderData(OrderData)` | 喂入订单事件 |
| `MatchingEngine::OnTradeData(TradeData)` | 喂入成交事件 |
| `OrderBook::GetSnapshot(MarketSnapshot&)` | 获取 10 档深度快照 |
| `OrderBook::AddOrder(Order, TradingPhase)` | 添加订单并撮合 |
| `OrderBook::CancelOrder(OrderID)` | 撤单 |
| `MatchingEngine::SetMatchResultCallback(fn)` | 注册成交回调 |

## Agent Skills

### Issue tracker

GitHub Issues（`gh` CLI）。详见 `docs/agents/issue-tracker.md`。

### Triage labels

使用默认 triage 标签名（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）。详见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文仓库。领域文档在 `RTAuction/CONTEXT.md`（撮合引擎术语表）。详见 `docs/agents/domain.md`。
