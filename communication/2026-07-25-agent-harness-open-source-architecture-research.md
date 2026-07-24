# Agent Harness 开源架构研究报告

日期：2026-07-25  
范围：只读研究，不修改产品代码  
目标：为 Narrative IDE 的右侧 Agent 控制面板和 sidecar harness 提供可落地的架构参考。

## 1. 结论先说

Narrative IDE 不需要把 Claude Code 或 Codex CLI 原样搬进来。应该借鉴它们共同的产品原则：

1. Agent 的每个动作都变成可观察、可审批、可恢复的事件。
2. 工具调用、文件变更、子任务、计划和人工决定使用统一协议，而不是各自维护一套 UI 状态。
3. 右侧面板展示“当前行动、原因摘要、工具结果、等待用户的决定、可回退的历史”，而不是只展示运行数量。
4. 业务数据仍然必须经过 proposal/review gate。Agent 可以提出搬运建议，但不能绕过 reviewer 直接污染 canonical World Model。

当前仓库的 durable runtime 已经具备较好的底座：SQLite WAL、run/attempt、lease/fence、事件 sequence、tool intent/result、checkpoint metadata、human decisions、DAG task 表、memory records、SSE/轮询回退，以及有限制的 ReAct/Self-Ask/Plan-Execute 模块。主要问题是这些能力还没有被统一成一个前端可理解的 Agent protocol；World Model 也仍存在多套分类事实来源。

## 2. 公开边界：Claude Code 与 Codex

### Claude Code

官方仓库是公开的：

- https://github.com/anthropics/claude-code
- https://code.claude.com/docs/en/overview
- https://docs.anthropic.com/en/docs/claude-code/getting-started
- https://github.com/anthropics/claude-agent-sdk-python
- https://github.com/anthropics/claude-agent-sdk-typescript
- https://github.com/anthropics/claude-code-action

可以公开研究的内容包括 CLI 的公开仓库、插件目录、Agent SDK、GitHub Action、命令/配置/权限文档、变更记录和示例。它们能说明公开的工具接口、插件边界、session/resume、权限提示、任务和 SDK 集成方式。

不能声称已经拿到 Claude Code 的完整核心实现、模型服务端、内部 system prompt、内部调度策略或所有桌面/IDE 产品代码。即使 `anthropics/claude-code` 仓库公开，也不能把仓库内容等同于 Claude Code 全部运行时。研究时必须把“官方公开实现”与“根据产品行为做的架构推断”分栏记录。

### OpenAI Codex CLI

Codex CLI 的官方仓库是 Apache-2.0 开源项目，核心 Rust CLI、文档和 SDK 入口可直接研究：

- https://github.com/openai/codex
- https://github.com/openai/codex/tree/main/codex-rs
- https://github.com/openai/codex/blob/main/docs/getting-started.md
- https://github.com/openai/codex/blob/main/docs/config.md
- https://help.openai.com/en/articles/11096431
- https://openai.com/index/introducing-the-codex-app/
- https://openai.com/index/introducing-upgrades-to-codex/

Codex CLI 的公开资料明确体现了 approval modes、sandbox、工具调用、任务进度、compact、MCP、会话恢复、diff/测试结果和本地执行边界。Codex App 的官方介绍还公开了多线程、多 agent、worktree 隔离、任务监督和 review diff 的产品方向。

## 3. 可迁移的 Harness 设计

### 3.1 统一事件协议

建议把所有运行信息归一成一个 `AgentEvent`，而不是让 W1 activity、runtime event、task run、proposal 和聊天消息分别驱动 UI：

```text
AgentEvent {
  eventId, sequence, runId, attemptId, parentEventId,
  kind, actor, status, timestamp,
  target, summary, detailRef,
  requiresApproval, approvalKey,
  toolCallId, taskId, checkpointId,
  costDelta, artifactRefs, errorCode
}
```

`kind` 至少包括：`run_started`、`plan_created`、`task_ready`、`task_started`、`tool_intent`、`tool_output`、`artifact_staged`、`proposal_created`、`approval_required`、`human_decision`、`checkpoint_saved`、`compaction`、`subagent_started`、`subagent_finished`、`run_paused`、`run_resumed`、`run_failed`、`run_completed`。

事件只保存用户需要审计的摘要、证据引用和结果，不保存隐藏思维链。UI 用 sequence 补齐和去重；SSE 只是传输方式，数据库事件才是事实来源。

### 3.2 Tool lifecycle

每次工具调用必须经过：`intent -> policy check -> approval if needed -> started -> output/error -> receipt -> event`。工具定义应包含名称、输入 schema、读集合、写集合、风险级别、是否收费、幂等键、超时、取消能力和允许的 side effect。

这与仓库当前 `tool_calls`、`ToolRegistry`、`ReActExecutor` 已有方向一致，但前端还看不到一个统一的 lifecycle。右侧面板应该能展开看到：工具做了什么、读写了什么、花费多少、结果在哪里、失败是否可重试。

### 3.3 Approval 与安全边界

审批不是一个布尔值，而是带 scope 和版本的决定：

