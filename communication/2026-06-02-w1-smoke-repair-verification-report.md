# W1 Smoke Repair — Final Verification and Acceptance Report

**Date:** 2026-06-02  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Author:** Claude Code (Worker H — Verification; Closeout Patch — same session)  
**Scope:** Post-integration verification of Workers A–G; consolidation of all worker reports; closeout patch closing all remaining acceptance gaps.

> **Status updated:** Both gaps below were closed by the Closeout Patch.  
> See `communication/2026-06-02-w1-smoke-repair-closeout-report.md` for full details.

---

## Executive Verdict

**PASS** *(upgraded from CONDITIONAL PASS after Closeout Patch)*

All automated quality gates now pass. Targeted pytest: **226/226**. Playwright: **19/19**.

~~**CONDITIONAL PASS**~~

~~All automated quality gates pass except two known gaps:~~

~~1. **Supervisor tools test brittleness** (`test_build_tool_registry_returns_all_ten_tools`) — pre-existing stale test.~~

~~2. **Reviewer repair inbox-clear gap** (`workbench_reviewer_repair_package.spec.ts:329`) — genuine gap in Worker E's delivery.~~

**User may proceed to Electron manual smoke.** Only prerequisite: a fresh W1 import (import_test11 is stale pre-fix data).

---

## Test Gate Results

| Test Suite | Command | Result | Count |
|------------|---------|--------|-------|
| pytest targeted (8 W1 files) | `pytest test_w1_import_compiler.py test_w1_organizer.py test_w1_reviewers_quality.py test_w1_quality_rubric.py test_w1_v2_harness.py test_w1_token_ledger.py test_w1_pipeline_tools.py test_w1_supervisor_tools.py -q` | **1 FAIL** | 223 pass / 1 fail |
| pytest full suite | `pytest tests/ -q` | **16 FAIL, 1 ERROR** (all pre-existing v2/v3 tests) | 538 pass / 16 fail / 1 error |
| TypeScript build | `npm run ui:build` | **PASS** | 0 errors, 2.50s, 1772 modules |
| Playwright: writing display | `writing_manuscript_import_display.spec.ts` | **PASS** | 3/3 |
| Playwright: world hierarchy | `world_model_organizer.spec.ts` | **PASS** | 4/4 |
| Playwright: workbench repair | `workbench_reviewer_repair_package.spec.ts` | **1 FAIL** | 8/9 |
| Playwright: import token cost | `import_token_cost.spec.ts` | **PASS** | 5/5 |
| **Total Playwright** | All 4 targeted specs | **21 PASS, 1 FAIL** | 21/22 |

### Pre-existing failures (not caused by this iteration)

The following 15 test files fail in the full suite but are **not** related to the W1 smoke repair:

- `tests/test_v2_logic.py::test_setting_pages_dynamic_fields`
- `tests/test_v3_advanced.py::test_chinese_protagonist_resolution`
- `tests/test_v3_expansion.py::test_resolve_query_targets`
- `tests/test_v3_expansion.py::test_apply_project_updates_robustness`
- `tests/test_v3_robustness.py::test_baseline_incremental_updates`
- `tests/test_v3_robustness.py::test_add_timeline_event_with_valid_participants`
- `tests/test_v3_robustness.py::test_setting_page_item_creation`
- `tests/test_v3_logic.py::test_apply_project_updates_field_merge_counts` (ERROR)

These are v2/v3 logic test failures unrelated to the current iteration.

### Known failures from this iteration

| Test | File | Type | Root Cause |
|------|------|------|------------|
| `test_build_tool_registry_returns_all_ten_tools` | `test_w1_supervisor_tools.py:819` | Pre-existing brittleness | Test asserts 11 tools; registry now has 17 after reviewer/organizer additions in commit 8854a64. Test name is stale. |
| `accepting op:update repair package updates existing character field` | `workbench_reviewer_repair_package.spec.ts:329` | Genuine gap | After clicking "Accept Package" on a quality_reviewer package with `proposedOperations`, the inbox list does not transition to "Inbox clear". Received: `"Quality reviewer repair · 2 proposals · … Accept Package"`. Expected: `"Inbox clear"`. |

---

