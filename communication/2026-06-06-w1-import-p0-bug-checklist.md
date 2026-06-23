# W1 Import P0 Bug Checklist — 2026-06-06

## Executive Summary

本轮按用户最新手动 smoke 反馈执行 P0 修复：重点不是继续堆 UI，而是修正 Writing/Manuscript 投影、Reviewer 修复落盘、关系图布局、Undo 误回滚、以及 Import Console 的 Reviewer 活动可观测性。

自动化结论：核心零成本 gate 已通过。真实前 10 章 live import 未在本轮自动执行，因为需要 Electron 交互、provider key 与费用确认；dry-run harness 已确认 gated live smoke 默认跳过。

## Bug Checklist

| ID | 用户问题 | 状态 | 本轮证据 | 剩余风险 |
|---|---|---:|---|---|
| P0-1 | Writing Studio 里 Manuscript 为空 | Fixed | `writing_manuscript_import_display.spec.ts` 新增 projection repair 测试，验证缺失 `manuscriptNodes` 时可从 chapters/scenes 投影出 manuscript tree，并能打开 scene 正文 | 需要下一次真实 import smoke 验证 `import_test15` 类项目打开后视觉结果 |
| P0-2 | 空 `nodes.json` / `manuscriptNodes` 覆盖已有正文 | Fixed | `projectService.openProject/saveProject/serializeProjectToFolder` 在 nodes 缺失时 repair，且不再把 `memory://` 写成磁盘目录；`w1_import.py` 不用空 manuscript pairs 覆盖非空 nodes | 若未来新增其他保存路径，仍需复用 service 层，不允许 UI 直接写 canonical storage |
| P0-3 | 新建角色后 Cmd+Z 回到 import 前 | Fixed for import-package path | `global_undo.spec.ts` 新增测试：accept import package 后新增角色，undo 只撤销角色，保留导入章节和 scene | 这不是完整 Command/Patch 架构重写；更深的跨模块 undo 仍建议独立架构任务 |
| P0-4 | 关系图节点排成一条线，边文字互相盖住 | Fixed | `CharacterRelationshipFlow` 改为 deterministic radial layout；`character_relationship_flow_layout.spec.ts` 验证星型关系分散，edge label 有独立盒子 | 大型复杂图仍可能需要 force/cluster/label annealing 第二阶段 |
| P0-5 | World Model 把 `无名口诀` / `项甲功` 归到错误容器 | Fixed for deterministic taxonomy + repair apply | `organizer.py` 加强 `口诀/功/诀/法/术/心法/秘术` 信号；`workbench_reviewer_repair_package.spec.ts` 验证 `reclassify_world_item` 通过 package accept 真正移动 item | 模型输出极差时仍依赖 Reviewer 发现；下一轮 live smoke 需要看 Reviewer 是否产出足够 repair actions |
| P0-6 | Reviewer 看起来没真正修复 | Fixed for supported repair op | `_collect_repair_proposals()` 标准化 `reclassify_world_item` 的 `entityType/entityId`；`projectService` 支持 apply 该 op | Reviewer 仍不能绕过 Workbench 安全门，自动修复会进入 package accept，不会静默改 canonical data |
| P0-7 | Import Console 不显示 Reviewer/repair 进度 | Partial | `qa_review()` 现在 emit `qa_review / quality_reviewer / fact_reviewer / consistency_reviewer / organizer_repair` activity events | 目前是 activity feed 增量，不是全新 Claude-Code 式丰富进度 UI |
| P0-8 | World Model 需要 OneNote-like 多级 Category + 右键/拖拽 | Partial | 本轮优先修错分与 repair apply；已有 categoryPath/categoryId 兼容字段继续保留 | 完整 Notebook -> Category Tree -> Item 交互、右键新建/删除、跨层级拖拽仍需单独 UI 重构 |
| P0-9 | 真实前 10 章 import 结果要亲测 | Needs live smoke | dry-run harness 5/5 PASS，live smoke gate 默认跳过 | 需要用户确认 provider/key/费用后在 Electron 中执行 |

## Code Contribution Matrix

| Area | Files | Contribution |
|---|---|---|
| Manuscript projection | `src/ui-react/services/projectService.ts`, `src/ui-react/store.ts`, `sidecar/workflows/w1_import.py` | 从 chapters/scenes deterministic 生成 `ManuscriptNode` tree；读内容时 fallback 到 linked scene；避免空 nodes 覆盖 |
| Proposal / Reviewer repair | `src/ui-react/models/project.ts`, `src/ui-react/services/projectService.ts`, `sidecar/supervisor/tools.py` | 增加 `reclassify_world_item` op 类型和 applier；Reviewer repair proposal 标准化；package accept 可实际移动 world item |
| World taxonomy | `sidecar/supervisor/organizer.py`, `tests/test_w1_organizer.py`, `tests/test_w1_reviewers_quality.py` | 修正“口诀/功/诀/法/术”等分类信号，补 Reviewer quality 测试 |
| Graph layout | `src/ui-react/components/graph/CharacterRelationshipFlow.tsx`, `tests/e2e/p1/character_relationship_flow_layout.spec.ts` | 星型关系 radial layout；edge label 盒子和 offset |
| Undo regression | `src/ui-react/store.ts`, `tests/e2e/p1/global_undo.spec.ts` | Import package accept 不再进入普通 Cmd+Z 快照路径；新增 post-import undo 回归 |
| Console activity | `sidecar/supervisor/tools.py` | Reviewer 阶段和 repair proposal 数量写入 W1 activity feed |

## Verification

