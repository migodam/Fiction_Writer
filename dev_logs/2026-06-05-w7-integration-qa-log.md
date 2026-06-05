# Worker W7 — Integration QA Log

**Date:** 2026-06-05  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Worker:** W7 (Integration QA)

---

## Timeline

### Phase 1: Pre-requisite Reads
- Read `AGENTS.md`, `dev_docs/README.md`, `dev_docs/DEV_RULES.md` (via Explore agent)
- Read all W1-W6 communication reports (via Explore agent)
- Inspected git log, changed files vs main, test file inventory (via Explore agent)

### Phase 2: Novel File Discovery

```bash
find . -maxdepth 4 -name "*.txt" | grep -iv "node_modules|.venv"
```

**Result:** `benchmark_results/w1_failure_closure_20260526_011743/smoke_10_chapter/凡人修仙传_前10章.txt` (662 lines, 10 chapters). Also `novels/凡人修仙传1.txt` (full novel).

### Phase 3: py_compile

```bash
git diff main --name-only | grep '\.py$' | xargs python -m py_compile
# exit: 0
```

43 changed Python files, 0 syntax errors.

### Phase 4: W1 Import Module Load

```bash
source sidecar/.venv/bin/activate
python -c "import sidecar.workflows.w1_import; print('W1 import module loads OK')"
# W1 import module loads OK
```

### Phase 5: Full pytest

```bash
python -m pytest tests/ -q --tb=short
# 568 passed, 17 failed, 7 errors
```

**Failure breakdown:**
- 10 legacy v2/v3 failures confirmed pre-existing on main branch
- 2 stale fixture failures in `test_w1_orchestrator_artifacts.py` (expects `W1_EXTRACT_EVENTS_DEEP_ARC`, actual `W1_EXTRACT_EVENTS_DEEP_SPARSE` — correct behavior post-W1 AI delivery)
- 4 v2 harness cascade failures from same stale fixture
- 1 file-not-found error in legacy v3 tests

### Phase 6: W1-W6 Targeted pytest (255 tests)

```bash
python -m pytest tests/test_w1_organizer.py tests/test_w1_supervisor_tools.py \
  tests/test_w1_supervisor_policy.py tests/test_w1_manifest_revision_schema.py \
  tests/test_w1_quality_rubric.py tests/test_w1_reviewers_quality.py \
  tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py \
  tests/test_w1_prompt_policy_selection.py tests/test_w1_token_ledger.py \
  tests/test_w1_pipeline_tools.py tests/test_w1_run_events.py -q
# 255 passed in 1.06s
```

### Phase 7: UI Build

```bash
npm run ui:build
# ✓ 1773 modules transformed
# ✓ built in 2.52s
# BUILD_EXIT: 0
```

### Phase 8: Playwright W1-W6 Owned Specs

```bash
npm run test:e2e -- --project=chromium tests/e2e/p1/global_undo.spec.ts \
  tests/e2e/p1/graph_sidebar_linkage.spec.ts tests/e2e/p1/import_activity_status.spec.ts \
  tests/e2e/p1/import_quality_status.spec.ts tests/e2e/p1/import_smoke_acceptance.spec.ts \
  tests/e2e/p1/import_token_cost.spec.ts tests/e2e/p1/import_workflow.spec.ts \
  tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts \
  tests/e2e/p1/timeline_interaction.spec.ts tests/e2e/p1/timeline_topology_import.spec.ts \
  tests/e2e/p1/workbench_reviewer_repair_package.spec.ts tests/e2e/p1/world_hierarchy.spec.ts \
  tests/e2e/p1/world_model_organizer.spec.ts
# 108 passed (1.3m)
```

### Phase 9: Playwright Full p1 Suite

```bash
npm run test:e2e -- --project=chromium tests/e2e/p1/
# 129 passed, 12 failed (2.5m)
```

12 failures are pre-existing (backlog_gaps, chapter_preview, characters_routes 2, cross_page_links 2, graph_layout_persist 1, layout_i18n, tag_search, workbench_import_package_accept 1, world_map_publish). All confirmed pre-date W1-W6 work.

### Phase 10: Artifact Inspection

```bash
find . -name "review_report.json" -not -path "*/.worktrees/*"
# 5 files in benchmark_results/ (all pre-W2 refactoring, reviewer_reports=[])

find . -name "prompt_policy_decision.json" -not -path "*/.worktrees/*"
# (no output — artifact only generated on live import)

find . -name "organizer_output.json" -not -path "*/.worktrees/*"
# (no output — artifact only generated on live import)
```

Most recent benchmark artifact (`w1_full50_after_streaming_20260526_190513/review_report.json`) structure: `status=pass`, `model=deepseek-v4-pro`, `profile=deep`, `reviewer_reports=[]` (pre-dates W2 refactoring).

### Phase 11: First-10-Chapter Experiment

**NOT RUN.** Requires Electron desktop app + valid API key + interactive operation. Cannot be automated from CLI.

---

## Files Consulted

```
AGENTS.md
dev_docs/README.md
dev_docs/DEV_RULES.md
communication/2026-06-04-w1-import-test13-defect-repair-report.md
communication/2026-06-04-w1-ai-import-orchestrator-delivery-report.md
communication/2026-06-05-w1-w7-integration-readiness-report.md
communication/2026-06-04-w2-reviewer-organizer-manifest-report.md
communication/2026-06-04-w1-worker3-timeline-sync-layout-report.md
communication/2026-06-04-w4-global-undo-report.md
communication/2026-06-04-w5-hierarchical-tags-report.md
communication/2026-06-04-w1-worker6-sidebar-graph-linkage-report.md
sidecar/workflows/w1_import.py (module load check)
sidecar/supervisor/ (module load check)
benchmark_results/w1_full50_after_streaming_20260526_190513/copied_artifacts/review_report.json
benchmark_results/w1_failure_closure_20260526_011743/smoke_10_chapter/凡人修仙传_前10章.txt
tests/e2e/p1/ (all 36 specs)
tests/ (44 Python test files, 255 targeted tests run)
```

---

## Deliverables

- `communication/2026-06-05-w1-import-ai-frontend-final-qa-report.md` — full PM QA report
- `dev_logs/2026-06-05-w7-integration-qa-log.md` — this file

---

## Issues Found

| ID | Severity | Description | Owner |
|----|----------|-------------|-------|
| QA-01 | P1 | `test_w1_orchestrator_artifacts.py` 2 stale fixture failures: expects `W1_EXTRACT_EVENTS_DEEP_ARC` for `fast` profile but W1 AI delivery correctly dispatches `W1_EXTRACT_EVENTS_DEEP_SPARSE`. Fix: update expected constant in 2 assertions. | W1 |
| QA-02 | P2 | `prompt_policy_decision.json` + `organizer_output.json` not yet observed in live context post-W1/W2 refactoring. Verify after first live import. | W1/W2 |
| QA-03 | P2 | `reviewer_reports` array in `review_report.json` was empty in all pre-W2 benchmark runs. Needs live confirmation that W2 reviewer output appears in this field. | W2 |
| QA-04 | P3 | 12 pre-existing Playwright failures in p1 suite unrelated to W1-W6 scope. Separate cleanup track needed. | Lead |
| QA-05 | P3 | `test_w1_v2_harness.py` 4 failures cascade from QA-01. Resolve by fixing QA-01. | W1 |