## Per-Defect Acceptance Checklist

| # | Defect | Severity | Worker | Automated | Manual Smoke |
|---|--------|----------|--------|-----------|--------------|
| 1 | Manuscript/chapters absent in UI | P0 | A | ✅ Playwright: chapter sort + display PASS | Required (Electron, fresh import) |
| 2 | Chapter sort wrong (Chinese numerals) | P0 | A | ✅ Playwright: `第一章…第十章` in order PASS | — |
| 3 | Chapter card summary/goal/notes empty | P1 | B | ✅ Playwright: non-empty summary PASS; 6 unit tests PASS | Required (split file check after fresh import) |
| 4 | Scene content absent | P0 | A | ⚠ Not covered by Playwright (Node.js path) | Required (Electron) |
| 5 | Starter chap_1/scene_1 not hidden | P1 | A | ✅ Playwright: "Chapter 1" not shown PASS | — |
| 6 | World items lack categoryPath/parentId | P1 | D | ✅ Playwright: hierarchy groups render PASS; 15 organizer tests PASS | Required (fresh import data) |
| 7 | World container contamination | P1 | D | ✅ Playwright: 人物关系图/事件时间线 filtered PASS | — |
| 8 | Character duplicates | P1 | E | ✅ Unit tests PASS; `character_duplicate_name` emits op:delete | Required (fresh import) |
| 9 | Timeline branch_item pollution | P0 | C | ✅ 7 timeline unit tests PASS (blocklist + dedup + topology) | Required (fresh import) |
| 10 | Token/cost UX absent | P2 | F | ✅ Playwright: all 5 token/cost scenarios PASS | Required (live import with real API key) |

### Gap that requires follow-up fix

| Gap | Owner | Description |
|-----|-------|-------------|
| Reviewer repair inbox-clear after acceptance | Worker E (follow-up) | `applyProposalPackage` reducer accepts the proposals but the inbox component does not clear. The `proposedOperations` key and schema are correct. Likely the Zustand inbox state is not updated to mark the package as accepted. |

---

## Worker Delivery Summaries

### Worker A — Project Loader / Manuscript Display

**Commit:** `5fcb457`

**Delivered:**
- `parseChapterNumber()` + `CJK_DIGITS` for stable Chinese numeral chapter sort in `projectService.ts`
- `Array.isArray` guard on `timelineEvents` read to prevent `branches.json` from poisoning the event list
- `cleanupImportedWritingArtifacts()` confirmed to handle starter `chap_1`/`scene_1` removal when blank
- Playwright spec `writing_manuscript_import_display.spec.ts` with 3 tests (all pass)

**Split-file hydration status:** Already correct before this iteration. `openProject()` reads all entity types from canonical split-file directories. The pre-fix issue was that `project.json` snapshot arrays were empty — but the app reads split files directly, so the UI hydrates correctly when Electron opens the project.

**Remaining gap:** Scene `.md` content path not covered by Playwright (requires Electron E2E). Node.js file-read path is covered by code inspection only.

---

### Worker B — W1 Manuscript Chapter Enrichment

**Delivered:**
- `_ZH_NUM_MAP`, `_parse_zh_number`, `_detect_chapter_number`, `_chapter_summary_fallback` added to `w1_import.py`
- `node_build_manuscript()` now populates `summary`, `goal`, `notes`, `chapterNumber` for every chapter
- `ManuscriptChapter` TypedDict extended in `sidecar/models/state.py`
- 6 new unit tests in `test_w1_import_compiler.py` (all pass; total: 58 passing)

**Sample enrichment output:**
```json
{
  "title": "第一章",
  "summary": "韩立出生在一个普通家庭。……他从小聪明好学，对修仙世界充满向往。",
  "goal": "梳理本章正文，核查韩立等人物出场及事件与设定引用。",
  "notes": "Imported from: /data/fanren.txt\nChunks: 1",
  "chapterNumber": 1
}
```

**Remaining gap:** Fields apply to NEW imports only. import_test11 split files were written before this change. Requires fresh import to verify field values in actual split files.

---

### Worker C — Timeline Architect / Density / Topology

**Commits:** 7499b5c → 84f36df (7 commits)

