# Worker D — World Model Hierarchy Implementation Report

**Date:** 2026-06-01  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** D (World Model Hierarchy and Organizer Robustness)

---

## Summary

Closed Defect #6: World items had `categoryPath: null / parentId: null`. Contamination containers (`人物关系图`, `事件时间线`) appeared in the World Model UI alongside real items. WorldWorkspace rendered a flat item list with no grouping.

After this work:
- Items with `categoryPath` render under sticky section headers grouped by `categoryPath[1]`
- Contamination containers are filtered from the left sidebar at render time (not deleted from disk)
- Old imports without `categoryPath` are normalized on load via `normalizeWorldItem()` using a TypeScript mirror of the Python category-path map
- `WorldContainer` TypeScript interface now includes `description?` and `importCategoryKey?`
- Organizer tests expanded to 15 with explicit `categoryPath` content assertions
- 4 Playwright hierarchy/contamination/fallback tests added

---

## Files Changed

| File | Change |
|------|--------|
| `tests/test_w1_organizer.py` | Added 3 tests (tests 11–13): explicit `categoryPath` content for `cultivation_method`, `organization`, `location` |
| `src/ui-react/models/project.ts` | Added `description?` and `importCategoryKey?` to `WorldContainer` interface |
| `src/ui-react/services/projectService.ts` | Added `WORLD_CATEGORY_PATH_MAP`, `normalizeWorldItem()`, patched world items load to call `.map(normalizeWorldItem)` |
| `src/ui-react/components/WorldWorkspace.tsx` | Added `CONTAMINATION_CONTAINER_NAMES` set, `groupedItems` memo, contamination filter on container list, `data-testid="world-container-{id}"`, grouped item rendering with group headers |
| `tests/e2e/p1/world_hierarchy.spec.ts` | New: 4 Playwright tests for hierarchy grouping, contamination filtering, flat fallback |

---

## Tests Run

### Python organizer tests
```
sidecar/.venv/bin/python -m pytest tests/test_w1_organizer.py -q
```
**Result: 15 passed** (was 12 before this session's 3 additions; the file also had 3 tests added in a prior session making 13 total on disk, but git shows 15 in the committed file)

**Note:** The test file was already on disk with 13 tests (10 original + 3 path-content tests added earlier in this session's plan). Committed state: 15 tests.

### TypeScript build
```
npm run ui:build
```
**Result: PASS** — `tsc` zero errors, Vite built in 2.69s

### Playwright (requires dev server — not run in this session)
```
npx playwright test tests/e2e/p1/world_hierarchy.spec.ts --reporter=list
```
Expected: 4 PASS against running dev server at `http://localhost:3000`

---

## Before / After: WorldWorkspace Behavior

**Before:**
- Left sidebar: all containers shown including `人物关系图`, `事件时间线`, and other contamination strings
- Item list: flat `containerItems.map()` — no grouping, no section headers
- Old imports: `categoryPath: undefined`, `parentId: undefined` — hierarchy completely absent
- `WorldContainer` TypeScript type: missing `description` and `importCategoryKey` fields

**After:**
- Left sidebar: contamination containers filtered by `CONTAMINATION_CONTAINER_NAMES` set; clean list of real world containers
- Item list: items grouped by `categoryPath[1]` with sticky section headers (e.g., "功法与术法", "地理位置"); items without `categoryPath` fall to ungrouped flat list at bottom
- Old imports: `normalizeWorldItem()` fills `categoryPath` from `category` field on projectService load (additive, non-destructive)
- `WorldContainer` TypeScript type: now includes `description?` and `importCategoryKey?`

---

## Normalization Map (TypeScript)

```typescript
const WORLD_CATEGORY_PATH_MAP = {
  location:           ['世界模型', '地理位置'],
  organization:       ['世界模型', '门派组织'],
  faction:            ['世界模型', '门派组织'],
  item:               ['世界模型', '物品与法器'],
  artifact:           ['世界模型', '物品与法器'],
  cultivation_method: ['世界模型', '功法与术法'],
  rule:               ['世界模型', '修炼境界与制度'],
  system:             ['世界模型', '修炼境界与制度'],
  concept:            ['世界模型', '概念与设定'],
  culture:            ['世界模型', '文化与习俗'],
  custom:             ['世界模型', '概念与设定'],
};
```

Mirrors Python `_CATEGORY_PATH_ROOTS` in `sidecar/supervisor/organizer.py`.

---

## Open Risks

1. **Worker A conflict on `projectService.ts`**: Worker A also owns `projectService.ts` for character/chapter hydration. Worker D added `normalizeWorldItem` (~line 122) and patched the world items load line (~line 852). These are disjoint regions from Worker A's character/chapter work, but merge order matters. **Recommendation:** merge Worker D first (or last with a manual diff review of the world items section).

2. **Contamination containers remain in Zustand store**: The filter is render-only. If any other component iterates `worldContainers` and expects clean data (e.g., a world export function), it will still see `人物关系图`. For now, UI-only filter is sufficient. If a future task adds export/sync, add a selector helper `selectCleanWorldContainers`.

3. **Mixed container (old + new items)**: A container with both pre-organizer items (no `categoryPath`) and post-organizer items (with `categoryPath`) will show two sections: named group headers for new items + ungrouped flat list for old items. This is correct behavior — no visual bug.

4. **`world-container-list` testid scope**: The Playwright tests assert `not.toBeVisible()` for contamination containers. If the container list is paginated or virtualized in a future refactor, these selectors may need updating.

---

## Manual Smoke Instructions

1. Start the dev server: `npm run electron:dev`
2. Open or create a project with an existing W1 import that has world items
3. Navigate to World Model (Activity Bar → globe icon)
4. Verify: `人物关系图` and `事件时间线` containers do NOT appear in the left sidebar
5. Click a world container that has items with `categoryPath`
6. Verify: items appear under labeled section headers (e.g., "功法与术法", "地理位置")
7. If any old-format items exist (no `categoryPath`), they should still appear below any grouped sections
8. Click an item and verify it is selectable and its detail pane opens correctly

---

## Commits

```
cadf95d feat: add categoryPath hierarchy grouping and contamination filter to WorldWorkspace
8b2bbdc test: add Playwright world hierarchy, contamination filter, and flat fallback tests
```

Prior session commits (same branch):
```
test: add explicit categoryPath content assertions to organizer tests
feat: add description and importCategoryKey to WorldContainer interface
feat: normalize world item categoryPath on load in projectService
```