- 只读分析：自动允许。
- 写 staged proposal：允许，但不能写 canonical。
- 接受 package、搬运到 World、删除/合并：必须人工审批。
- 外发正文、付费 API、网络、文件系统越界：单独审批。

审批应绑定 `approvalKey = run + task + tool + inputHash + policyVersion`。重复点击返回同一结果；输入变化后必须重新审批。Electron 仍是 native bridge，React 不能直接访问 runtime DB。

### 3.4 Plan / Task DAG / Subagents

Codex 和 Claude 的可迁移经验不是“让模型自由乱跑”，而是给 Agent 一个可观察的任务空间：计划、依赖、当前任务、等待原因、写集合、子 agent 和结果。Narrative IDE 已有 `agent_task_plans`、`agent_tasks`、claim lease、dead letters 等表，应把它们提升为右侧面板的主数据源。

计划允许 re-plan，但只在新证据、任务失败或人工修改时发生。子 agent 通过 artifact blackboard 协作，不能共享内存对象；canonical commit、proposal publication 和 package acceptance 由单写者负责。

### 3.5 Checkpoint、Resume、Compaction、Time Travel

恢复必须从已提交 checkpoint 或已确认 artifact 继续，不能从半截 token stream 继续。未知 API 结果必须停下来让用户决定是否重试。Time Travel 创建 child attempt，旧历史不可变；重放产生新的 proposal，不能静默覆盖 canonical 数据。

Compaction 的目标是压缩工作上下文，不删除审计证据。UI 只显示“已压缩到 checkpoint X，保留了哪些事实、哪些 artifact、哪些未决问题”。

### 3.6 Streaming UI 与审计日志

Codex/Claude 式体验不是把每个 chunk 原样刷屏，而是分三层：

1. 当前行动：正在计划、调用工具、等待权限或提交结果。
2. 可展开的行动卡：工具输入摘要、输出摘要、耗时、费用、artifact。
3. 长期审计：完整事件序列、checkpoint、决定、失败和重试。

右侧控制面板默认显示第一层和第二层，第三层按需展开。这样用户知道 Agent 正在做什么，又不会被无意义 token 淹没。

## 4. 对照本仓库的 Gap Matrix

| 能力 | 当前仓库事实 | Gap | 建议模块边界 |
|---|---|---|---|
| Durable run | `RuntimeStore` 已有 run/attempt/lease/event/tool/decision/checkpoint metadata | 事件模型仍按 W1/runtime 分散，UI 需二次拼接 | `sidecar/runtime/protocol.py` 统一事件 schema |
| Tool lifecycle | `ToolRegistry`、`ReActExecutor`、tool intent/result 已存在 | 缺少统一 approval、receipt、取消和前端展示 | `sidecar/agentic/tools/` + `routers/runtime.py` |
| Plan/DAG | `agent_task_plans`、`agent_tasks`、claim/fence/dead letter 已存在 | Agent Dock 只显示统计，未展示 DAG/写锁/等待原因 | `src/ui-react/components/agent/AgentRunConsole.tsx` |
| Subagents | 有 agentic 模块和 task 表 | 缺少 parent/child 运行视图与 artifact blackboard UI | `sidecar/agentic/subagents.py` + agent console |
| Approval | W0 有 grant/deny，W1 有 human decisions | 权限语义未统一到所有工具和 package acceptance | `ApprovalPolicy` + `approval_required` event |
| Resume | W1 已有恢复、未知调用、人审重试 | 主要是 W1 特化，缺通用 run protocol | runtime API v2，先兼容旧 API |
| Time Travel | checkpoint fork 已有 | UI 需要 diff、分叉理由、成本预估 | `CheckpointTimeline` + fork preview contract |
| Streaming | SSE + durable polling fallback | 没有统一 event envelope；右侧 dock 仍只看 taskRuns | `AgentEventStream` store slice |
| Compaction | runtime 有安全 memory 约束，Codex/Claude 可作参考 | 没有面向用户的 compaction 记录和恢复摘要 | `compaction` event + summary artifact |
| Audit | 事件、决定、receipt 表存在 | 缺用户可读的 run report 与 artifact provenance | `RunAuditPanel` + report serializer |
| World Model | `worldContainers`、`worldCategories`、`categoryPath` 并存 | 多套分类事实来源导致错位；`categoryPath[1]` 是脆弱推断 | `NotebookTree` 单一 parentId 树；迁移旧字段 |
| 条目详情 | EventInspector 有 title/summary/time/location/participants | “查看时间线”只跳 Writing Studio，关联 event/scene/timeline 不成可追溯链 | `EntityLinkPanel`，所有链接带 type/id/label/source |
| Review搬运 | proposal gate 存在 | 没有明确 Reviewer -> Organizer -> Canonical Commit 的阶段和拒绝原因 | `ReviewPackage`、`RoutingDecision`、single-writer commit |

## 5. 对用户指出的三个问题的架构判断

### World Model 文件夹

OneNote 值得借鉴的是“笔记本/分区/页面”的稳定层级和明确的当前选中对象，而不是把所有对象都塞进一个 category。Narrative IDE 应采用：