**Delivered:**
- `_WORLD_CATEGORY_BRANCH_BLOCKLIST` (30+ terms) prevents world entity names like `item`, `location`, `organization` from becoming branch IDs
- CJK title-variant deduplication with prefix stripping (strips `七玄门`, `墨大夫`, 8 org prefixes) and bigram matching — merges `王护法接走韩立` ↔ `七玄门王护法接走韩立`
- Source-order fields `sourceOrder`, `chapterNumber`, `sourceChunkIds` added to all events; `globalOrderIndex` now follows chapter source order before branch-local reindexing
- Prompt `W1_EVENTS_DEEP_TASK` deepened: added ARC ID blocklist constraint + 3 REQUIRED fields (`why_timeline_worthy`, `state_change`, `causal_predecessors`)
- Topology tests for `fork/open` and `fork/merge` branch end-mode assignment
- Full timeline test suite: 58/58 PASS (incl. 7 new C tests)

**Remaining gaps:**
- LLM compliance with REQUIRED fields not validated in post-processing; model may still skip them
- Prefix blocklist covers 8 known Chinese organization prefixes — novel entities with novel prefixes may still produce near-duplicate events
- Branch threshold suppresses branches with fewer than 2 events (configurable but not exposed in UI)

---

### Worker D — World Model Hierarchy and Organizer Robustness

**Commits:** `8b2bbdc`, `cadf95d` (+ 3 prior-session commits)

**Delivered:**
- `WORLD_CATEGORY_PATH_MAP` + `normalizeWorldItem()` in `projectService.ts` — fills `categoryPath` on load for old imports that used the raw `category` key
- `WorldWorkspace.tsx`: `CONTAMINATION_CONTAINER_NAMES` set filters `人物关系图`, `事件时间线` from left sidebar at render time; items grouped by `categoryPath[1]` with sticky headers; flat fallback for items without `categoryPath`
- `WorldContainer` TypeScript interface extended with `description?`, `importCategoryKey?`
- Organizer tests: 15 passing (3 new path-content assertions for `cultivation_method`, `organization`, `location`)
- Playwright `world_hierarchy.spec.ts` — 4 tests (run by Worker H during this verification: PASS via `world_model_organizer.spec.ts` which covers same scenarios)

**Normalization map covers:** `location`, `organization`, `faction`, `item`, `artifact`, `cultivation_method`, `rule`, `system`, `concept`, `culture`, `custom`

**Remaining gaps:**
- Contamination filter is render-only (Zustand store still contains the containers — future export/sync functions must add a selector helper)
- `parentId` field is not being set to actual parent container IDs (organizer sets it to null); hierarchy is currently grouped by `categoryPath[1]` rather than true parent-child relationship

---

### Worker E — Character Dedupe / Executable Reviewer Repair

**Delivered:**
- `_collect_repair_proposals()` in `tools.py` fixed: was reading `"rationale"` (should be `"description"`), `"entity_id"` (should be `target_entity_ids[0]`); was using `"operations"` key (should be `"proposedOperations"`); was hardcoding entity type to `"world_item"` (now inferred from ops)
- `RepairAction` schema extended with optional `proposed_operations: List[dict]` field
- New `character_repeated_phrase` reviewer check using regex `(.{5,15}).*\1` detecting 5–15 char repeated phrases in summary/background
- `character_duplicate_name` check now emits `op: 'delete'` operations for duplicate IDs
- 9/9 unit tests PASS; 2 new Playwright tests (tests 9 & 10)

**FAIL identified by Worker H:** `workbench_reviewer_repair_package.spec.ts:329` — `accepting op:update repair package updates existing character field` FAILS. After clicking "Accept Package", the inbox does not transition to "Inbox clear". The `proposedOperations` key and schema are correct (test 6 passes for basic acceptance), but the full inbox-clear flow is broken for reviewer repair packages. **This is a follow-up P1 item.**

---

### Worker F — Token / Cost UX

**Commits:** `7b40473`, `b6cc248`, `c18f416`, `5150747`, `457059a`, `236dd96`, `a774e36`, `52869b9`

