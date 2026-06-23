# W1 Import P0 Lead Report — Live Smoke Runner, Hard-Fail Guard, and Frontend Gates

## Executive Summary

本轮我没有继续把问题推给 Claude，而是作为 Lead 做了三件事：

1. 亲自跑完 Manuscript、Undo、World/Graph、Import Console 的自动化验收。
2. 建立 `tools/w1_live_smoke_10ch.py`，用真实前 10 章源文件走 direct W1 runner。
3. 修复一个比 UI 更严重的后端缺陷：模型连接失败时，W1 不得继续 `done`、不得写 proposal、不得让用户误以为 import 成功。

当前结论：自动化 P0 gate 已通过；真实外部 DeepSeek 10 章 smoke 仍需要用户显式授权，因为它会发送本地小说内容到外部 API 并可能产生费用。Codex 已尝试申请外部网络执行，但安全审查拒绝了未授权外呼，这是正确的保护。

## Worker / Lead 分工

| Role | Owner | 贡献 | 状态 |
|---|---|---|---:|
| Explorer A | Sub-agent Avicenna | 只读确认前 10 章源文件路径、推荐 direct sidecar smoke 路径、说明 dry-run harness 不等于 live smoke | Done |
| Explorer C | Sub-agent Hegel | 只读审计前端覆盖缺口，指出 reviewer activity、真实 world drag/drop、workbench package undo 仍需 Lead 验证 | Done |
| Worker B | Sub-agent Lagrange | 增强 `tools/w1_import_diagnostics.py`，新增 artifact quality 检查与测试 | Done |
| Lead Codex | 本窗口 | 新增 10 章 runner、修复 extraction 全失败 hard_fail、补 reviewer activity Playwright、跑完整 gate、写报告 | Done |

## Root Cause Fixed This Round

### Problem

在 direct 10 章 smoke 中，模型 API 连接失败后，旧逻辑仍可能继续走后续节点，最终出现：

- `current_node = done`
- 写入章节/场景/容器类 proposals
- judge score 低但仍有“完成”形态
- 用户看到的是“好像跑完了”，但实际 AI extraction 全部失败

这就是你前面多次遇到“跑了很久、钱花了、结果像假的”的底层风险之一。

### Fix

`sidecar/supervisor/policy.py` 现在在 window prompt 全失败达到阈值后：

- 写入 `[extraction_failed]` error
- 标记 `converge_status = hard_fail`
- 停止 cross_validate / rerun / reduce / timeline / judge / proposal_write
- streaming 最终 yield `current_node = error`

这意味着系统宁愿明确失败，也不能伪装成功。

## 10-Chapter Smoke Evidence

| Item | Value |
|---|---|
| Source file | `/Volumes/migodam's-external-brain/Development/Narrative_IDE/benchmark_results/w1_manuscript_smoke_20260526_091106/smoke_10_chapter/凡人修仙传_前10章.txt` |
| Runner | `tools/w1_live_smoke_10ch.py` |
| Latest artifact | `/tmp/narrative_ide_w1_live_smoke/20260606_044555` |
| Provider/model attempted | DeepSeek / `deepseek-v4-pro` |
| API key handling | Loaded from local Electron settings only inside subprocess env; key was not printed |
| Final behavior | Correct hard fail under connection/API failure |
| Proposals written | 0 |
| Fake done prevented | Yes |

## Test Results

| Suite | Result |
|---|---:|
| `py_compile sidecar/supervisor/policy.py tools/w1_live_smoke_10ch.py` | PASS |
| `pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py -q` | 113 passed |
| `pytest tests/test_w1_import_artifact_quality.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py -q` | 157 passed |
| `npm run ui:build` | PASS |
| Manuscript + Undo Playwright | 13 passed |
| World hierarchy + World drag/store + Relationship graph Playwright | 9 passed |
| Import activity + Import workflow + Import quality Playwright | 38 passed |
| `git diff --check` | PASS |

## User Bug Checklist Status

| Bug | Status | Evidence |
|---|---:|---|
| Manuscript missing | Fixed in projection path | 9 manuscript Playwright tests pass |
| Undo returns to pre-import | Fixed for covered package path | Post-import undo test passes |
| Relationship graph label overlap | Fixed for star/core graph | Radial layout + label box tests pass |
| World taxonomy misclassification | Partial/fixed deterministic cases | Organizer/reviewer tests + world UI tests pass; real live output still needs smoke |
| World category drag/drop | Partial | Store/action/DOM drag handle covered; full Windows-like drag tree remains larger UI task |
| Import Console reviewer progress | Fixed for activity feed | Reviewer/organizer activity feed test passes |
| 10 chapter live smoke | Needs user-run or explicit approval | Direct runner exists; external DeepSeek call blocked by safety review |
| Model/API failure should stop safely | Fixed | Hard-fail policy test and direct smoke artifact confirm no fake proposal write |

## Remaining Risk

