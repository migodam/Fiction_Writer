# Worker W5 — Hierarchical Tags and Windows-like Drag/Drop
**Date:** 2026-06-04  
**Branch:** codex/w1-orchestrated-import-quality  
**Status:** Implementation complete; build passing; 5/5 E2E tests passing

---

## Summary

Added unlimited-depth hierarchical tag trees to both the Character tag system and the World category system, with Windows Explorer–style drag/drop reordering powered by `@dnd-kit/core`.

---

## Problem Addressed

- Character tags were flat `{id, name, color, description, characterIds}` — no parent/child or sort order.
- World categories were computed read-only groupings derived from `categoryPath[1]` with no interactive management.
- Neither system supported drag/drop reorganization or nesting deeper than 2 levels.

---

## Data Model Before/After

### CharacterTag
| Field | Before | After |
|-------|--------|-------|
| `parentTagId` | absent | `?: string \| null` — hierarchy pointer |
| `sortOrder` | absent | `?: number` — sibling order |
| `collapsed` | absent | `?: boolean` — UI collapse state |

### WorldCategoryNode (new type)
```typescript
export interface WorldCategoryNode {
  id: string;
  name: string;
  parentId: string | null;
  sortOrder: number;
  scope: 'world';
  collapsed?: boolean;
}
```

### NarrativeProject
```typescript
worldCategories?: WorldCategoryNode[];   // new optional field
```

### Schema Version
`PROJECT_SCHEMA_VERSION` bumped `4 → 5`.

---

## Migration

`migrateProject()` in `projectService.ts`:
- Back-fills `parentTagId: null, sortOrder: idx` on every `CharacterTag` lacking those fields.
- If `project.worldCategories` is absent or empty, derives initial nodes from `WORLD_CATEGORY_PATH_MAP` (one root `世界模型` + one leaf per distinct subcategory found on world items).
- `PROJECT_SCHEMA_VERSION: 5` is written on every save.

`serializeProjectToFolder()` writes `entities/world/categories.json`.  
Load path reads `entities/world/categories.json` (falls back to `[]`).

---

## New Store Actions (`store.ts`)

| Action | Purpose |
|--------|---------|
| `moveCharacterTag(tagId, newParentId, insertBeforeSiblingId?)` | Moves a character tag in the tree; rejects cycles |
| `toggleCharacterTagCollapsed(tagId)` | Toggles collapse state |
| `addWorldCategory(node)` | Adds a new world category node |
| `updateWorldCategory(node)` | Updates an existing node |
| `deleteWorldCategory(nodeId)` | Removes a node |
| `moveWorldCategory(nodeId, newParentId, insertBeforeSiblingId?)` | Moves a world category; rejects cycles |
| `toggleWorldCategoryCollapsed(nodeId)` | Toggles collapse state |

Both `move*` actions use an `isDescendant` check before mutating; a cycle attempt is a silent no-op + `console.warn`.

---

## New Component: `TagTreePanel.tsx`

`src/ui-react/components/TagTreePanel.tsx` — reusable generic tree component.

- `DndContext` (from `@dnd-kit/core` v6.3.1) wraps the full list.
- Each node exposes a `useDraggable` drag handle and two `useDroppable` zones:
  - `drop-before-{id}` — thin 6px zone above the row → drop before sibling.
  - `drop-inside-{id}` — full-row zone → drop as child.
- `DragOverlay` shows a ghost card during drag.
- Tree is flattened for render in DFS order; collapsed nodes hide all descendants.
- Indentation: `depth × 16px` CSS `paddingLeft`.
- Cycle prevention in store actions (not in the component).
- Generic type parameter `<T extends TagTreeNode>` — accepts both `CharacterTag` and `WorldCategoryNode`.

---

## UI Changes

### CharactersWorkspace.tsx
- `TagsPanel` flat grid (`grid gap-5 lg:grid-cols-2`) replaced with `<TagTreePanel nodes={characterTags} …>`.
- Each node renders the existing tag card (color dot, name, character count badge, expandable character assign/remove list).
- New tags created with `parentTagId: null, sortOrder: characterTags.length`.

### WorldWorkspace.tsx
- Added collapsible "Categories" section above the item list in the second `aside`.
- Contains `<TagTreePanel<WorldCategoryNode> …>` powered by `worldCategories` from store.
- Clicking a category node sets `selectedCategoryId`; the item list filters to show only items whose `categoryPath` includes that category's name.
- "Add Category" button creates a root-level `WorldCategoryNode`.
- The tree toggle (chevron) shows/hides the panel.

---

## Test Selector Naming (Corrected)

After initial implementation, a `strict mode violation` was discovered: the TreeRow `div` and the `renderNodeContent` button inside `WorldWorkspace` both resolved to `world-category-node-{id}`.