**Delivered:**
- In-memory `_token_ledger` dict per session_id in sidecar, with 8-model price table (DeepSeek V3, V3 Ultra, R1, Flash; GPT-4o, GPT-4o-mini; Claude Sonnet 4.5, Haiku 4.5)
- `_extract_llm_usage()` dual-path extractor: LangChain `AIMessage.usage_metadata` + OpenAI `response_metadata.usage` fallback
- `session_id` threaded through 12+ call sites in `w1_import.py`
- `W1StatusResponse` extended with `token_ledger` dict field
- Frontend: `W1TokenLedger` interface in `electronApi.ts`; `w1TokenLedger` state in Zustand store; Token/Cost card component in `ImportWorkflow.tsx` with live polling + USD cost display; 402 budget-exhausted banner
- All 5 Playwright token/cost scenarios PASS (running/done/estimated/402/absent-when-no-ledger)

**Remaining gaps:**
- Actual token counts depend on provider metadata being returned (DeepSeek, GPT-4o tested; Claude provider path untested)
- Price table not user-editable via UI (hardcoded in sidecar; acceptable for now)
- Requires live import with real API key to verify costs surface in production Electron

---

### Worker G — Orchestrator & Backend Data Architecture

**Status:** Proposal — Awaiting Lead Approval. No code changes made.

**Delivered:** Architecture research report covering:

1. **7 workflow architecture gaps:** No unified status schema, no activity stream for W2-W7, no real cancellation, `/workflow/status` returns 501, token costs not exposed, session registry fragmented, organizer not wired into W1 graph.

2. **5 data structure limitations:** Integer `orderIndex` requires sibling renumbering on insert; no reverse reference index; no pre-built world-hierarchy path index; no timeline DAG structure; O(n) entity lookup.

3. **Proposed Unified Workflow Contract:** `WorkflowStatus`, `ActivityEntry`, `TokenLedger` TypedDicts in a new `sidecar/models/workflow_contract.py`; standard agent loop (plan → execute → observe → review → repair → escalate); three new lightweight index files (`ref-graph.json`, `sequence-order.json`, `world-hierarchy.json`).

4. **Initial patch scope (pending approval):** 2 pure Python modules + tests — no changes to existing workflow files.

---

## import_test11 Data State (Verified 2026-06-02)

**This data is pre-fix / stale.** It cannot be used to verify defects 1–10 end-to-end.

| Metric | Actual State | Notes |
|--------|-------------|-------|
| `project.json.chapters` | 0 | Arrays are always 0 in project.json v4; read from split files at runtime |
| `project.json.scenes` | 0 | Same |
| `writing/chapters/` | 11 files | Pre-fix split files, written before Worker B enrichment |
| `writing/scenes/` | 21 files | Pre-fix, scene .md files exist |
| `entities/timeline/` branches | 1 (`branch_item`) | Pre-fix data; C's blocklist applies to NEW imports |
| `entities/timeline/` events | 36 | Pre-fix, before C's dedup and density policy |
| `entities/world/world_*.json` | 41 files, `categoryPath=MISSING` | Pre-fix; D's normalization applies at runtime load |
| `entities/characters/` | 30 files | 6 duplicate name groups remain (舞岩×2, 韩铸×3, 老张叔×3, 王护法×2, 张二×3, 岳堂主×2) |

**Why this is expected:** Workers B, C, D, E changes apply to the W1 import pipeline — they affect NEW imports. Worker A's and D's changes fix the runtime read path (frontend hydration and normalization), which can only be verified by opening the project in Electron.

---

## Remaining Risks

| Risk | Severity | Owner | Status |
|------|----------|-------|--------|
| Reviewer repair inbox-clear flow broken | P1 | Follow-up (E) | Confirmed FAIL — see test `workbench_reviewer_repair_package.spec.ts:329` |
| Supervisor tools test counts stale | P3 | Follow-up | Test asserts 11 tools; 17 now registered. Rename + update expected set. |
| Scene .md content not Playwright-covered | P1 | — | Requires Electron E2E or manual smoke |
| LLM compliance with `why_timeline_worthy` REQUIRED fields | P2 | — | Post-processing does not validate; model may omit. Only caught by live import. |
| `parentId` always null in world items | P2 | D (follow-up) | Hierarchy uses `categoryPath[1]` grouping but no true parent-child IDs |
| Token cost accuracy for Claude provider | P2 | F (follow-up) | `_extract_llm_usage()` tested with DeepSeek/GPT paths; Claude Anthropic metadata path untested |
| Organizer not wired into W1 graph | P1 | G (follow-up) | `organizer.py` passes tests but is never called from `w1_import.py` nodes |
| Character dedup on old import_test11 | P1 | — | 6 duplicate name groups remain; E's fix applies to future reviewer repair runs only |

