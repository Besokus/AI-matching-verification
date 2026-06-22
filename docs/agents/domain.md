# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`RTAuction/CONTEXT.md`** — 撮合引擎领域术语表（OrderBook、撮合、集合竞价等核心概念）
- **`docs/PRD_AI_Trading_Agent_Platform.md`** — AI Agent 平台完整 PRD（架构、Agent 角色、数据流、设计决策）
- **`RTAuction/CLAUDE.md`** — 撮合引擎构建、架构和性能特征
- **`docs/adr/`** — 架构决策记录（待积累）

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront.

## File structure

本项目为单上下文仓库，但包含两个逻辑子系统：

```
Matching Engine/
├── CLAUDE.md                    ← 项目总览 + Agent 平台指南
├── RTAuction/
│   ├── CLAUDE.md                ← 撮合引擎专用指南
│   ├── AGENTS.md                ← 撮合引擎开发规则
│   └── CONTEXT.md               ← 撮合引擎领域术语表
├── agent/                       ← AI Agent 平台（待建）
├── docs/
│   ├── PRD_AI_Trading_Agent_Platform.md
│   └── adr/                     ← 架构决策记录
└── docs/agents/                 ← 本目录
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `RTAuction/CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 — but worth reopening because…_
