# W1 Reviewer / Organizer / Inbox / Timeline 验收复核报告

**Date:** 2026-06-01  
**Reviewer:** Codex Acceptance Review  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Scope:** 复核 W1-W5 Claude sessions 的实际交付、报告可信度、测试结果和是否可进入手动 smoke。

---

## 结论

**不建议现在进入手动 import smoke。**

Timeline canonical round-trip 这一块当前表现最好，Playwright 8/8 通过；但是 Reviewer / Organizer / Inbox package 的产品闭环还没有完成：

- Reviewer 已经有 deterministic framework，但还没有接进 `qa_review()`。
- Organizer 已经有纯函数和单元测试，但还没有插入 `w1_import.py` graph。
- Inbox package 前端 UX 有基础实现，但 sidecar 还没有稳定产出对应 package metadata。
- 新增/相关 Playwright 并非全绿，报告里“E2E PASS”的说法需要修正。
- 当前工作区仍有多个未追踪文件和一个已删除旧 report，尚未达到可提交/可验收状态。

---

## 实际执行的验收命令

| Command | Result | Notes |
|---|---:|---|
| `sidecar/.venv/bin/python -m pytest tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_pipeline_tools.py -q` | **69 passed** | Reviewer / Organizer / Pipeline tool 单元层通过 |
| `npm run ui:build` | **PASS** | TypeScript + Vite build 成功 |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts --reporter=list` | **8 passed** | Timeline canonical fields、save-reload、sync warning、label overlap 测试通过 |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/world_model_organizer.spec.ts --reporter=list` | **2 passed / 2 failed** | 新增 organizer package spec 未跑通 |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts --reporter=list` | **6 passed / 2 failed** | W5 package UX spec 未全绿 |

---

## 逐项验收

| Area | Status | Evidence | Blocking Issue |
|---|---|---|---|
| Reviewer Framework | **Partially accepted** | `69 passed` includes reviewer tests; reviewer package exists | Not wired into `sidecar/supervisor/tools.py:qa_review()` |
| Fact Reviewer token-light design | **Accepted at unit level** | Tests pass; evidence-card-only design reported | No RAG adapter/live quality verification yet |
| Consistency Reviewer | **Accepted at unit level** | Tests pass | Not called by import pipeline |
| Organizer pure function | **Accepted at unit level** | `tests/test_w1_organizer.py` included in `69 passed` | `organize_project_content()` not inserted into `w1_import.py` graph |
| Organizer UI package E2E | **Rejected for now** | `world_model_organizer.spec.ts`: 2/4 failed | Single-proposal package tests expect card, but `buildProposalPackages()` filters `group.length > 1` |
| Inbox package transaction | **Partially accepted** | Most transaction tests pass | 2/8 Playwright failures; sidecar metadata gap remains |
| Timeline canonical sync | **Accepted for current zero-cost scope** | `timeline_sync_roundtrip.spec.ts`: 8/8 passed | Still needs real import smoke |
| Timeline label overlap | **Accepted for current zero-cost scope** | Dense label Playwright test passed | Still needs visual/live smoke on real dense import |
| Reports / docs | **Partially accepted** | Merged PM report exists | Some claims overstate E2E pass status |
| Git hygiene | **Not accepted yet** | `git status` has many untracked files + deleted old report | Needs cleanup/staging decision before commit |

---

## Playwright Failures

### 1. `world_model_organizer.spec.ts`

Result: **2 passed / 2 failed**

Failing tests:

- `organizer package renders with source badge`
- `organizer package shows low risk badge when no blocking`

Root cause:

`src/ui-react/services/projectService.ts` only creates package cards for grouped proposals where `group.length > 1`. These tests inject exactly one organizer proposal, so no package card is rendered. The tests and implementation contract disagree.

Decision needed:

- If a package can contain one proposal, update `buildProposalPackages()` to allow single-item reviewer/organizer packages.
- If packages are intentionally multi-proposal only, update the tests to inject two proposals and update the report language.

### 2. `workbench_reviewer_repair_package.spec.ts`

Result: **6 passed / 2 failed**

Failing tests:

- `reviewer repair package renders with source badge`
- `package card is collapsed by default; expand button reveals proposal list`

Root causes:

- Source badge renders human label `Quality reviewer repair`, while the test expects raw string `quality_reviewer`.
- Expanded list displays proposal titles like `Repair character`, not proposed entity names `Alpha` / `Beta`. Either UI should expose entity names, or tests should assert title text.

Recommendation:

I would fix the UI to expose entity names in package expanded rows, because PM/user-facing review needs to show what the package actually contains, not just generic `Repair character`.

---

## Integration Gaps That Must Be Fixed Before Manual Smoke

1. **Wire reviewers into import review stage**

`sidecar/supervisor/tools.py:qa_review()` currently calls `node_review_import()` and symptom flags only. It does not call `run_quality_review`, `run_fact_review`, or `run_consistency_review`, so the Reviewer framework is not part of real W1 import.

2. **Insert organizer into W1 graph**

`sidecar/supervisor/organizer.py` exists and passes tests, but `w1_import.py` does not call `organize_project_content()`. World Model cleanup/classification will not affect real imports until this is wired.

3. **Emit package metadata from sidecar**

Frontend grouping depends on source/package run metadata such as `source='organizer'` and `data.reviewerRunId` / `originTaskRunId`. The merged report itself marks this as high-risk deferred. Until sidecar emits it, package UI will not represent real reviewer/organizer output.

4. **Fix E2E specs or implementation contract**

Current Playwright result is not green. This must be corrected before claiming package UX ready.

5. **Clean repo state**

Current `git status` includes untracked code, untracked reports, an untracked `docs/superpowers/`, and a deleted old communication report. These need a deliberate keep/delete/stage decision.

---

## Recommended Lead Patch Order

1. Fix package UI/test contract:
   - Decide single-proposal package behavior.
   - Prefer showing entity display name in expanded package rows.
   - Re-run `world_model_organizer.spec.ts` and `workbench_reviewer_repair_package.spec.ts`.

2. Wire Organizer into `w1_import.py`:
   - Add deterministic Stage 5b after entity reconciliation and before timeline architecture.
   - Persist `organizer_output.json`.
   - Ensure excluded module contamination does not enter world proposals.

3. Wire Reviewer into `qa_review()`:
   - Run quality/fact/consistency reviewers after import review artifact exists.
   - Persist `reviewer_reports`.
   - Convert repairable findings into package proposals with stable `reviewerRunId`.

4. Re-run zero-cost gate:
   - Pytest reviewer/organizer/pipeline tests.
   - `npm run ui:build`.
   - Playwright package specs.
   - Timeline sync spec.

5. Only then do a small manual `deep` import smoke.

---

## Final PM Judgment

This delivery is **strong progress**, but not an acceptance-ready milestone. The best part is W4 Timeline: canonical persistence and label layout now have meaningful E2E coverage. The weakest part is the Reviewer/Organizer integration boundary: the new intelligence exists as tools and pure functions, but real W1 import does not yet consume it.

**Go / No-Go:** No-go for manual smoke as “feature complete”.  
**Allowed next step:** Lead integration patch + E2E cleanup.  
**Manual smoke after:** all package/reviewer/organizer Playwright tests pass and sidecar emits real package metadata.

---

## Claude 修复指令 / Plan Prompt

下面这段可以直接复制给 Claude Code，让它先进入 plan 模式。重点不是“把测试改绿”这么浅，而是补上真实 W1 import 产品链路：Reviewer 必须进入 review stage，Organizer 必须进入 import graph，Inbox package 必须能消费真实 sidecar metadata。

```markdown
PLEASE CREATE A PLAN, THEN IMPLEMENT AFTER APPROVAL:

