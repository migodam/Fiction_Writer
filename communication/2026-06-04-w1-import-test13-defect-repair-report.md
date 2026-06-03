# W1 Import Test 13 Defect Repair Report — 2026-06-04

## Executive Summary

本轮不是复述 Claude 的验收结论，而是直接检查真实项目 `import_test13`：

`/Volumes/migodam's-external-brain/home/narrative_ide/import_test13`

结论：Reviewer/Organizer 的 helper 和测试存在，但真实 W1 legacy import graph 没有完整闭环到项目写入链路。因此用户看到的问题不是错觉，确实包括章节重复、chapter metadata 空、空 timeline branch、人物简介重复、以及 reviewer 不在真实路径充分工作。

本轮修复以确定性数据链路为主，避免把基础结构正确性继续押给 Reviewer 事后修补。

## Real Project Findings

| Area | import_test13 Evidence | Root Cause |
|---|---|---|
| Reviewer 是否真在干活 | `system/history.json` 176 条 proposal 全部 `source=import`，没有 `quality_reviewer/fact_reviewer/consistency_reviewer/organizer` 来源 | 三 Reviewer 接在 supervisor `qa_review()` tool 路径，但 `w1_import.py` legacy graph 的 `node_review_import()` 没有调用它们 |
| Manuscript | `writing/scenes/*.md` 有正文，但 imported chapter metadata 的 `summary/goal/notes` 全为空，starter `scene_1` 仍存在 | `node_build_manuscript()` 只生成 title/chunk/content/orderIndex，没有填 writer-facing details；项目加载未清理 starter |
| 章节重复 | 31 个 chapter；第一章到第十章各出现 3 次；`chap_1 Chapter 1` starter 仍存在 | 多次 import accept 后没有按 chapter number/title 做安全合并；读项目时没有 normalization |
| Timeline 空 branch | 3 个 branch；`主时间线` 两个空 branch，20 个 event 全在 `branch_main` | branch proposal 写入时没有按 event branch refs 过滤空 branch；旧项目打开也没有过滤 |
| 人物简介重复 | 韩立 summary 有多个年龄片段；舞岩、王护法等也有重复描述 | character reducer/proposal write 只是拼接短文本，缺少事实片段级去重 |
| World Model | Organizer helper 已能过滤部分污染项，但真实 import artifact 没有 `organizer_output.json` | Organizer stage 的图节点/Artifact 闭环不足；flat `world` 与 `world_detailed` 同步容易漏 |

## Code Changes This Session

| File | Change | Why It Matters |
|---|---|---|
| `sidecar/workflows/w1_import.py` | Added `_dedupe_text_segments()` and wired it through `_compact_text_value()` | Removes repeated age/fact fragments before character proposals are written |
| `sidecar/workflows/w1_import.py` | Enriched manuscript chapters with `summary`, `goal`, `notes`, `chapterNumber` | Chapter side card no longer depends on blank metadata |
| `sidecar/workflows/w1_import.py` | Added duplicate manuscript chapter merge by parsed Chinese/Arabic chapter number/title | Prevents multiple 第九章/第十章 records from one import compile path |
| `sidecar/workflows/w1_import.py` | Ensured organizer writes `organizer_output.json` and mirrors enriched category onto flat `world` index | Makes organizer evidence visible and keeps proposal write from seeing excluded/stale categories |
| `sidecar/workflows/w1_import.py` | Added compact proposal view and runs Quality/Fact/Consistency Reviewer inside `node_review_import()` | Real W1 graph now emits reviewer reports, not only supervisor tool tests |
| `sidecar/workflows/w1_import.py` | Filters timeline branches before proposal write to keep only branches referenced by events unless no event refs exist | Prevents empty imported branch proposals |
| `src/ui-react/services/projectService.ts` | Added project-open normalization for writing collections | Existing damaged projects are cleaned on open: blank starter removed, duplicate chapters folded, scenes remapped |
| `src/ui-react/services/projectService.ts` | Added project-open normalization for timeline collections | Existing generic empty import branches are filtered and events with missing branch refs are remapped |
| `tests/test_w1_import_compiler.py` | Added regression tests for duplicate chapter merge, manuscript metadata, age-fragment dedupe, and real reviewer reports | Locks the concrete `import_test13` failure modes |

## Acceptance Checklist

| User-Reported Problem | Status | Evidence / Caveat |
|---|---|---|
| 人物简介重复 | Fixed for new proposal writes; old project cleans when re-imported or rewritten | `_compact_character_card()` now removes repeated age fragments; test added |
| Manuscript 为空 | Partially fixed | Scene markdown already had content; new import chapter metadata is enriched; existing projects are normalized on open. If UI still shows blank, next check should be specific component binding |
| Duplicate chapters | Fixed for compiler and project open | `_dedupe_manuscript_chapters()` + `normalizeWritingCollections()` |
| Timeline 空白 branch | Fixed for proposal write and project open | branch filtering now uses actual event branch references; project-open cleanup only removes generic empty import branches, not user-named planning branches |
| World Model 错误分类 | Partially fixed | Organizer now writes artifact and mirrors category fixes; taxonomy quality still needs next real smoke validation |
| Reviewer 真的在干活吗 | Partially fixed | Real `node_review_import()` now runs all three reviewers and writes reports. Reviewer repair proposals are still advisory; deterministic compiler/apply fixes handle structural issues |

## Verification

| Command | Result |
|---|---|
| `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py` | PASS |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py -q` | PASS, 96 passed |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_tools.py tests/test_w1_supervisor_policy.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py -q` | PASS, 137 passed |
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts --reporter=list` | PASS, 3 passed |

## Remaining Risks

| Risk | Why It Remains |
|---|---|
| Existing `import_test13` files may still contain historical duplicate JSON until opened/saved by the app | The frontend normalization runs through `openProject()` and serializes back; this was not manually executed against the live project folder in this session |
| Reviewer repair proposals are not yet a fully transactional auto-fix layer | They now run in the real graph, but deterministic compiler/write/load safeguards remain the reliable path |
| Timeline event quality still may be too流水账 | This session fixed structural correctness, not the event-density prompt/orchestrator policy |
| World taxonomy still needs live smoke validation | Organizer deterministic tests pass, but real model outputs can still stress category rules |

## Manual Smoke Recommendation

1. Open `import_test13` once after this build so `openProject()` normalization can rewrite duplicate chapters and empty branches.
2. Check Writing:
   - No blank `Chapter 1 / Scene 1` starter mixed with imported chapters.
   - 第九章/第十章 are single chapters, not repeated triplets.
   - Chapter side card has summary/goal/notes.
3. Check Timeline:
   - Empty imported branches are gone.
   - Events still attach to a valid branch.
4. Run a fresh small deep import only after the above old-project cleanup looks correct.
5. Inspect latest import artifact:
   - `review_report.json` contains `reviewer_reports`.
   - `organizer_output.json` exists.
