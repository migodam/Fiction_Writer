# W4 World Taxonomy Repair + Item Drag/Drop — Implementation Report

**Date:** 2026-06-05  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** W4

---

## Problem

Three interconnected gaps:

1. **Taxonomy misclassification**: 项甲功 (a cultivation skill) was placed under 修炼境界与制度 (Rules & Systems) instead of 功法与术法 (Cultivation Methods). The name "项甲功" ends in "功" — a strong semantic signal for cultivation method — but `_normalize_category` only checked `raw_category` for cultivation hints. When `raw_category` was "规则与制度", the substring "制度" → "rule" path won.

2. **Reviewer gap**: `QualityReviewer._check_world_wrong_classification` only detected `category="character"` misclassifications. Cultivation ↔ rule misroutes were invisible. Even when reclassify repairs were applied, `pipeline_tools.repair_import_artifacts` only updated the `category` field — leaving `categoryPath` and `container_key` stale.

3. **UI gap**: No drag/drop on world items. Users had to delete and recreate items to fix wrong container placement.

---

## Architecture

### Taxonomy Algorithm (`classify_world_item`)

Extracted `_normalize_category` into a public `classify_world_item(name, raw_category, description)` function with a new priority step 2 (cultivation name-suffix check) that fires BEFORE the raw_category substring match.

**Priority table:**

| Priority | Rule | Example |
|----------|------|---------|
| 1 | `person/character/人物` in raw → custom | raw=`"人物"` |
| **2 (new)** | **Name ends with 功/法诀/秘术/etc. AND desc doesn't say rank/realm → cultivation_method** | **"项甲功" → cultivation_method** |
| 3 (new) | Name contains 境界/层/制度/etc. → rule | "修炼境界" → rule |
| 4 | Role-rank token in name AND not location suffix → rule | "护法" → rule |
| 5 | Explicit cultivation hint in raw → cultivation_method | raw=`"功法"` |
| 6 | Name location/org suffix → location/organization | "七玄门" → organization |
| 7 | Alias map on raw | `"sect"` → organization |
| 8 | Substring matches on raw | `"制度"` → rule |
| 9 | Name suffix fallback | — |
| 10 | Default → concept | — |

`_normalize_category` becomes a thin wrapper: `return classify_world_item(name, str(raw_category or ""))`.

The call site in `organize_project_content` now passes `description` to enable description-based disambiguation.

### QualityReviewer Repair

`_check_world_wrong_classification` now:
- Case 1 (existing): `category="character"` → find correct category via `classify_world_item`, emit `proposed_operations` with `new_category`, `new_container_key`, `new_category_path`.
- Case 2 (new): `classify_world_item(name, raw_category, description)` differs from `current_category` with high confidence (cultivation ↔ rule) → emit finding + reclassify repair with full `proposed_operations`.

### Pipeline Tools Fix

`repair_import_artifacts` reclassify branch now reads `proposed_operations[0]` first and updates `category`, `container_key`, and `categoryPath`. Falls back to description-parsing (legacy) if no `proposed_operations`.

### UI Drag/Drop

- **`moveWorldItemToCategory(itemId, newCategory, newContainerId, newCategoryPath)`** added to store (captures undo snapshot → `'Move world item'`).
- **`DraggableWorldItem`** sub-component: wraps item row with `useDraggable`, shows `GripVertical` handle on hover.
- **`DroppableCategoryHeader`** sub-component: group header becomes a drop zone; highlights on hover.
- **`DndContext`** wraps the item list. `handleDragEnd` finds the target container by matching the drop zone name to `worldContainers[].name` or `importCategoryKey`.
- `DragOverlay` shows a floating card with the dragged item name.
- Sensor: `PointerSensor` with 5px activation distance (same as TagTreePanel).

---

## Files Changed

| File | Change |
|---|---|
| `sidecar/supervisor/organizer.py` | Added `_CULTIVATION_NAME_SUFFIXES`, `_RULE_NAME_HINTS` constants; extracted `classify_world_item()` public function; `_normalize_category` delegates to it; call site passes `description` |
| `sidecar/supervisor/reviewers/quality_reviewer.py` | `_check_world_wrong_classification` uses `classify_world_item` for semantic mismatch detection; emits `proposed_operations` in reclassify repairs |
| `sidecar/supervisor/pipeline_tools.py` | Reclassify branch reads `proposed_operations` and updates `categoryPath` + `container_key` |
| `src/ui-react/store.ts` | Added `moveWorldItemToCategory` action with undo snapshot |
| `src/ui-react/components/WorldWorkspace.tsx` | DndContext + DraggableWorldItem + DroppableCategoryHeader + handleDragEnd |
| `tests/test_w1_organizer.py` | 4 new tests |
| `tests/test_w1_reviewers_quality.py` | 2 new tests |
| `tests/e2e/p1/world_item_drag_drop.spec.ts` | 3 new Playwright tests |
| `communication/2026-06-05-w4-world-taxonomy-dragdrop-report.md` | This report |

---

## Test Results

### Python

```
tests/test_w1_organizer.py        21 passed
tests/test_w1_reviewers_quality.py 17 passed
Total: 38 passed
```

New tests added:
- `test_xiangjia_gong_routes_to_cultivation_method` — 项甲功 routes correctly
- `test_xiulian_jingjie_routes_to_rule` — 修炼境界 routes correctly  
- `test_ji_ming_dizi_still_excluded` — existing exclusion not broken
- `test_classify_world_item_direct_call` — public API importable
- `test_quality_catches_xiangjia_gong_misrouted` — reviewer detects + repairs
- `test_reclassify_repair_updates_container_key_and_category_path` — pipeline fix verified

### Playwright

```
tests/e2e/p1/world_item_drag_drop.spec.ts  3 passed (3.5s)

  ✓ moveWorldItemToCategory store action moves item to new container
  ✓ moveWorldItemToCategory is undoable via undoAction
  ✓ world item rows are draggable — drag handle present in DOM
```

P0 regression: 18 failures confirmed pre-existing (identical set as before this work). No regressions.

---

## Known Ambiguous Cases

1. **Names ending in 功 that are not techniques**: e.g., "天功门" (organization) — caught by `_ORG_HINTS` check (step 6) before cultivation suffix (step 2) only if the name also ends in an org hint token. In "天功门", "门" is in `_ORG_HINTS` but "天功门" also ends in "门" — so the org suffix check fires at step 6 after the cultivation check at step 2 sees "门" is NOT in `_CULTIVATION_NAME_SUFFIXES`. Correct behavior: org.

2. **Description-based disambiguation**: The cultivation suffix check only overrides when `description` doesn't contain "境界/层次/等级制度/rank". If a skill has no description (empty string), it still routes to cultivation_method via name suffix alone. This is the desired behavior for "项甲功 with description=''".

3. **"修炼" in raw_category**: Still routes to "system" via step 8 substring match. This is correct for items whose raw_category is the chapter section header "修炼" (as opposed to their name indicating a cultivation technique).

---

## Manual Smoke

1. Open app, navigate to World Model.
2. Click a container that has items with `categoryPath`.
3. Hover an item row — a small grip icon appears on the left.
4. Drag the item onto a different category group header (the header highlights on hover).
5. Release — item moves to the new container. Its `categoryPath[1]` updates.
6. Press Cmd+Z — item returns to original container. ✓