# W1 Reviewer / Organizer / Inbox 集成缺口修复计划

## Context

Codex acceptance review found that the current W1-W5 delivery is not yet acceptance-ready.

Confirmed green:
- `sidecar/.venv/bin/python -m pytest tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_pipeline_tools.py -q` → 69 passed.
- `npm run ui:build` → pass.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts --reporter=list` → 8/8 passed.

Confirmed failures:
- `world_model_organizer.spec.ts` → 2/4 failed.
- `workbench_reviewer_repair_package.spec.ts` → 6/8 passed, 2 failed.

High-risk integration gaps:
- Reviewer framework exists but is not wired into `sidecar/supervisor/tools.py:qa_review()`.
- Organizer exists as `sidecar/supervisor/organizer.py` but is not inserted into `sidecar/workflows/w1_import.py`.
- Frontend package grouping depends on `source`, `originTaskRunId`, and `data.reviewerRunId` / package metadata, but sidecar does not yet emit these fields consistently.

Hard constraints:
- No live API/model calls.
- No full50.
- Do not read provider keys.
- Do not rewrite timeline W4 unless a regression is directly caused by this task.
- Do not touch unrelated dirty files.
- Keep changes deterministic and zero-cost.
- Preserve existing P0 observability/cancel/402 behavior.

## Required Fixes

### 1. Fix Inbox package UI/test contract

Investigate and decide the intended package rule:
- Preferred product behavior: reviewer/organizer packages may contain a single proposal if the source is `quality_reviewer`, `fact_reviewer`, `consistency_reviewer`, or `organizer`, because these are user-facing repair/organizer units.
- Import packages can still require multiple proposals if that is the existing contract.

Fix `src/ui-react/services/projectService.ts` and tests accordingly:
- `buildProposalPackages()` should render reviewer/organizer package cards even when the group has one proposal.
- Keep import grouping behavior stable unless tests prove it should change.
- Expanded `PackageCard` rows should show useful entity display names, not only generic proposal titles like `Repair character`.
- For display name, prefer operation fields: `name`, `title`, `label`, then proposal `preview`, then proposal `title`.
- Source badge assertions should match the UI contract. Either expose a stable raw source via `data-testid`/attribute or assert the human label intentionally. Prefer human-readable UI text plus stable test IDs.

Acceptance:
- `world_model_organizer.spec.ts` passes 4/4.
- `workbench_reviewer_repair_package.spec.ts` passes 8/8.

### 2. Wire Organizer into real W1 import graph

`sidecar/supervisor/organizer.py` currently passes unit tests but real import does not call it.

Implement deterministic Stage 5b after entity reconciliation and before timeline architecture:
- Build `OrganizerInput` from current state:
  - `characters`: `state["entity_registry"]["characters"]`
  - `events`: registry event values or current event candidates
  - `relationships`: current relationships
  - `world_candidates`: `state["entity_registry"]["world_detailed"]`
  - `timeline_architecture`: current architecture if present
  - `project_digest`: project digest
  - `source_language`: detected source language / fallback `"zh"`
- Call `organize_project_content()`.
- Replace or filter world candidates so excluded module-contamination/person/rank items do not become World Model proposals.
- Persist `organizer_output.json` artifact in the same import artifact directory used by W1.
- Add supervisor log/activity event entry if an activity system already exists.

Acceptance:
- Add/extend zero-cost tests proving module contamination like `人物关系图` and `事件时间线` does not reach world proposals.
- Add/extend tests proving `organizer_output.json` is produced in synthetic/no-live flow if there is an artifact harness.
- Existing W1 regression tests still pass.

### 3. Wire Reviewers into `qa_review()`

`sidecar/supervisor/tools.py:qa_review()` currently calls `node_review_import()` and symptom flags only. It must also run the three deterministic reviewers.

Implement:
- Run `QualityReviewer`, `FactReviewer`, and `ConsistencyReviewer` after the standard review report is built.
- Store output under `reviewer_reports` in returned state.
- Preserve existing `import_review_report` behavior and `gate_failures`.
- Do not make reviewer hard-fail the import unless it detects safety/contract failures. Novel-quality issues should become warnings, repair actions, or orchestrator requests.
- Ensure token ledger says zero-cost / no live calls.

Package emission:
- For local repair actions or organizer packages that should appear in Workbench, emit proposals with stable package metadata:
  - `source`: one of `quality_reviewer`, `fact_reviewer`, `consistency_reviewer`, `organizer`
  - `originTaskRunId`: stable reviewer/organizer run id
  - `data.reviewerRunId`: same run id
  - `data.reviewFindingId` or equivalent if available
- Use package grouping fields consistently so frontend `buildProposalPackages()` can group them.

Acceptance:
- Add zero-cost test proving `qa_review()` returns `reviewer_reports` with `quality`, `fact`, `consistency`.
- Add zero-cost test proving repair/package proposals include package metadata.

### 4. Keep Timeline W4 green

Do not regress:
- canonical branch fields: `startAnchor`, `parentBranchId`, `forkEventId`, `endAnchor`, `endMode`, `mergeTargetBranchId`, `mergeEventId`, `geometry`
- timeline save-reload round trip
- label overlap test

Acceptance:
- `timeline_sync_roundtrip.spec.ts` remains 8/8 pass.

### 5. Repo hygiene and reports

Update:
- `communication/2026-06-01-w1-reviewer-organizer-verification-report.md` or create a new follow-up report explaining what was actually fixed.
- `dev_logs/2026-06-01-w1-reviewer-organizer-lead-fix.md` with commands and results.
- Docs only if behavior changes.

Do not delete old communication reports unless explicitly asked. If replacing old reports, explain why.

## Verification Commands

Run these in order, not one per tiny edit:

```bash
sidecar/.venv/bin/python -m py_compile \
  sidecar/supervisor/tools.py \
  sidecar/supervisor/organizer.py \
  sidecar/workflows/w1_import.py \
  sidecar/supervisor/pipeline_tools.py
