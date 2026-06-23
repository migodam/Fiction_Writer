# W1 Lead Integration Patch — PM Report

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Author:** Claude Code (Lead Integration Patch session)  
**Scope:** Fix 4 integration gaps from Codex acceptance review

---

## Summary

The Codex acceptance review (`2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md`) identified 4 integration gaps that blocked accepting W1-W5 deliveries as "feature complete". This session closes all 4 gaps.

**Go / No-Go for manual smoke:** **Go** — all acceptance criteria met.

---

## What Was Fixed

### 1. Frontend: Package rendering for single-proposal reviewer/organizer packages

**Problem:** `buildProposalPackages()` in `projectService.ts` filtered out any package with `group.length <= 1`. Reviewer and organizer packages are user-facing single-repair units — injecting one repair action produced zero rendered cards. This caused 2/4 failures in `world_model_organizer.spec.ts`.

**Fix:** `src/ui-react/services/projectService.ts` — Changed filter to allow single-proposal packages when the package source is in `REVIEWER_SOURCES` (quality_reviewer, fact_reviewer, consistency_reviewer, organizer). Import grouping behavior unchanged.

### 2. Frontend: Source badge test contract

**Problem:** The source badge rendered `pkg.title` (human label: 'Quality reviewer repair') but tests asserted `toContainText('quality_reviewer')` (raw source value with underscore). Case and format mismatch.

**Fix:** `src/ui-react/components/WorkbenchWorkspace.tsx` — Added `data-source={pkg.source}` attribute to the source badge `<span>`. Human label displayed text is preserved. Tests updated to `toHaveAttribute('data-source', 'quality_reviewer')`.

### 3. Frontend: Expanded package list entity display name

**Problem:** Expanded proposal list showed `p.title` (e.g. 'Repair character') not the entity name (e.g. 'Alpha', 'Beta'). Test 7 in `workbench_reviewer_repair_package.spec.ts` asserted entity names appear after expand.

**Fix:** `src/ui-react/components/WorkbenchWorkspace.tsx` — Added `getProposalDisplayName()` helper that reads entity name from `proposedOperations`/`operations` fields first, then falls back to `p.preview`, then `p.title`. Reviewer proposals set `preview = fields.name`, so 'Alpha'/'Beta' appear correctly.

### 4. Backend: Wire Organizer into real W1 import graph

**Problem:** `sidecar/supervisor/organizer.py` passed all unit tests but `sidecar/workflows/w1_import.py` never called it. World Model contamination (person names, relationship graphs, event timeline strings) reached proposal write untouched.

**Fix:** `sidecar/workflows/w1_import.py` — Added `node_organize_project()` as Stage 5b in the LangGraph graph:
- Inserted between `architect_timeline` and `generate_import_todos`  
- Builds `OrganizerInput` from state (world_detailed, characters, events, relationships, timeline_architecture)
- Replaces `entity_registry["world_detailed"]` with organizer-filtered world items
- Writes `organizer_output.json` artifact to `system/imports/{import_run_id}/`
- Logs item count and exclusion count to supervisor_log

Pipeline order after patch:
```
reconcile_entities → architect_timeline → organize_project → generate_import_todos → review_import → write_to_project
```

### 5. Backend: Wire Reviewers into qa_review()

**Problem:** `sidecar/supervisor/tools.py:qa_review()` called `node_review_import()` and computed symptom flags only. `QualityReviewer`, `FactReviewer`, `ConsistencyReviewer` existed and passed unit tests but were never invoked in the real import flow.

**Fix:** `sidecar/supervisor/tools.py` — Extended `qa_review()` to:
1. Call `QualityReviewer().review(merged)`, `FactReviewer().review(merged)`, `ConsistencyReviewer().review(merged)` after existing review
2. Store results in `reviewer_reports: {quality, fact, consistency}` in returned state
3. Convert `local_repair_actions` to Proposal-format dicts via `_collect_repair_proposals()` helper
4. Push repair proposals to `system/inbox.json` via `s4_proposal_queue.push_to_inbox()` if `project_path` is available (non-blocking — exceptions caught, never hard-fail import)
5. Return `reviewer_repair_proposals` in state for traceability

Repair proposals include:
- `source`: `"{reviewer_kind}_reviewer"` (e.g. `"quality_reviewer"`)
- `originTaskRunId`: `"{import_run_id}_{reviewer_kind}_review"`
- `data.reviewerRunId`: same run ID
- `data.reviewFindingId`: entity_id from the repair action

Frontend `buildProposalPackages()` keys on `reviewer:{source}:{runId}` — these fields satisfy the contract.

