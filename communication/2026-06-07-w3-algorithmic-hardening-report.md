# W3 Algorithmic Hardening — Delivery Report

**Date:** 2026-06-07  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Domain:** UI algorithmic hardening — World Model, Timeline Undo, Relationship Graph  
**Status:** COMPLETE — 22/22 tests pass, `npm run ui:build` zero TS errors

---

## Executive Summary

W3 hardened three algorithmic subsystems with correctness issues uncovered during investigation:

1. **World Model** — `wcat_root` hidden-root orphan bug fixed, `categoryId`-stable item grouping, undo wired to `addWorldCategory` + `moveWorldCategory` + `moveWorldItemToCategory`
2. **Timeline Undo** — Event drag wrapped in `beginUndoTransaction`/`commitUndoTransaction`, new `rollbackUndoTransaction` for Escape cancel, snapshot includes both state and `undoStack`
3. **Relationship Graph** — Three pure layout modes (`radial`, `cluster`, `force-lite`), AABB label collision guard, deterministic force-lite via `id.localeCompare()` sort, layout toggle UI with `data-testid`

---

## Test Results

| File | Tests | Result |
|---|---|---|
| `world_hierarchy.spec.ts` | 8 (4 existing + 4 new) | ✅ 8/8 PASS |
| `timeline_undo_transactions.spec.ts` | 10 (7 existing + 3 new) | ✅ 10/10 PASS |
| `character_relationship_flow_layout.spec.ts` | 4 (2 existing + 2 new) | ✅ 4/4 PASS |
| **Total** | **22** | **✅ 22/22 PASS** |

Build: `npm run ui:build` — zero TypeScript errors, zero type regressions.

---

## Detailed Changes

### B1 — World Model (`store.ts` + `WorldWorkspace.tsx`)

**Root cause found — `wcat_root` orphan bug:**  
`TagTreePanel.flattenTree` treats nodes as roots only when `resolveParentId(n) === null`. Filtering `wcat_root` from the array while its children still carried `parentId: 'wcat_root'` (non-null) made them invisible orphans. Fix: `visibleCategories` useMemo both filters hidden roots AND remaps direct children's `parentId` to `null`.

**`worldCategories` missing from `ProjectDataSnapshot`:**  
The `Pick<ProjectState, ...>` union at line 455 lacked `'worldCategories'`. Any `captureUndoSnapshot` call before this fix captured state that could not restore world categories on undo. Added `| 'worldCategories'` to the Pick union and `worldCategories: state.worldCategories` to `extractSnapshot`.

**Undo wiring:**  
- `addWorldCategory`: added `captureUndoSnapshot('Add world category')` guard before `set(...)`
- `moveWorldCategory`: converted from `set(state => ...)` return form to imperative form to allow side-effect snapshot before mutation
- `moveWorldItemToCategory`: extended signature with `newCategoryId?` + `newParentId?`, writes `categoryId` field, guards with `captureUndoSnapshot`

**`groupedItems` useMemo:**  
Primary key changed from `item.categoryPath[1]` (mutable display string) to `item.categoryId` with name fallback, so stable ID-based filtering works across category renames.

### B2 — Timeline Undo (`store.ts` + `TimelineCanvas.tsx`)

**`cancelUndoTransaction` does not restore state:**  
Original implementation only cleared `pendingUndoTransaction: null` — it did NOT restore the before-state. During event drag, `updateTimelineEventPosition` writes intermediate positions to `timelineEvents`. Pressing Escape while mid-drag left the event at the drag position with no undo entry.

**`rollbackUndoTransaction` added:**  
New action restores `pending.snapshot` (all state fields) AND `pending.undoStack` (prevents orphaned entries from initialization racing with `beginUndoTransaction`).

**`pendingUndoTransaction` type extended:**  
Added `undoStack: UndoEntry[]` to the pending transaction object. `beginUndoTransaction` captures the current stack at open time. `commitUndoTransaction` uses saved stack as the base, so new entries from concurrent initializations are properly isolated.

**`moveTimelineEvent` guard:**  
Added `if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Move event')` so calling it inside an open transaction doesn't push a double entry.

**`startEventDrag` → `commitEventDrag` flow:**  
- `startEventDrag`: `beginUndoTransaction('Move event')` captures before-state (branchId + position)
- `commitEventDrag`: `commitUndoTransaction()` after all mutations — one entry, correct before-state
- Escape keydown + `pointercancel`: `rollbackUndoTransaction()` restores to before-drag state with zero undo entries

**Initialization race fix:**  
Tests set `{ undoStack: [], redoStack: [], pendingUndoTransaction: null }` after injection and navigate to `/timeline` directly (not `/`) so React app startup's `addWorldCategory` calls don't corrupt `stackBefore`.