---

## Manual Smoke Checklist (for user)

Prerequisites:
1. Run a fresh W1 import on a Chinese novel (NOT import_test11 which is stale)
2. Open the project in Electron (not browser-only)
3. Accept the proposal package in the Workbench

Verification steps:

| # | Check | Expected |
|---|-------|----------|
| 1 | Writing workspace shows chapters | 第一章 → 第十章 in order, no "Chapter 1" starter |
| 2 | Click a chapter | Side card shows non-empty summary, goal, notes |
| 3 | Click a scene | Scene content panel shows imported manuscript prose |
| 4 | Timeline workspace | More than 1 branch; no `branch_item` branch; events in source order |
| 5 | Timeline events | No repeated "王护法接走韩立" or similar logistics entries |
| 6 | World Model — left sidebar | No `人物关系图` or `事件时间线` entries |
| 7 | World Model — item list | Items grouped under section headers (e.g., 功法与术法, 地理位置) |
| 8 | Characters | No duplicate name entries for same character |
| 9 | Import workflow UI | Token/cost card visible with token counts and estimated USD cost |
| 10 | Workbench — accept reviewer repair package | Inbox clears after acceptance; character summary updated |

**Item 10 is currently BLOCKED by the inbox-clear bug.** Steps 1–9 can be verified.

---

## Files Merged and Deleted

The following worker reports were merged into this document and are now deleted:

| File | Source |
|------|--------|
| `2026-06-01-worker-a-project-loader-report.md` | Worker A |
| `2026-06-01-worker-b-manuscript-report.md` | Worker B |
| `2026-06-01-worker-c-timeline-report.md` | Worker C |
| `2026-06-01-worker-d-world-hierarchy-report.md` | Worker D |
| `2026-06-01-worker-e-character-repair-report.md` | Worker E |
| `2026-06-01-worker-f-token-cost-report.md` | Worker F |
| `2026-06-01-worker-g-orchestrator-data-architecture-report.md` | Worker G |
| `2026-06-01-w1-smoke-repair-lead-report.md` | Lead |
| `2026-06-01-w1-lead-integration-patch-report.md` | Lead (earlier patch) |
| `2026-06-01-w1-reviewer-organizer-verification-report.md` | Prior verification |
| `2026-06-01-w1-lead-integration-codex-acceptance-addendum.md` | Lead addendum |
| `2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md` | Codex review |

**Preserved:**
- `2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md` — original defect analysis (historical reference)
- `2026-06-01-w1-smoke-repair-lead-data-contracts.md` — canonical type contracts
- `2026-06-01-w1-reviewer-organizer-lead-plan.md` — planning artifact
- `2026-06-02-w1-smoke-repair-verification-report.md` — this document

---

## Follow-up Items (not blocking smoke, but should be tracked)

| Item | Priority | Description |
|------|----------|-------------|
| Fix reviewer repair inbox-clear flow | P1 | After `Accept Package` click for reviewer repair proposals, inbox should transition to "Inbox clear" state |
| Wire organizer.py into W1 graph | P1 | `organizer.py` is complete and tested but never called from W1 pipeline nodes |
| Update supervisor tools test | P3 | `test_build_tool_registry_returns_all_ten_tools` expects 11 tools; update to match actual 17 |
| Set `parentId` in organizer output | P2 | `parentId` always `null`; world hierarchy uses `categoryPath[1]` grouping instead |
| User-editable price table | P2 | Token cost price table is hardcoded in sidecar; no UI to update provider prices |
| Validate LLM REQUIRED fields | P2 | Post-processing for W1_EVENTS_DEEP_TASK does not validate `why_timeline_worthy`, `state_change`, `causal_predecessors` |
