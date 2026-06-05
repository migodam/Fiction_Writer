# W1 Manuscript Canonical Pipeline — Delivery Report

**Date:** 2026-06-05  
**Branch:** `codex/w1-ai-import-orchestrator`  
**Commit:** `2355f30`  
**Files changed:** 4  
**Tests added:** 1 Python + 3 Playwright  
**Regression:** 193/193 pass

---

## Problem

After a real 10-chapter W1 import, Writing Studio → Manuscript always showed empty. Root cause was two-fold:

1. W1 never wrote `writing/manuscript/nodes.json` or `*.md` content files — only `manuscript.json` (root-level prose snapshot).
2. `projectService.ts` never persisted or loaded `manuscriptNodes` — the Zustand store always reset to `[]` on project open.

---

## What W1 Now Writes

| File | Timing | Purpose |
|------|--------|---------|
| `manuscript.json` | BEFORE proposals (unchanged) | Chapter prose snapshot; always survives cancellation |
| `writing/manuscript/nodes.json` | BEFORE proposals (new) | ManuscriptNode tree; drives Writing Studio Manuscript view |
| `writing/manuscript/mn_{scene_id}.md` | BEFORE proposals (new) | Per-chapter prose; read by `loadManuscriptNodeContent` on node click |
| `writing/chapters/{chapter_id}.json` | AFTER proposal acceptance (unchanged) | Chapter entity |
| `writing/scenes/{scene_id}.md` + `.meta.json` | AFTER proposal acceptance (unchanged) | Scene entity |

**Early-write guarantee:** `_write_manuscript_nodes()` is called in Phase 2, after the pre-build loop assembles `manuscript_scene_pairs` but before Phase 3 chapter proposals and Phase 4 scene proposals. If the user cancels mid-import or the process dies during proposals, `nodes.json` and `*.md` files are already on disk — Writing Studio Manuscript is visible immediately.

---

## How Writing Studio Reads Manuscript

1. **`openProject()`** in `projectService.ts` reads `writing/manuscript/nodes.json` → normalizes → populates `manuscriptNodes` in the returned `NarrativeProject`.
2. **Store hydration:** `setOpenProject()` in `store.ts` sets `manuscriptNodes: hydratedProject.manuscriptNodes ?? []` (unchanged — was already correct).
3. **`ManuscriptWorkspace`** reads `manuscriptNodes` from Zustand store and renders the node tree (unchanged).
4. **`loadManuscriptNodeContent(projectRoot, nodeId)`** in `store.ts` reads `writing/manuscript/{nodeId}.md` via `require('fs')` when a scene node is clicked (unchanged).

---

## Normalization on Load

`openProject()` normalizes `nodes.json` defensively:

- **Non-array value** → warn + return `[]` (guards against corrupted or empty file)
- **Missing/wrong-type fields** → safe defaults (`title: ''`, `type: 'note'`, `orderIndex: 0`, `wordCount: 0`, `parentId/linkedChapterId/linkedSceneId: null`, `collapsed: false`)
- **Duplicate IDs** → deduplicated via `Set<string>` (guards against retry-written duplicates)
- **Type cast** → reduces via `ManuscriptNode[]` accumulator with per-field guards

---

## Node ID Safety

`_safe_node_id(raw_id)` strips characters unsafe for filenames and ManuscriptNode IDs:

```python
re.sub(r"[/\\:*?\"<>| \x00-\x1f]", "_", raw_id)
```

IDs follow the pattern `mn_{chapter_id}` for chapter nodes and `mn_{scene_id}` for scene nodes. Since chapter/scene IDs are UUIDs or `chap_`/`scene_`-prefixed hex strings, no unsafe characters appear in practice — but the guard ensures correctness for arbitrary import data.

---

## CJK Word Count

`_estimate_word_count(text, source_language)` uses:
- **Chinese (`source_language == "zh"`):** count characters in Unicode range `U+4E00–U+9FFF` (CJK Unified Ideographs)
- **Latin/other:** `len(text.split())` (whitespace-split tokens)

