# W6 Dev Log — Sidebar Collapse & Relationship Graph Linkage
**Date:** 2026-06-04  
**Branch:** codex/w1-orchestrated-import-quality

## Changes Made

### src/ui-react/store.ts
- Added 3 volatile (non-persisted) state fields: `graphImportanceFilter: string[]`, `characterGroupCollapsed: Record<string, boolean>`, `graphSidebarLinkageEnabled: boolean`
- Added 4 setter actions: `setGraphImportanceFilter`, `setCharacterGroupCollapsed`, `toggleCharacterGroupCollapsed`, `setGraphSidebarLinkageEnabled`
- Fixed `saveProject` to preserve volatile fields across auto-saves (restore from `get()` before spreading `deriveState`)

### src/ui-react/components/graph/CharacterRelationshipFlow.tsx
- Added `graphImportanceFilter` read from store
- Added `visibleChars` and `visibleCharIds` and `visibleRelationships` derivation memos
- Graph now renders only visible characters + edges where both endpoints are visible
- Removed redundant `initialNodes`/`initialEdges` useMemo hooks (only used as `useNodesState` seed)

### src/ui-react/components/CharactersWorkspace.tsx
- Migrated local `collapsed` useState to `characterGroupCollapsed` from store
- `handleGroupToggle` simplified to call `toggleCharacterGroupCollapsed` only
- Added `useEffect` that derives `graphImportanceFilter` from collapse state when linkage is on
- Added `data-testid="character-group-header-{group}"` to all group header buttons
- Added filter chip strip to `RelationshipGraphPanel` header with per-group chips, "All" chip, and linkage toggle

### tests/e2e/p1/graph_sidebar_linkage.spec.ts
- 3 Playwright acceptance tests covering: chip visual state change, reverse un-hide, and data integrity after filter round-trip

### dev_docs/TEST_SELECTORS.txt
- 4 new entries: `character-group-header-{group}`, `graph-importance-filter-all`, `graph-importance-filter-{imp}`, `graph-sidebar-linkage-toggle`

### communication/2026-06-04-w1-worker6-sidebar-graph-linkage-report.md
- PM delivery report with behavior table, persistence decision, smoke checklist

## Tests Executed

| Suite | Result |
|-------|--------|
| `tests/e2e/p1/graph_sidebar_linkage.spec.ts` | 3/3 PASS |
| `npm run ui:build` | Clean (0 new errors) |
| `npm run ui:lint` | Clean |
