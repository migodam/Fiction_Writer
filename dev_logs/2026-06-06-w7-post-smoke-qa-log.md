# Worker W7 — Post-Smoke QA Log

**Date:** 2026-06-06  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Worker:** W7 (Integration QA)

---

## Timeline

### Phase 1: Git state + changed file inventory

```bash
git diff main --name-only | grep '\.py$'
# 20 changed Python files (state.py, tools.py, organizer.py, policy.py,
#   prompt_policy.py, quality.py, reviewers/*, pipeline_tools.py, etc.)
```

### Phase 2: py_compile

```bash
git diff main --name-only | grep '\.py$' | xargs python -m py_compile && echo OK
# exit: 0 — OK
```

### Phase 3: run_harness --no-write

```bash
source sidecar/.venv/bin/activate
python benchmark_results/v2_planner_dry_run/run_harness.py --no-write
# case_1_10ch_zh_deep:   PASS
# case_2_50ch_zh_deep:   PASS
# case_3_40ch_en_deep:   PASS
# case_4_20ch_en_balanced: PASS
# case_5_10ch_en_fast:   PASS
# Secret scan: CLEAN
# Summary: 5/5 passed
# [GATED_LIVE_SMOKE] Skipped
```

Note: `case_5_10ch_en_fast` now PASSES — this was QA-01 in the previous session (stale fixture expecting `W1_EXTRACT_EVENTS_DEEP_ARC` instead of `W1_EXTRACT_EVENTS_DEEP_SPARSE`).

### Phase 4: Targeted pytest W1-W6

```bash
python -m pytest tests/test_w1_organizer.py tests/test_w1_supervisor_tools.py \
  tests/test_w1_supervisor_policy.py tests/test_w1_manifest_revision_schema.py \
  tests/test_w1_quality_rubric.py tests/test_w1_reviewers_quality.py \
  tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py \
  tests/test_w1_prompt_policy_selection.py tests/test_w1_token_ledger.py \
  tests/test_w1_pipeline_tools.py tests/test_w1_run_events.py -q
# 265 passed in 0.89s
```

### Phase 5: Orchestrator artifacts (previously QA-01)

```bash
python -m pytest tests/test_w1_orchestrator_artifacts.py -q
# 57 passed in 0.52s
```

Previously 55/57 (2 stale failures on fast profile). Now all 57 pass. QA-01 resolved.

### Phase 6: Full pytest

```bash
python -m pytest tests/ -q
# 585 passed, 11 failed, 7 errors in 6.26s
```

All failures/errors are pre-existing legacy v2/v3 (same as main branch baseline, confirmed in previous session). Zero W1-W6 regressions.

### Phase 7: npm ui:build

```bash
npm run ui:build 2>&1 | tail -5
# ✓ 1773 modules transformed. ✓ built in 2.52s. BUILD_EXIT: 0
```

### Phase 8: Playwright W1-W6 owned specs

```bash
npm run test:e2e -- --project=chromium [14 owned spec files]
# 110 passed (1.2m)
```

+2 vs previous session (108 → 110).

### Phase 9: Playwright full p1 suite

```bash
npm run test:e2e -- --project=chromium tests/e2e/p1/
# 151 passed (4.3m)
```

Previously 129/141 (12 failures). All 12 previously-failing specs now pass. 151/151 clean.

### Phase 10: Artifact schema simulation (zero-cost)

Run synthetic Python script to validate artifact schemas without live LLM calls.

#### 10a. API discovery (needed to fix wrong import names)

```bash
python -c "import sidecar.supervisor.prompt_policy as m; print(dir(m))"
# prompt_policy_decision (function), not select_prompt_policy

python -c "import sidecar.supervisor.reviewers.schemas as m; print(dir(m))"
# ReviewReport (TypedDict), not ReviewSession
```

#### 10b. Synthetic validation results

```
[PASS] prompt_policy_decision: chosen_density='chapter_level', directive_keys=10, rationale_lines=3
[PASS] organizer_output: world_items=2, excluded=1, packages=2
       七玄门 categoryPath=['世界模型', '门派组织', '七玄门']
       长春功 categoryPath=['世界模型', '功法与术法', '长春功']
[PASS] QualityReviewer.review(): reviewer='quality', verdict='warn', severity='medium'
       findings=1, repairs=0
[PASS] review_report.json reviewer_reports: 1 entry
[PASS] ConsistencyReviewer.manifest_revision_diffs present: 0 entries

All 4 artifact schema checks PASSED
exit: 0
```

### Phase 11: Live 10-chapter smoke

NOT RUN. Requires Electron desktop app + valid API key + explicit Lead approval.

---

## Issues Table

| ID | Severity | Description | Resolution |
|----|----------|-------------|------------|
| QA-01 | P1 | Stale fixture: fast profile expected `W1_EXTRACT_EVENTS_DEEP_ARC` | **FIXED** — 57/57 pass |
| QA-02 | P2 | `prompt_policy_decision.json` not yet live | Synthetic schema PASS; live needs first import |
| QA-03 | P2 | `organizer_output.json` not yet live | Same |
| QA-04 | P3 | 12 pre-existing Playwright p1 failures | **FIXED** — 151/151 clean |
| QA-05 | P3 | v2 harness cascade from QA-01 | **FIXED** (resolved via QA-01) |
| QA-06 | P2 | reviewer_reports array live confirmation | Synthetic PASS; live needs first import |
| LIVE-01 | P1 | 10-chapter live smoke not run | Awaiting Lead approval + API key |

---

## Deliverables

- `communication/2026-06-06-w7-post-smoke-final-qa-report.md` — full PM QA report
- `dev_logs/2026-06-06-w7-post-smoke-qa-log.md` — this file