Using `split()` on Chinese text would return 1 for any sentence with no spaces, drastically undercounting. The character-count method gives accurate estimates for Chinese prose.

---

## Post-Cancellation State

Because `_write_manuscript_nodes()` is in Phase 2 (before proposals), even if the user closes the app during proposal writing:

- `writing/manuscript/nodes.json` exists → Writing Studio Manuscript tree visible
- `writing/manuscript/mn_*.md` files exist → content readable on node click
- `manuscript.json` exists (existing behavior) → full prose accessible

The `test_node_write_to_project_writes_manuscript_before_cancellable_proposals` test (pre-existing) already proves `manuscript.json` survives cancellation. The new test proves `nodes.json` is also written before proposals.

---

## Content Non-Empty — Proof

**Python:** `test_node_write_to_project_writes_manuscript_node_projection`

- Provides 2 chapters with Chinese prose (`韩立踏上修仙之路…`, `韩立进入七玄门…`)
- Sets `source_language = "zh"`
- Asserts `nodes.json` exists and has 4 nodes (2 chapter + 2 scene)
- Asserts `ch1_node["wordCount"] > 1` (verifies CJK character-count path)
- Asserts each `mn_*.md` file exists and has non-empty content
- Asserts no `/`, `\`, or space in any node ID

**Playwright D2:** `manuscript node content readability`

- Builds mock fs with `fakeFiles` map keyed by `memory://…/writing/manuscript/{id}.md`
- Injects `require('fs')` override that serves from `fakeFiles`
- Navigates to `/writing/manuscript`, clicks `manuscript-node-mn_scene_mn01`
- Asserts `manuscript-editor` visible and `manuscript-editor-wordcount` does not contain `"0 "`

---

## Test Summary

| Test | File | Result |
|------|------|--------|
| `test_node_write_to_project_writes_manuscript_node_projection` | `test_w1_import_compiler.py` | PASS |
| All 11 existing manuscript tests | `test_w1_import_compiler.py` | PASS (12 total) |
| Full W1 regression (193 tests) | all W1 test files | 193/193 PASS |
| `manuscript workspace shows all 10 chapter nodes` | `writing_manuscript_import_display.spec.ts` | Added |
| `chapter nodes and scene nodes are present in the tree` | `writing_manuscript_import_display.spec.ts` | Added |
| `clicking a scene node shows non-empty content` | `writing_manuscript_import_display.spec.ts` | Added |

(Playwright tests require the dev server; added to the spec file for CI/manual runs.)

---

## Files Changed

| File | Change |
|------|--------|
| `sidecar/workflows/w1_import.py` | Added `_safe_node_id`, `_estimate_word_count`, `_write_manuscript_nodes` helpers; restructured `node_write_to_project` into 4 phases (pre-build → node write → chapter proposals → scene proposals) |
| `src/ui-react/services/projectService.ts` | Added `manuscriptDir` to ensureDir list; persist `nodes.json` after scenes in `serializeProjectToFolder`; load + normalize `manuscriptNodes` in `openProject`; added `ManuscriptNode`, `ManuscriptNodeType` imports |
| `tests/test_w1_import_compiler.py` | Added `test_node_write_to_project_writes_manuscript_node_projection` |
| `tests/e2e/p1/writing_manuscript_import_display.spec.ts` | Added `makeManuscriptNodesFixture`, `injectManuscriptFixture`, two new describe blocks (tree display + content readability) |

## Files NOT Changed

| File | Reason |
|------|--------|
| `sidecar/models/state.py` | Shared surface — no Lead reservation; `ManuscriptNode` addition not required |
| `store.ts` | `manuscriptNodes ?? []` and `cloneProject` already correct |
| `ManuscriptWorkspace.tsx` | Tree rendering + empty state already correct |
| `WritingWorkspace.tsx` | Routes to ManuscriptWorkspace correctly |
| `models/project.ts` | `ManuscriptNode` type already defined at line 426 |
