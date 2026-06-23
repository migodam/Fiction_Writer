# W6 — Sidebar Collapse & Relationship Graph Linkage: Delivery Report
**Date:** 2026-06-04  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** W6

## What Was Delivered

Sidebar folder collapse state and relationship graph node visibility are now linked. Collapsing a sidebar group hides those characters' nodes from the graph; expanding re-includes them. A filter chip strip in the graph header allows direct per-group filtering that also drives the sidebar. All state is session-only — no character data is mutated.

## Files Changed

| File | Change |
|------|--------|
| `src/ui-react/store.ts` | Added `graphImportanceFilter: string[]`, `characterGroupCollapsed: Record<string, boolean>`, `graphSidebarLinkageEnabled: boolean` + 4 setter actions. Volatile — not persisted. Fixed `saveProject` to preserve volatile fields across saves. |
| `src/ui-react/components/graph/CharacterRelationshipFlow.tsx` | Filters `characters` and `relationships` via `graphImportanceFilter` before building ReactFlow nodes/edges. Orphaned edges excluded. |
| `src/ui-react/components/CharactersWorkspace.tsx` | Migrated `collapsed` from local state to store. `handleGroupToggle` calls `toggleCharacterGroupCollapsed`. `useEffect` derives `graphImportanceFilter` from collapse state when linkage is on. Added `data-testid` to group headers. Added filter chip strip + linkage toggle to `RelationshipGraphPanel`. |
| `tests/e2e/p1/graph_sidebar_linkage.spec.ts` | 3 Playwright acceptance tests (3/3 passing). |
| `dev_docs/TEST_SELECTORS.txt` | 4 new selector entries registered. |

## UI Behavior Table

| Action | Linkage ON | Linkage OFF |
|--------|------------|-------------|
| Collapse sidebar group | Graph hides group nodes + orphaned edges | Sidebar collapses only |
| Expand sidebar group | Graph shows group nodes | Sidebar expands only |
| Click filter chip (e.g. "supporting") | Graph hides group + sidebar collapses group | Graph hides group only |
| Click "All" chip | Graph shows all + sidebar expands all | Graph shows all only |
| Click "Linked" toggle | Turns linkage off (decouples surfaces) | Turns linkage on |

## Persistence Decision

All three new state fields (`graphImportanceFilter`, `characterGroupCollapsed`, `graphSidebarLinkageEnabled`) are **session-only**:
- Initialized to defaults (`[]`, `{}`, `true`) on project open/create/load.
- Not written to the project file (`cloneProject` serialization path untouched).
- Preserved across auto-saves (fixed in `saveProject`).
- Reset on project switch.

## Data Integrity

`Character.importance` values are never written by any filter operation. The filter state is purely a display mask. Confirmed by test 3 (card count unchanged after filter round-trip).

## Manual Smoke Checklist

1. Open any project with characters in multiple groups.
2. Navigate to Characters → Relationship Graph.
3. Click a filter chip (e.g. "supporting") → supporting nodes disappear from graph AND supporting group collapses in sidebar.
4. Click "All" → all nodes reappear, all groups expand.
5. Collapse a sidebar group manually → graph hides those nodes.
6. Click "Linked" toggle → sidebar collapse no longer affects graph.
7. Re-enable linkage → sync resumes on next collapse/expand.
8. Verify: no `importance` field changed on any character throughout.

## Test Results

| Suite | Result |
|-------|--------|
| `tests/e2e/p1/graph_sidebar_linkage.spec.ts` | 3/3 PASS |
| `npm run ui:build` | Clean (0 new errors) |
| `npm run ui:lint` | Clean |
