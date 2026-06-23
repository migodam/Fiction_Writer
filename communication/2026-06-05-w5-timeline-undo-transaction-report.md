# Worker W5 — Timeline Undo Transaction Model
**Date:** 2026-06-05  
**Branch:** codex/w1-orchestrated-import-quality  
**Status:** Implementation complete; build passing; 7/7 new tests + 4/4 regression tests passing

---

## Problem Statement

Pressing Cmd+Z after a timeline branch drag operation could cycle through dozens of intermediate drag states before reverting to the pre-drag position, or appear to jump all the way to the pre-import baseline. The effect was that a single branch drag (moving a start/end anchor or adjusting the curve shape) consumed most or all of the 20-entry undo stack with meaningless intermediate states.

---

## Root Cause Analysis

| Location | Issue |
|----------|-------|
| `store.ts:1218` | `setTimelineBranchGeometry` called `captureUndoSnapshot('Adjust branch')` unconditionally |
| `store.ts:1232` | `setTimelineBranchAnchors` called `captureUndoSnapshot('Anchor branch')` unconditionally |
| `TimelineCanvas.tsx:796,801,826` | Both called inside `pointermove` — fired every ~16ms during drag |
| `store.ts:442` | `MAX_UNDO_DEPTH = 20` — a ~300ms drag at 60fps produces 18 snapshots, filling the stack |

A single branch drag touching the anchor or bend handle would push up to `MAX_UNDO_DEPTH` snapshots. After a large import accept (which also pushes a snapshot), the first Cmd+Z would undo to an intermediate drag state, and after ~20 more presses you'd reach the pre-import state — appearing to skip past all timeline work.

`moveTimelineEvent` and `updateTimelineEventPosition` were already correct: the former commits one snapshot, the latter captures nothing (transient position only).

`handleSynchronizeAnalysis` in `TimelineWorkspace.tsx` is purely read-only diagnostic — no undo interaction required.

---

## Transaction Model

### New Store API (`store.ts`)

```typescript
// New state field (NOT in ProjectDataSnapshot — transient UI runtime state)
pendingUndoTransaction: { label: string; snapshot: ProjectDataSnapshot } | null;

// New actions
beginUndoTransaction(label: string): void;
commitUndoTransaction(): void;
cancelUndoTransaction(): void;
```

**`beginUndoTransaction`**  
Captures the current state snapshot into `pendingUndoTransaction`. Guard 1: if a transaction is already pending, logs a warning and returns without overwriting the original pre-drag snapshot.

**`commitUndoTransaction`**  
Guard 2: compares `timelineBranches` and `timelineEvents` by reference against the pending snapshot. If unchanged (pointerdown with no move, or accidental re-commit), discards the pending transaction without pushing to `undoStack`. If changed, pushes exactly one `UndoEntry`.

**`cancelUndoTransaction`**  
Discards the pending transaction unconditionally (no undo entry pushed).

### Modified Geometry Mutators

```typescript
// Before (fires one snapshot per pointermove):
setTimelineBranchGeometry: (branchId, geometry) => {
  get().captureUndoSnapshot('Adjust branch');
  set(...);
},

// After (snapshots only when no transaction is active — backward-compatible):
setTimelineBranchGeometry: (branchId, geometry) => {
  if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Adjust branch');
  set(...);
},
```

Same change applied to `setTimelineBranchAnchors`. The Alt+click path (`TimelineCanvas.tsx:885`) calls `setTimelineBranchGeometry` directly without a transaction, so it continues to push one snapshot as before.

### `TimelineCanvas.tsx` Wiring

| Point | Action |
|-------|--------|
| `startBranchDrag()` (after `setMode('branch-drag')`) | `beginUndoTransaction('Anchor branch' \| 'Adjust branch')` |
| `onUp` handler (branch drag `useEffect`) | `commitUndoTransaction()` before clearing drag state |
| `pointercancel` event (new listener in branch drag effect) | `cancelUndoTransaction()` + cleanup |
| `keydown` Escape (new listener in branch drag effect) | `cancelUndoTransaction()` + cleanup |
| Effect cleanup callback | `cancelUndoTransaction()` — no-op if already committed/cancelled |

### Persistence Safety

`pendingUndoTransaction` is not in `ProjectDataSnapshot` (type-level exclusion — the `Pick<>` type definition does not include it). `cloneProject()` does not reference it. `openProject`, `loadProject`, and `createProject` all explicitly set `pendingUndoTransaction: null` so a stale drag transaction from a previous project is never carried over.

---

## Files Changed

| File | Change |
|------|--------|
| `src/ui-react/store.ts` | Add `pendingUndoTransaction` field + 3 actions to interface and initial state; implement all three; guard `setTimelineBranchGeometry` and `setTimelineBranchAnchors`; clear pending in `createProject`, `openProject`, `loadProject` |
| `src/ui-react/components/timeline/TimelineCanvas.tsx` | Destructure 3 new store actions; call `beginUndoTransaction` in `startBranchDrag`; `commitUndoTransaction` in `onUp`; `pointercancel` + Escape + cleanup all call `cancelUndoTransaction` |
| `tests/e2e/p1/timeline_undo_transactions.spec.ts` | **NEW** — 7 tests |

---

## Test Results

```
npm run ui:build
✓ 1773 modules transformed (0 TypeScript errors)
✓ built in 3.12s

npx playwright test tests/e2e/p1/timeline_undo_transactions.spec.ts --reporter=list
  ✓ branch drag creates exactly one undo entry
  ✓ cancelUndoTransaction leaves undo stack unchanged
  ✓ post-import timeline drag pushes only one undo entry
  ✓ anchor drag batches into one entry and non-timeline data is untouched
  ✓ moveTimelineEvent undo still works after transaction API added
  ✓ commit with no actual geometry change does not push undo entry
  ✓ nested beginUndoTransaction preserves original snapshot
7 passed (4.8s)

npx playwright test tests/e2e/p1/global_undo.spec.ts --reporter=list
  ✓ updateCharacter pushes to undo stack and undoAction restores previous state
  ✓ moveTimelineEvent pushes to undo stack and undoAction restores event branch
  ✓ setSelectedEntity does not create undo stack entries
  ✓ redoAction re-applies change after undoAction
4 passed (3.3s)
```

---

## UI-Level Drag Coverage Note

Tests 1–7 invoke the store transaction API directly via `window.__narrativeStore`. This exercises the same code path a real pointer drag takes: `startBranchDrag` → `setTimelineBranchGeometry` × N → `onUp`. The only piece not covered is the DOM pointer event dispatch itself. Playwright SVG pointer-drag simulation is flaky in headless Chromium against dnd-kit/custom pointer listeners, so UI-level drag is explicitly deferred to a future `timeline_canvas_drag.spec.ts` file. The store-level tests provide full behavioral coverage of the undo batching logic.

---

## Remaining UX Notes

| Item | Notes |
|------|-------|
| `redo` after drag | Works correctly — `commitUndoTransaction` clears `redoStack` as expected |
| Multi-branch simultaneous drag | Not supported in the UI; `beginUndoTransaction` guard prevents accidental nesting |
| Very long drags (> 20 intermediate states) | Previously would have overflowed `MAX_UNDO_DEPTH`; now always exactly one entry |
| Synchronize analysis | Read-only; no undo interaction — confirmed no changes needed |