```

```bash
sidecar/.venv/bin/python -m pytest \
  tests/test_w1_reviewers_quality.py \
  tests/test_w1_reviewers_fact.py \
  tests/test_w1_reviewers_consistency.py \
  tests/test_w1_organizer.py \
  tests/test_w1_pipeline_tools.py \
  tests/test_w1_quality_rubric.py \
  tests/test_w1_v2_harness.py \
  -q
```

```bash
npm run ui:build
```

```bash
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/world_model_organizer.spec.ts \
  --reporter=list
```

```bash
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/workbench_reviewer_repair_package.spec.ts \
  --reporter=list
```

```bash
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/timeline_sync_roundtrip.spec.ts \
  --reporter=list
```

## Final Report Requirements

Write a PM-style Markdown report in `communication/` with:
- Files changed.
- What was wired into real W1 import vs only tested as a pure helper.
- Exact test results.
- Remaining risks.
- Manual smoke readiness: yes/no.

Chat summary can be short, but the file report must be detailed.

## Definition of Done

Do not claim this is done unless:
- Reviewer is actually called by real `qa_review()`.
- Organizer is actually called by real W1 import flow.
- Sidecar emits metadata that frontend package grouping can consume.
- `world_model_organizer.spec.ts` passes.
- `workbench_reviewer_repair_package.spec.ts` passes.
- `timeline_sync_roundtrip.spec.ts` still passes.
- Build and backend zero-cost tests pass.
- Report exists in `communication/`.
```

---

## 给 Claude 的最短补充说明

如果 Claude 已经有上下文，可以只发下面这段：

```markdown
请按 `communication/2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md` 里的 “Claude 修复指令 / Plan Prompt” 做 Lead integration patch。不要只修测试表面。必须把 Reviewer 接进 `qa_review()`，把 Organizer 接进真实 `w1_import.py`，并让 sidecar 产出 frontend package grouping 所需 metadata。当前 Playwright 实测：`world_model_organizer.spec.ts` 2/4 failed，`workbench_reviewer_repair_package.spec.ts` 6/8 passed，`timeline_sync_roundtrip.spec.ts` 8/8 passed。完成后写详细 PM report 到 `communication/`。
```
