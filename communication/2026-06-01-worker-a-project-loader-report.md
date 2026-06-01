# Worker A — Project Loader / Manuscript Display Report

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Commit:** `5fcb457`

---

## Summary

Investigated the frontend/canonical loading gap for `import_test11`. Found that split-file hydration in `projectService.ts` is already implemented and correct — `openProject()` reads every entity type from its canonical directory. The actual gaps were:

1. Chapter sort fallback used `title.localeCompare()` which is unstable for Chinese chapter numbers (第一章…第十章) when two chapters share the same `orderIndex`.
2. `timelineEvents` read lacked an explicit `Array.isArray` guard to defensively exclude `branches.json` parsing as an array.
3. No Playwright regression test existed for the import display path.

All three gaps are now closed.

---

## Files Changed

| File | Change |
|---|---|
| `src/ui-react/services/projectService.ts` | Added `parseChapterNumber()` + `CJK_DIGITS`; patched chapter sort; added `!Array.isArray` guard on `timelineEvents` |
| `tests/e2e/p1/writing_manuscript_import_display.spec.ts` | **NEW** — 3 Playwright tests |

---

## Hydration Path (Already Correct, Verified)

`projectService.openProject()` reads split files directly:

| Split files | Hydrated to |
|---|---|
| `writing/chapters/*.json` | `NarrativeProject.chapters` |
| `writing/scenes/*.meta.json` + `.md` | `NarrativeProject.scenes` (content from .md) |
| `entities/timeline/branches.json` | `timelineBranches` |
| `entities/timeline/event_*.json` | `timelineEvents` |
| `entities/world/containers.json` | `worldContainers` |
| `entities/world/world_*.json` | `worldItems` |
| `entities/characters/*.json` | `characters` |
| `entities/relationships.json` | `relationships` |
| `entities/character-tags.json` | `characterTags` |

`cleanupImportedWritingArtifacts` runs inside `migrateProject` and:
- Removes blank `chap_1`/`scene_1` starter when imported chapters exist  
- Sorts chapters by `orderIndex` then `parseChapterNumber(title)` then `localeCompare`  
- Deduplicates scenes with identical content

**Confirmed via import_test11:**
- `scene_1.md` is 0 bytes → starter cleanup correctly fires
- Imported chapter orderIndex values: 第一章=0, 第二章=1 … 第十章=9

---

## Sort Fix Detail

**Before:**
```typescript
.sort((a, b) => a.orderIndex - b.orderIndex || a.title.localeCompare(b.title))
```

**After:**
```typescript
.sort((a, b) => a.orderIndex - b.orderIndex || parseChapterNumber(a.title) - parseChapterNumber(b.title) || a.title.localeCompare(b.title))
```

`parseChapterNumber` handles:
- Arabic: `"Chapter 3"`, `"第3章"`, `"3."` → extracts first integer
- Chinese: `"第十二章"` → parses CJK digit sequence into number (12)
- Unknown: returns 9999 (sorts last, then falls to localeCompare)

---

## Tests

```
tests/e2e/p1/writing_manuscript_import_display.spec.ts   3/3 PASS  (2.8s)
npm run ui:build                                         ✓ 0 errors
```

### Test coverage

| Test | What it verifies |
|---|---|
| `imported chapters appear in numeric order` | `cleanupImportedWritingArtifacts` sort produces 第一章…第十章 in the sidebar |
| `blank starter "Chapter 1" is not shown` | `isBlankStarterChapter` removes starter; no `chapter-item-chap_1` visible |
| `chapter card shows non-empty summary` | Chapter click reveals editor with non-empty summary field |

**Test approach:** `page.addInitScript` injects a project fixture into `localStorage['narrative-ide-project']` before the app boots. Since `getNodeRuntime()` returns null in the Playwright browser context (no Node.js), `openProject()` falls back to localStorage — this is the same path taken after `saveProject()` in memory mode. The fixture deliberately provides chapters in shuffled orderIndex order to exercise the sort.

---

## Remaining Risks

| Risk | Status |
|---|---|
| Node.js file-read path not covered by Playwright tests | Known gap. Tests verify sort/cleanup/render logic via localStorage injection. File-read fidelity is verified by code inspection of `openProject()`. |
| Scene content in .md files not tested | The Playwright test verifies chapter-level summary display; scene prose content (.md) verification requires either Electron E2E or a manual smoke of `import_test11`. |
| Merge rule for legacy project.json arrays | Not implemented — project.json has no arrays in current schema (v4). Premature to add. |
| Other workers touching `projectService.ts` | Worker D has partial ownership for world item hydration. Coordinate before merging. |