### B3 — Relationship Graph (`CharacterRelationshipFlow.tsx`)

**Pure layout functions extracted:**  
- `buildRadialNodes` (renamed from `buildNodes`) — existing radial ellipse layout
- `buildClusterNodes` — tier-columns layout: core/major/supporting/minor sorted by degree within each tier column
- `buildForceLiteNodes` — Fruchterman-Reingold force-directed with deterministic seeding (sorted by `id.localeCompare()`, circle init, integer rounding throughout, no `Math.random`)
- `resolveNodeLabelCollisions` — AABB guard: bumps Y by 16px per overlap pass, anchored to importance rank

All four functions are stateless (no hooks, no React), defined before the component.

**Component wiring:**  
`useState<GraphLayoutMode>('radial')` controls layout selection. `useCallback buildByMode` dispatches to the correct function. `useEffect` recalculates nodes on char/rel/mode changes. Layout toggle buttons rendered with `data-testid="graph-layout-mode-{radial|cluster|force-lite}"`.

---

## Bugs Found During Investigation

| Bug | Severity | Status |
|---|---|---|
| `wcat_root` children become invisible orphans when root is filtered | High | Fixed |
| `worldCategories` absent from `ProjectDataSnapshot` Pick union | High | Fixed |
| `cancelUndoTransaction` does not restore state | Critical | Fixed (new `rollbackUndoTransaction`) |
| `moveTimelineEvent` calls `captureUndoSnapshot` unconditionally (double-entry inside transaction) | High | Fixed |
| Timeline Escape during drag leaves event at drag position with no undo entry | High | Fixed |
| Initialization race: `addWorldCategory` undo entries corrupt `stackBefore` in tests | Medium | Fixed (test setup resets stack) |
| `groupedItems` uses display string as primary key (breaks on rename) | Medium | Fixed (`categoryId`-primary) |
| `moveWorldItemToCategory` never writes `categoryId` field | Medium | Fixed |

---

## Acceptance Matrix — Final State

| ID | Criterion | Result |
|---|---|---|
| W-5 | wcat_root children visible as top-level nodes | ✅ PASS |
| W-6 | categoryId-based item filter | ✅ PASS |
| W-7 | addWorldCategory undo reversible | ✅ PASS |
| W-8 | moveWorldCategory undo reversible | ✅ PASS |
| W-1–4 | existing world_hierarchy regressions | ✅ PASS |
| TL-9 | real pointer drag → 1 undo, Meta+Z restores | ✅ PASS |
| TL-10 | Escape during drag → 0 undo, position restored | ✅ PASS |
| TL-11 | chapter data survives event drag undo | ✅ PASS |
| TL-1–7 | existing branch drag undo regressions | ✅ PASS |
| G-cluster | cluster layout tier column separation >100px | ✅ PASS |
| G-force-lite | force-lite determinism ±5px | ✅ PASS |
| G-1 | radial distribution (existing) | ✅ PASS |
| G-2 | edge label overlap (existing) | ✅ PASS |
| Build | `npm run ui:build` zero TS errors | ✅ PASS |

---

## Files Modified

| File | Change Type |
|---|---|
| `src/ui-react/store.ts` | feat: worldCategories in snapshot, rollbackUndoTransaction, undo guards for world actions and moveTimelineEvent, pendingUndoTransaction extended with undoStack |
| `src/ui-react/components/WorldWorkspace.tsx` | feat: visibleCategories useMemo (hidden root promotion), categoryId-primary groupedItems, pass targetFolderNode?.id to moveWorldItemToCategory |
| `src/ui-react/components/timeline/TimelineCanvas.tsx` | feat: wrap event drag in begin/commitUndoTransaction, add rollback on Escape/pointercancel |
| `src/ui-react/components/graph/CharacterRelationshipFlow.tsx` | feat: buildClusterNodes, buildForceLiteNodes, resolveNodeLabelCollisions, GraphLayoutMode, layout toggle buttons |
| `tests/e2e/p1/world_hierarchy.spec.ts` | test: add Tests 5-8 (hidden root, categoryId filter, addWorldCategory undo, moveWorldCategory undo) |
| `tests/e2e/p1/timeline_undo_transactions.spec.ts` | test: add Tests 9-11 (pointer drag undo, Escape cancel, chapter guard) |
| `tests/e2e/p1/character_relationship_flow_layout.spec.ts` | test: add cluster tier-column and force-lite determinism tests |

---

## Deferred (out of scope for W3)

- `WorldItem.parentId` sub-item nesting UI (parentId field preserved, tree nesting UI not built)
- Graph layout persistence to Zustand store or disk (transient `useState` only)
- `commitUndoTransaction` world-operation path (world ops still use `captureUndoSnapshot` directly, not transaction API, since the no-op check is timeline-scoped)