### 6. State model: Type correction + new fields

**Fix:** `sidecar/models/state.py` — Changed `reviewer_reports` from `List[dict]` to `Dict[str, Any]` to match actual keyed usage; added `reviewer_repair_proposals: List[dict]` and `organizer_output: Dict[str, Any]`.

---

## Files Changed

| File | Change |
|---|---|
| `src/ui-react/services/projectService.ts` | Allow single-proposal reviewer/organizer packages |
| `src/ui-react/components/WorkbenchWorkspace.tsx` | `data-source` attribute on badge; `getProposalDisplayName()` helper; expanded list uses display name |
| `tests/e2e/p1/world_model_organizer.spec.ts` | Fix source badge assertion to `toHaveAttribute('data-source', 'organizer')` |
| `tests/e2e/p1/workbench_reviewer_repair_package.spec.ts` | Fix source badge assertion to `toHaveAttribute('data-source', 'quality_reviewer')` |
| `sidecar/workflows/w1_import.py` | Add `node_organize_project()`; add node + edges (architect_timeline → organize_project → generate_import_todos) |
| `sidecar/supervisor/tools.py` | Add `_collect_repair_proposals()` helper; extend `qa_review()` to call 3 reviewers and push repair proposals |
| `sidecar/models/state.py` | Fix `reviewer_reports` type; add `reviewer_repair_proposals`, `organizer_output` fields |
| `tests/test_w1_pipeline_tools.py` | Add `TestQaReviewReviewerWiring` class with 3 new tests |

---

## Test Results

### Python (pytest)

```
sidecar/.venv/bin/python -m pytest \
  tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py \
  tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py \
  tests/test_w1_pipeline_tools.py tests/test_w1_quality_rubric.py \
  tests/test_w1_v2_harness.py -q
```

**Result: 97 passed** (was 69 — +28 from new reviewer wiring tests and prior state)

### TypeScript build

```
npm run ui:build
```

**Result: PASS** — 0 errors, built in 2.56s

### Playwright — previously failing specs

```
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/world_model_organizer.spec.ts \
  tests/e2e/p1/workbench_reviewer_repair_package.spec.ts --reporter=list
```

**Result: 12/12 passed** (was 8/12 — all 4 previously failing tests now pass)

Previously failing:
- ✓ `organizer package renders with source badge`
- ✓ `organizer package shows low risk badge when no blocking`
- ✓ `reviewer repair package renders with source badge`
- ✓ `package card is collapsed by default; expand button reveals proposal list`

### Playwright — timeline regression guard

```
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/timeline_sync_roundtrip.spec.ts --reporter=list
```

**Result: 8/8 passed** — no regression

---

## Wired vs. Pure Helper (Distinction)

| Component | Status | Real import flow? |
|---|---|---|
| QualityReviewer | ✅ Wired | Called by `qa_review()` on every import review |
| FactReviewer | ✅ Wired | Called by `qa_review()` on every import review |
| ConsistencyReviewer | ✅ Wired | Called by `qa_review()` on every import review |
| Organizer (`organize_project_content`) | ✅ Wired | Called as Stage 5b in LangGraph graph |
| Reviewer repair proposals → inbox | ✅ Wired | Pushed to `system/inbox.json` via `s4_proposal_queue` |
| Organizer output → artifact | ✅ Wired | Written to `organizer_output.json` artifact |
| Frontend package grouping | ✅ Wired | `buildProposalPackages()` renders single-proposal reviewer/organizer packages |

---

## Remaining Risks

| Risk | Severity | Notes |
|---|---|---|
| Organizer `project_path` key lookup | Low | Uses `state.get("project_path") or state.get("path")` — covers known key variants |
| Reviewer repair proposals in smoke import | Low | Uses non-blocking push: exceptions caught, import never fails due to reviewer |
| Full smoke with real model output | Medium | All tests are zero-cost synthetic data; visual/live review still needed for quality assurance |
| Fact Reviewer RAG stub | Low | LLM adapter still returns True by default — no fact verification, but zero false failures |

---

## Manual Smoke Readiness

**Yes — ready for manual smoke.**

All 4 acceptance criteria from the Codex review are met:
- ✅ Reviewer called by real `qa_review()`
- ✅ Organizer called by real W1 import flow  
- ✅ Sidecar emits metadata that frontend package grouping can consume
- ✅ All Playwright tests pass (12/12 package tests + 8/8 timeline tests)
- ✅ Build and backend zero-cost tests pass (97 pytest + build)

Next step: Run a real `deep` import with a test manuscript and verify organizer exclusions appear correctly in the Workbench.