| Command | Result |
|---|---:|
| `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/tools.py sidecar/supervisor/organizer.py sidecar/supervisor/reviewers/quality_reviewer.py` | PASS |
| `npm run ui:build` | PASS |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py -q` | 55 passed |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q` | 62 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts --reporter=list` | 8 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/global_undo.spec.ts --reporter=list` | 5 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts --reporter=list` | 11 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts tests/e2e/p1/graph_sidebar_linkage.spec.ts --reporter=list` | 5 passed |
| `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` | 5/5 passed, secret scan clean, live smoke skipped |

## Manual Smoke Checklist

下一次真实 import 前建议按这个顺序验收：

1. 打开新项目，导入前 10 章，确认 Import Console 显示 Reviewer 阶段和 repair 数量。
2. Import done 后先不 accept，检查 Workbench package 是否包含 Reviewer/Organizer repair package。
3. Accept package 后打开 Writing Studio -> Manuscript，确认章节树和正文存在。
4. 在 World Model 中检查 `无名口诀`、`项甲功`、功法/法术类项目是否进入 `功法与术法` 或等价容器。
5. 新建一个角色后按 Cmd+Z，确认只撤销角色，不撤销 import package。
6. 打开关系图，把韩立和莫大夫/张铁/武言/韩三叔构成星型关系，确认节点不再横排挤压，关系文字不盖住其它节点。

## Known Non-P0 Follow-Up

- 完整 Undo 架构仍应从 snapshot 逐步迁移到 Command/Patch/Transaction，而不是长期依赖模块内手写 snapshot。
- World Model 的 OneNote-like notebook/category/item 交互仍未完整重构，本轮只修 taxonomy 和 repair apply 的 P0 链路。
- Console 还可以继续升级成“当前 Reviewer / findings / repairs / ETA”的专门卡片。
- 大型关系图仍需要 force-lite 或 cluster layer；本轮只解决小型核心人物星型关系遮挡。

---

## Lead Re-Verification Addendum — 2026-06-06 12:53 +08

本节记录 Codex Lead 在 Worker A/B/C 后的亲自复验。结论有两个：第一，P0 自动化 gate 已补齐；第二，真正 10 章 live smoke 仍不能由 Codex 在未获显式外部 API 风险确认前直接发往 DeepSeek，但我们已经用同一 10 章源文件跑通 gated direct runner，并修掉一个会导致“模型全失败却显示 done”的严重后端缺陷。

### Updated Checklist

| ID | 用户问题 | 当前状态 | 新证据 |
|---|---|---:|---|
| P0-1 | Writing Studio 里 Manuscript 为空 | Fixed by projection + tests | `writing_manuscript_import_display.spec.ts` 9/9 通过，包括章节顺序、空 starter 清理、nodes repair、scene 正文读取 |
| P0-3 | Cmd+Z 回到 import 前 | Fixed for covered regression | `global_undo.spec.ts` 4/4 通过；包含 accept import package 后 undo 不恢复 import 前项目 |
| P0-4 | 关系图排成直线、关系文字覆盖 | Fixed for star/core graph | `character_relationship_flow_layout.spec.ts` 2/2 通过；核心人物星型关系 radial 分布，edge label 有可读盒子 |
| P0-5/P0-8 | World taxonomy / category drag | Partial but tested | `world_hierarchy.spec.ts` + `world_item_drag_drop.spec.ts` 7/7 通过；仍缺真实 OS-like 拖拽完整交互重构 |
| P0-7 | Console 显示 Reviewer/repair 进度 | Fixed for activity feed | `import_activity_status.spec.ts` 新增 reviewer feed 用例通过；显示 `quality_reviewer/fact_reviewer/consistency_reviewer/organizer_repair` |
| P0-9 | 真实前 10 章 import 亲测 | Blocked for external API; direct runner completed | `tools/w1_live_smoke_10ch.py` 使用前 10 章源文件执行；外部 DeepSeek 调用因安全审查需用户显式批准，未绕过 |
| P0-10 | 模型连接失败后不能假装成功 | Fixed | `sidecar/supervisor/policy.py` 在 prompt 全失败时 hard_fail，停止 reduce/architect/judge/proposal_write；回归测试通过 |

### 10-Chapter Smoke Runner Evidence

- Source fixture: `/Volumes/migodam's-external-brain/Development/Narrative_IDE/benchmark_results/w1_manuscript_smoke_20260526_091106/smoke_10_chapter/凡人修仙传_前10章.txt`
- Runner: `tools/w1_live_smoke_10ch.py`
- Latest artifact: `/tmp/narrative_ide_w1_live_smoke/20260606_044555`
- Outcome: hard fail with 0 proposals, which is correct under network/API connection failure.
- Important fix: before the policy fix, the same failure could continue to `done` and write low-quality placeholder proposals; after the fix, it stops before proposal write.

### Verification Commands Added

| Command | Result |
|---|---:|
| `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py tools/w1_live_smoke_10ch.py` | PASS |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py -q` | 113 passed |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_import_artifact_quality.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py -q` | 157 passed |
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts tests/e2e/p1/global_undo.spec.ts --reporter=list` | 13 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/world_hierarchy.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts --reporter=list` | 9 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts tests/e2e/p1/import_workflow.spec.ts tests/e2e/p1/import_quality_status.spec.ts --reporter=list` | 38 passed |
| `sidecar/.venv/bin/python tools/w1_import_diagnostics.py /tmp/narrative_ide_w1_live_smoke/20260606_044555/project --format both --fail-on-threshold` | Expected FAIL: no manuscript/chapters/proposals because API extraction hard-failed |

### Current Lead Decision

可以让用户手动跑 Electron 里的 10 章 smoke，但 Codex 自动外呼 DeepSeek 需要用户在知道“会把本地小说内容发送给外部 DeepSeek API 并产生费用”的前提下显式批准。没有这个批准时，本轮不会绕过安全审查。
