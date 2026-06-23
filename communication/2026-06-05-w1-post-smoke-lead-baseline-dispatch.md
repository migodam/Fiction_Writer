# W1 Post-Smoke Lead Baseline + Dispatch — 2026-06-05

## Status: DISPATCHED

**DISPATCH_HASH:** `a92963756e875c1211dbc07c088109a64184e4c3` (short: `a929637`)  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Baseline gate:** 219 pytest PASS · npm run ui:build PASS  
**Untracked at dispatch:** `docs/superpowers/` (intentionally left alone)

---

## Defects Being Addressed

| # | Defect | Worker |
|---|--------|--------|
| 1 | Writing Studio has no visible Manuscript after W1 import | W1 |
| 2 | Import granularity choices are too few | W2 |
| 3 | Codex/Flash token billing shows unavailable | W2 |
| 4 | World Model taxonomy misroutes items (e.g. 项甲功 → 修炼境界与制度) | W4 |
| 5 | No drag-move of world items between category levels | W4 |
| 6 | Timeline Cmd+Z reverts to import-before state | W5 |

---

## Worker Worktrees

| Worker | Branch | Worktree Path |
|--------|--------|---------------|
| W1 | `codex/ps-w1-manuscript-pipeline` | `.worktrees/ps-w1-manuscript` |
| W2 | `codex/ps-w2-granularity-billing` | `.worktrees/ps-w2-granularity` |
| W4 | `codex/ps-w4-world-taxonomy-dragdrop` | `.worktrees/ps-w4-world-dragdrop` |
| W5 | `codex/ps-w5-timeline-undo` | `.worktrees/ps-w5-timeline-undo` |

All workers fork from **DISPATCH_HASH `a929637`**. Worker reports must record this hash in their report header.

---

## Worker Scope Summary

### W1 — Manuscript Canonical Pipeline
- **Files:** `sidecar/workflows/w1_import.py`, `sidecar/supervisor/tools.py` (if needed), `src/ui-react/services/projectService.ts`, `src/ui-react/store.ts`, `src/ui-react/components/WritingWorkspace.tsx`, `src/ui-react/components/ManuscriptWorkspace.tsx`
- **Forbidden:** Import billing, world drag/drop, timeline undo
- **Key deliverable:** Every imported chapter must produce ManuscriptNode entries visible in Writing Studio without user knowing internal paths

### W2 — Import Granularity + Token Billing
- **Files:** `src/ui-react/components/ImportWorkflow.tsx`, `src/ui-react/services/electronApi.ts`, `src/ui-react/store.ts`, `src/ui-react/services/appSettingsService.ts`, `sidecar/models/state.py` (if needed), `sidecar/workflows/w1_run_events.py`, `tests/test_w1_token_ledger.py`
- **Forbidden:** Manuscript, world drag/drop, timeline undo
- **Key deliverable:** Auto + 6 granularity presets visible in UI; Flash model alias in price table; unavailable reason always shown, never treated as $0

### W4 — World Taxonomy + Drag/Drop
- **Files:** `sidecar/supervisor/organizer.py`, `sidecar/supervisor/reviewers/quality_reviewer.py`, `src/ui-react/store.ts`, `src/ui-react/components/WorldWorkspace.tsx`, `src/ui-react/models/project.ts`
- **Forbidden:** Timeline undo, import billing
- **Key deliverable:** `classify_world_item()` with name-suffix scoring; `moveWorldItemToCategory()` store action; Playwright drag/drop World item between categories

### W5 — Timeline Undo Transaction Model
- **Files:** `src/ui-react/store.ts`, `src/ui-react/components/TimelineWorkspace.tsx`, `src/ui-react/components/timeline/TimelineCanvas.tsx`, `src/ui-react/components/timeline/TimelineOperations.ts`, `src/ui-react/services/projectService.ts` (if save/derive is root cause)
- **Forbidden:** Manuscript, import billing, world taxonomy
- **Key deliverable:** `beginUndoTransaction`/`commitUndoTransaction` API; drag commits one entry on pointerup only if canonical fields changed; import-accept boundary never left as top undo entry after a timeline drag

---

## Integration Rules (Lead-Owned)

1. Merge only worker commits where tests pass (pytest + npm run ui:build minimum).
2. Resolve conflicts by preserving canonical data contracts and existing W1 safety gates.
3. Do not merge a worker that mocks success without fixing the real code path.
4. `w1_import.py` shared surface: W1 may edit directly (this is their core scope); W4/W5 must not touch it.
5. `store.ts` shared surface: W2, W4, W5 all touch it — coordinate slice boundaries; each worker must isolate their slice. Lead applies conflicting changes manually.
6. `projectService.ts` shared surface: W1 and W5 may touch it — Lead arbitrates on conflict.

**Serial merge recommendation:** W2 → W1 → W4 → W5 (W2 has fewest `store.ts` conflicts; W5 has most complex `store.ts` interaction).

---

## Integration Gates (Lead Runs Before W6)

```bash
# Python compile gate
sidecar/.venv/bin/python -m py_compile \
  sidecar/workflows/w1_import.py \
  sidecar/supervisor/organizer.py \
  sidecar/supervisor/reviewers/quality_reviewer.py

# pytest gate
sidecar/.venv/bin/python -m pytest \
  tests/test_w1_import_compiler.py \
  tests/test_w1_organizer.py \
  tests/test_w1_reviewers_quality.py \
  tests/test_w1_reviewers_fact.py \
  tests/test_w1_reviewers_consistency.py \
  tests/test_w1_supervisor_tools.py \
  tests/test_w1_supervisor_policy.py \
  -q --tb=short

# (if W2 adds token ledger tests)
sidecar/.venv/bin/python -m pytest tests/test_w1_token_ledger.py -q --tb=short

# Frontend build
npm run ui:build

# Playwright targeted
npx playwright test --config tests/playwright.config.ts \
  tests/e2e/p1/import_activity_status.spec.ts \
  --reporter=list
```

W6 QA smoke runs only after all above are green on the integration branch.

---

## Hard Constraints

- No full50 run.
- No live API/model calls in Lead or W1–W5.
- Stop on 402 / insufficient balance, no retry.
- Do not stage `docs/superpowers/`, Playwright traces/videos, benchmark run dirs, API keys, or `.claude` files.
- All worker reports must record `DISPATCH_HASH: a929637` in their header.
- Do not delete `communication/` history files.

---

## Post-Worker Checklist (Lead)

- [ ] W1 report received; pytest + ui:build pass on W1 branch
- [ ] W2 report received; pytest + ui:build pass on W2 branch
- [ ] W4 report received; pytest + ui:build pass on W4 branch
- [ ] W5 report received; pytest + ui:build pass on W5 branch
- [ ] W2 merged (store.ts granularity slice)
- [ ] W1 merged (manuscript pipeline + store.ts)
- [ ] W4 merged (world taxonomy + store.ts moveWorldItemToCategory)
- [ ] W5 merged (timeline undo transactions + store.ts)
- [ ] Post-merge pytest gate: all 219+ pass
- [ ] Post-merge npm run ui:build: PASS
- [ ] Post-merge targeted Playwright specs: PASS
- [ ] Lead integration report written
- [ ] W6 authorized for 10-ch smoke (only after above)
