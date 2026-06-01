# W1 Smoke Repair — Lead Integration Manager Report

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Author:** Claude Code (Lead Integration Manager)  
**Scope:** Lead initial patch — type contracts only; worker dispatch contracts defined

---

## Executive Summary

The W1 data pipeline is architecturally sound: W1 writes proposals → user accepts in Workbench → `projectService` reads split files from `writing/` and `entities/`. The defects are quality gaps, not structural failures.

The Lead's initial patch adds missing TypeScript type fields to unblock Workers C, D, E from writing their implementation code. The patch is minimal and non-breaking: no runtime behavior changes, no prompt changes, no graph changes.

**Go / No-Go for Worker dispatch:** **Go** — type contracts are in place, conflict matrix defined.

---

## Root Cause Diagnosis

| Defect | Severity | Root Cause | Owner |
|--------|----------|------------|-------|
| TypeScript missing `categoryPath/parentId` on `WorldItem` | P0 (blocks Worker D) | Fields never added to interface despite W1 writing them in proposals | Lead ✅ |
| TypeScript missing `globalOrderIndex` etc. on `TimelineEvent` | P0 (blocks Worker C) | Fields never added to interface | Lead ✅ |
| Timeline collapses to `branch_item` (36 events, 1 branch) | P0 | `_timeline_lane_key()` falls through to world category keys when `arcRole` is absent from LLM output | Worker C |
| World model contamination (`人物关系图`, `事件时间线`) | P1 | Organizer filter not catching these container names; old import data predates wiring | Worker D |
| Character duplicates (6 names × 2–3) | P1 | Reviewer repair proposals use wrong operation schema (`{type}` not `{op, entityType, fields}`) | Worker E |
| Chapter/scene content absent from Writing workspace | P0 | Split-file hydration code exists in `projectService.ts` lines 802–826; whether `WritingWorkspace` actually renders it is **unverified** | Worker A |
| Token/cost UX absent | P2 | No ledger emitted from sidecar; no UI card | Worker F |

---

## Files Changed

| File | Change |
|------|--------|
| `src/ui-react/models/project.ts` | Added `globalOrderIndex`, `chapterNumber`, `sourceChunkIds`, `sourceOrder` to `TimelineEvent`; added `categoryPath`, `parentId`, `importCategoryKey` to `WorldItem` |
| `src/ui-react/services/projectService.ts` | Added 4 new optional timeline event fields to schema metadata (documentation-only, line 611) |
| `communication/2026-06-01-w1-smoke-repair-lead-data-contracts.md` | Worker conflict matrix + canonical data contracts |
| `dev_logs/2026-06-01-w1-smoke-repair-lead.md` | Dev log |

---

## Test Results

### TypeScript Build

```
npm run ui:build
```

**Result: PASS** — 0 errors, built in 2.60s (1772 modules transformed)

### No pytest / Playwright changes in Lead patch

The Lead patch is pure type additions. No sidecar logic changed. No test regressions expected.

---

## Integration Decisions

### Decision 1: Type-only Lead patch

The Lead adds only type contracts. No runtime behavior changes. This keeps the Lead patch risk-free and preserves the zero-cost test baseline (97 pytest passing from previous session).

**Rationale**: Workers need stable TypeScript types to write their implementation code. Adding these types now unblocks parallel work.

### Decision 2: Split-file hydration marked as "needs verification"

`projectService.ts` lines 802–826 contain split-file hydration code. The code exists, but whether `WritingWorkspace` actually renders chapters/scenes from `project.chapters` (vs. stale local state) has **not been end-to-end verified** in this session.

Worker A must verify this with a real `import_test11` smoke test before this defect is marked resolved.

### Decision 3: `branch_item` root cause isolated to backend lane key fallthrough

`_timeline_lane_key()` (line 3117) returns tuples like `("theme", "item", ...)` when world-category keys appear in `arcId` or fall through theme classification. The branch ID format `f"branch_{lane_kind}_{_safe_branch_slug(lane_key)}"` then produces `branch_theme_item` or similar. Under certain conditions this can resolve to the literal `branch_item` ID used in the seed data.

Worker C owns this fix.

### Decision 4: Reviewer repair operation schema mismatch confirmed

`_collect_repair_proposals()` in `tools.py` emits:
```python
"operations": [{"type": action.get("action_type"), ...action.get("params", {})}]
```

Frontend `applyProposalOperation()` in `projectService.ts` reads `operation.op`, `operation.entityType`, `operation.entityId`, `operation.fields`. This mismatch means reviewer repair proposals silently no-op when accepted.

Worker E must fix the operation schema.

---

## Worker Matrix

| Worker | Priority | Unblocks | Key Files |
|--------|----------|----------|-----------|
| **A — Project Loader** | P0 | Manual smoke trust | `projectService.ts`, `WritingWorkspace.tsx` |
| **B — W1 Manuscript** | P1 | Summary/goal/notes in chapter cards | `w1_import.py` (manuscript nodes) |
| **C — Timeline Architect** | P0 | Meaningful branch topology | `w1_import.py` (timeline/branch nodes), `w1_prompts.py` |
| **D — World Hierarchy** | P1 | categoryPath rendering, contamination filter | `organizer.py`, `WorldWorkspace.tsx`, `models/project.ts` |
| **E — Character Dedupe** | P1 | Executable reviewer repair | `quality_reviewer.py`, `tools.py`, `projectService.ts` |
| **F — Token/Cost UX** | P2 | Import observability | `sidecar/routers/workflows.py`, `ImportWorkflow.tsx` |
| **G — Architecture** | P3 | Future orchestrator | Report only |
| **H — Verification** | P0 (after A-F) | Acceptance gate | Test suite + report |

---

## Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Split-file hydration end-to-end correctness | High | Code exists but unverified with real UI smoke; Worker A must confirm |
| Timeline branch inference with real LLM output | High | `branch_item` pollution depends on model-generated arcRole/arcId — synthetic tests can't cover all cases |
| Reviewer repair proposal schema — inbox proposals from previous import_test11 already use old schema | Medium | Old proposals in inbox.json are already broken; Worker E fix only applies to future imports |
| Worker B + C editing `w1_import.py` simultaneously | Medium | Must coordinate via merge or sequential edits; see conflict matrix |
| Worker A + D both editing `projectService.ts` | Medium | Must coordinate on function ownership before editing |

---

## Manual Smoke Instructions (pending Workers A-H)

After all workers complete, verify manually:

1. Open `import_test11` or a fresh copy.
2. Writing workspace shows chapters 第一章 → 第十章 in order.
3. No blank `Chapter 1 / Scene 1` starter visible.
4. Scene content is non-empty.
5. Timeline has >1 meaningful branch (not `branch_item` only).
6. Duplicate logistics events not repeated.
7. World Model has hierarchy groupings; no `人物关系图` or `事件时间线` containers.
8. Character duplicates reduced (岳堂主 × 2 → × 1, etc.).
9. Reviewer repair package accepted → character data actually changes.
10. Import UI shows token/cost estimate; no API key visible.

---

## Next Steps for User

Dispatch Workers A through G using copy blocks in `communication/2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md`.

Reference `communication/2026-06-01-w1-smoke-repair-lead-data-contracts.md` as the canonical data contract for all workers.

Suggested parallel dispatch order:
- Worker A (solo first — confirms UI smoke trust before others depend on it)
- Workers B + C in parallel (coordinate on `w1_import.py` ownership)
- Workers D + E in parallel (coordinate on `projectService.ts` ownership)
- Worker F (after A)
- Worker G (any time — report only)
- Worker H (after all implementation workers)