```text
Notebook
  Folder(parentId)
    Item(type, id)
```

`type` 决定条目语义，`parentId` 决定位置；组织、地点、制度、功法各自有允许的根 folder。拖动只接受明确的 droppable folder，并在 drop 前做类型规则校验。`categoryPath` 只作为旧数据迁移输入，不能继续作为运行时事实。

### 条目内部与关联链

每个 world item 或 event 的详情页应该分成：基本信息、来源证据、关联人物、关联事件、关联场景、所属时间线、所属 folder。关联对象必须显示“名称 + 类型 + 所在位置 + 可打开目标”，而不是只保存 ID 或跳到一个泛路由。

“查看时间线”应打开具体 timeline 和具体 event 的定位状态：`timelineId`、`branchId`、`eventId`、`sceneId`。如果一个条目关联多个 event，显示列表并允许逐个定位；不存在的关联显示断链，不要静默跳转。

### Review 与数据搬运

采集 Agent 不应决定最终 World 分类。推荐四阶段：

1. Extractor 只提交带 source span 的候选条目。
2. Semantic Reviewer 判断实体类型、字段证据、重复和疑问。
3. Organizer 依据类型 allowlist 选择稳定 `targetFolderId`，无法判断时进入待处理队列。
4. Human/Canonical Writer 批准后原子搬运。

“正门”应被识别为地点/入口；“主网六”若证据不足，应是地点、设施、称谓或未知候选，而不能因为文本上下文自动进入门派组织。组织 folder 只接受 `organization` 类型；地点 folder 只接受 `location` 类型；功法 folder 只接受 `technique` 类型。错误分类必须生成 reviewer issue，而不是静默纠正。

## 6. 建议的右侧控制面板

右侧面板分为四个固定层级：

- **Run Header**：目标、模型、预算、状态、暂停/继续/取消。
- **Live Activity**：当前 plan/task/tool，显示 Agent、阶段、耗时、费用和等待原因。
- **Review Queue**：需要审批的工具、proposal package、分类冲突、未知 API 结果。
- **History**：checkpoint 时间线、事件审计、子 agent、artifact 和 diff。

默认只显示行动摘要；点击行动卡才展开工具输出和证据。面板必须支持从某个事件跳回 World item、具体 event、scene 或 timeline，而不是只打开一个宽泛 workspace。

## 7. 落地顺序

1. 先定义统一 `AgentEvent`、`ToolCall`、`ApprovalRequest`、`ArtifactRef`、`ReviewIssue` 类型，并让 W0/W1 适配；不先改视觉。
2. 将右侧 Dock 改为单一 runtime event consumer，展示 plan/task/tool/approval/checkpoint，而不是读取多个旧数组。
3. 将 World Model 迁移到单一 NotebookTree，旧 `worldCategories`/`categoryPath` 只读迁移一次并生成 receipt。
4. 增加 `EntityLinkPanel` 和具体 event/timeline/scene 定位协议。
5. 把 Reviewer/Organizer/Canonical Writer 做成明确的 proposal 状态机和类型路由器。
6. 增加断线重连、重复审批、未知工具结果、任务 lease 过期、错误分类、Time Travel 分叉和 Electron 重启的 Playwright/pytest 验收。

完成标准不是“面板看起来像 Claude”，而是用户能回答：Agent 现在做什么、为什么做、写了什么、是否需要我批准、失败后从哪里恢复、哪个证据导致这个条目进入这个 folder。

## 8. 官方来源清单

- Anthropic Claude Code repository: https://github.com/anthropics/claude-code
- Anthropic Claude Code overview: https://code.claude.com/docs/en/overview
- Anthropic Claude Code setup: https://docs.anthropic.com/en/docs/claude-code/getting-started
- Anthropic Claude Agent SDK Python: https://github.com/anthropics/claude-agent-sdk-python
- Anthropic Claude Agent SDK TypeScript: https://github.com/anthropics/claude-agent-sdk-typescript
- Anthropic Claude Code Action: https://github.com/anthropics/claude-code-action
- OpenAI Codex CLI repository: https://github.com/openai/codex
- OpenAI Codex Rust CLI README: https://github.com/openai/codex/tree/main/codex-rs
- OpenAI Codex CLI getting started: https://github.com/openai/codex/blob/main/docs/getting-started.md
- OpenAI Codex configuration: https://github.com/openai/codex/blob/main/docs/config.md
- OpenAI Codex CLI help: https://help.openai.com/en/articles/11096431
- OpenAI Codex App architecture/product overview: https://openai.com/index/introducing-the-codex-app/
- OpenAI Codex agentic workflow overview: https://openai.com/index/introducing-upgrades-to-codex/

## 9. 研究限制

本报告使用官方网页、官方 GitHub 仓库和本仓库当前代码/开发文档。Claude Code 的公开仓库和 SDK 不等于其全部闭源核心；关于内部调度、隐藏 prompt 或商业产品服务端的内容，本报告没有作事实断言。所有“建议迁移”均是基于公开接口和本仓库现状的工程推导。