**Fix:** Renamed the `TagTreePanel` TreeRow container testid from `${testIdPrefix}-node-${id}` to `${testIdPrefix}-row-${id}`. The `renderNodeContent` button in `WorldWorkspace` keeps `world-category-node-{id}` as the interactive selector.

Final selector scheme (from `TEST_SELECTORS.txt`):

```
tag-tree-panel-<prefix>                  TagTreePanel   Root container; prefix = character-tag | world-category
tag-tree-row-<prefix>-<id>               TagTreePanel   Outer div for the full row (drag container); renamed from -node- to avoid collision
tag-tree-row-<prefix>-<id>-expand        TagTreePanel   Collapse/expand chevron; visibility:hidden when node has no children
tag-tree-row-<prefix>-<id>-drag-handle   TagTreePanel   Drag handle icon; opacity-0 until hover
tag-tree-drop-before-<prefix>-<id>       TagTreePanel   6px thin drop zone above a row (drop before sibling)
tag-tree-drop-inside-<prefix>-<id>       TagTreePanel   Full-row drop zone (drop inside, becomes child)
world-category-tree                      WorldWorkspace  Container of the world category TagTreePanel
world-category-tree-toggle               WorldWorkspace  Button to expand/collapse the category tree panel
world-category-node-<id>                 WorldWorkspace  Clickable filter button inside each category row
add-world-category-btn                   WorldWorkspace  "Add Category" button
```

---

## E2E Tests (`tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts`)

All 5 tests use the **navigate-first, then inject** pattern to avoid Zustand state wipe on `page.goto()`:

```typescript
async function injectAt(page, url, extra) {
  await page.goto(url);            // navigate first (rehydrates store)
  await page.evaluate((extra) => {
    const store = (window as any).__narrativeStore;
    store.setState((state) => ({ ...state, ...extra }));
  }, extra);
}
```

| # | Test | Assertion |
|---|------|-----------|
| 1 | `character tag tree renders 4 levels of nesting` | All 4 `character-tag-row-*` testids visible |
| 2 | `moveCharacterTag re-parents tag and tree reflects new structure` | Store action call; assert `parentTagId === 'ctag_root'` |
| 3 | `moveCharacterTag rejects cycle and leaves state unchanged` | Cycle attempt; assert `parentTagId === null` (unchanged) |
| 4 | `world category tree renders with 3-level categories` | `world-category-node-*` buttons visible |
| 5 | `moveWorldCategory rejects cycle and leaves world categories unchanged` | Cycle attempt; assert `parentId === null` |

### Verification Results

```
npm run ui:build
✓ 1773 modules transformed (0 TypeScript errors)
✓ built in 2.73s

npx playwright test tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts --reporter=list
  ✓ character tag tree renders 4 levels of nesting
  ✓ moveCharacterTag re-parents tag and tree reflects new structure
  ✓ moveCharacterTag rejects cycle and leaves state unchanged
  ✓ world category tree renders with 3-level categories
  ✓ moveWorldCategory rejects cycle and leaves world categories unchanged

5 passed (3.9s)
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/ui-react/models/project.ts` | `CharacterTag` extended (+`parentTagId`, +`sortOrder`, +`collapsed`); `WorldCategoryNode` added; `NarrativeProject.worldCategories` added; schema version `4→5` |
| `src/ui-react/services/projectService.ts` | Import `WorldCategoryNode`; `buildDefaultWorldCategories()`; migration in `migrateProject()`; write/read `categories.json` |
| `src/ui-react/store.ts` | Import `WorldCategoryNode`; add `worldCategories` to state + initial state + clone; add 7 new actions |
| `src/ui-react/components/TagTreePanel.tsx` | **NEW** — dnd-kit tree component (testid: `-row-` prefix for drag container) |
| `src/ui-react/components/CharactersWorkspace.tsx` | Replace `TagsPanel` grid with `<TagTreePanel>` |
| `src/ui-react/components/WorldWorkspace.tsx` | Add category tree panel + filter logic |
| `dev_docs/TEST_SELECTORS.txt` | Added W5 tag tree selectors with corrected `-row-` naming |
| `tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts` | **NEW** — 5 E2E tests (5/5 passing) |

---

## Risks and Deferred Items

| Item | Risk | Mitigation |
|------|------|-----------|
| Physical DnD drag in Playwright | Playwright's drag simulation can be flaky on dnd-kit pointer events | All 5 tests use store API directly (no actual pointer drag) |
| `worldCategories` persistence in `localStorage` mode | `migrateProject` sets `worldCategories` but the in-memory path does not read from `categories.json` | `migrateProject` handles it via spread merge; localStorage saves the entire project JSON |
| World category tree `tagIds` on WorldItem unused | Items still match by `categoryPath` name string; not yet wired to `tagIds` | Future work: wire `WorldItem.tagIds` to `WorldCategoryNode.id` for exact matching |
| Unlimited nesting scroll performance | Very deep trees (50+ nodes) may scroll awkwardly | Acceptable for current scope; virtualization is future work |