- True DeepSeek live smoke was not completed by Codex because external API execution requires explicit risk-aware approval from the user.
- World Model full OneNote-like tree UX remains only partially implemented; this needs a dedicated UI architecture pass.
- Relationship graph large-scale label placement may still need force-lite collision simulation; current fix covers the reported core star case.

## Recommended Manual Smoke

1. Start Electron normally.
2. Create a fresh project.
3. Import the first 10 chapters with `deepseek-v4-pro` or your chosen available DeepSeek model.
4. Watch Import Console for `quality_reviewer`, `fact_reviewer`, `consistency_reviewer`, and `organizer_repair`.
5. If extraction hard-fails, stop and inspect API/network/provider billing before retrying.
6. If it completes, accept package and inspect Writing Studio Manuscript, World Model classification, relationship graph, and Cmd+Z behavior.

---

## Continuation Addendum — 2026-06-06 13:05 +08

After the first Lead report, I kept the goal active and asked two read-only reviewers to inspect the remaining acceptance risk:

- **Rawls / Smoke readiness reviewer** found two real backend gaps: the runner did not fail on `hard_fail` / quality-probe failure, and pure `run_supervisor_policy()` could still reach `proposal_write` after `budget_exhausted`.
- **Turing / Frontend acceptance reviewer** found that Undo had store-level coverage but not real `Command+Z`, and that World starter cleanup coverage existed but was not included in the latest P0 gate.

### Fixes Applied After Reviewer Feedback

| Gap | Fix | Evidence |
|---|---|---|
| Runner could exit 0 despite bad quality probe | Added `_quality_probe_failures()` and `_smoke_result_exit_code()`; chapter count, empty manuscript nodes, duplicates, blocked proposals, empty branches, failed review status now return non-zero | `tests/test_w1_live_smoke_runner.py` 4 tests |
| Pure policy could proposal-write after `budget_exhausted` | Added extraction-loop budget guard in both non-streaming and streaming policy paths; budget now stops before reduce/judge/proposal_write | `TestPolicyBudgetExhaustedStop` asserts `judge_import` and `proposal_write` are not called |
| Undo shortcut not tested through keyboard | Added real `Meta+Z` Playwright path: accept import package, add character, press `Meta+Z`, imported chapter/scene remain while character is undone | `global_undo.spec.ts` now 6/6 |
| World starter cleanup not in latest gate | Added `import_smoke_acceptance.spec.ts` to the P0 run; it asserts starter English containers/items are removed after import accept | `import_smoke_acceptance.spec.ts` included in 10-test World gate |

### Additional Verification

| Command | Result |
|---|---:|
| `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py tools/w1_live_smoke_10ch.py` | PASS |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py::TestPolicyBudgetExhaustedStop tests/test_w1_supervisor_policy.py::TestPolicyFatalExtractionStop tests/test_w1_live_smoke_runner.py -q` | 8 passed |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_live_smoke_runner.py tests/test_w1_import_artifact_quality.py -q` | 54 passed |
| `sidecar/.venv/bin/python tools/w1_live_smoke_10ch.py --prepare-only` | PASS, no model calls |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/global_undo.spec.ts --reporter=list` | 6 passed |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_smoke_acceptance.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts tests/e2e/p1/world_hierarchy.spec.ts --reporter=list` | 10 passed |
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts tests/e2e/p1/global_undo.spec.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts tests/e2e/p1/import_activity_status.spec.ts --reporter=list` | 20 passed |

### Updated Lead Decision

The local P0 gate is now stronger than the previous report: cost stop-loss, fake-success prevention, real `Command+Z`, manuscript projection, starter cleanup, graph readability, and reviewer activity feed all have direct evidence.

The only remaining hard boundary is the same one: a true external DeepSeek 10-chapter import requires explicit user approval because it sends local manuscript text to an external provider and may incur cost.

---

## Timeout / Token Ledger Addendum — 2026-06-06

User observed: `Import timed out after 30 minutes and was cancelled to prevent silent spend.` even though the token card showed more than 800k input tokens and 200k output tokens.

### Root Cause

The timeout was frontend wall-clock based, not cost/activity based. `src/ui-react/store.ts` used a fixed polling loop:

- 600 iterations
- 3 seconds per iteration
- exactly 30 minutes total
- after the loop, call `w1Cancel()`

That meant a healthy long-running deep import could be cancelled at 30 minutes even when:

- token ledger was increasing,
- activity feed was updating,
- active model calls existed,
- the user could see real progress.

### Fix

The frontend now cancels after 30 minutes only if the import is truly silent:

- no active API calls,
- `idle_seconds >= 30 minutes`,
- no token progress for 30 minutes,
- no recent activity progress for 30 minutes.

It also keeps a separate 4-hour absolute safety cap so a genuinely stuck import cannot run forever.

### Verification

| Command | Result |
|---|---:|
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts tests/e2e/p1/import_token_cost.spec.ts tests/e2e/p1/import_workflow.spec.ts --reporter=list` | 35 passed |

### Product Impact

This matches the intended Claude-Code-like behavior better: long-running work is allowed if it is observable and making progress; only silent spend is cancelled.
