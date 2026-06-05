# W1 Manuscript Canonical Pipeline — Integration Fixback Report

**Date:** 2026-06-05  
**Integration branch:** `codex/w1-orchestrated-import-quality`  
**Integration commit:** `7fcd1f9`  
**Source commits:** `2355f30` (feat), `a7e575f` (docs) from `codex/w1-ai-import-orchestrator`  
**Method:** Manual cherry-pick (no branch merge — projectService.ts had conflicts)

---

## Commits Integrated

| Commit | Branch | Description |
|--------|--------|-------------|
| `2355f30` | `codex/w1-ai-import-orchestrator` | feat: write ManuscriptNode tree before proposals; load in openProject |
| `a7e575f` | `codex/w1-ai-import-orchestrator` | docs: W1 manuscript canonical pipeline delivery report 2026-06-05 |

The docs report was copied directly. The code changes from `2355f30` were applied manually.

---

## Conflicts Encountered and Resolved

### `src/ui-react/services/projectService.ts`

The integration branch had W4 and other additions to `projectService.ts` (world drag/drop, `WorldCategoryNode` import, etc.) that diverged from the W1 worktree branch. A blind `git cherry-pick` would have produced merge conflicts.

**Resolution:** Applied the four W1 additions manually:

1. `ManuscriptNode` and `ManuscriptNodeType` added to the `import type { ... }` block (alongside existing `WorldCategoryNode`)
2. `const manuscriptDir = path.join(writingDir, 'manuscript')` added in `serializeProjectToFolder`
3. `manuscriptDir` added to the `ensureDir` array
4. `writeJson(..., 'nodes.json', project.manuscriptNodes || [])` added after scene writes
5. `const manuscriptNodeDir = ...` added in `openProject`
6. `manuscriptNodes` IIFE added to the project object

**Improvement over W1 worktree version:**
- Added allowlisted `ManuscriptNodeType` validation using `new Set<ManuscriptNodeType>(['act', 'part', 'chapter_outline', 'scene_outline', 'note'])` instead of blind cast
- Added stable fallback `id = rawId || \`mn_unknown_\${i}\`` for nodes with empty/missing ID

### `sidecar/workflows/w1_import.py`

No conflicts — integration branch had not touched the helpers section. Applied cleanly.

**Improvement over W1 worktree version:**
- `_safe_node_id` returns `'mn_unknown'` instead of empty string on degenerate input (belt-and-suspenders for the `if not chap_node_id` guard added below)

### `tests/e2e/p1/writing_manuscript_import_display.spec.ts`

**Bug found and fixed during integration:**

The content readability test's `fakePathModule.join` used:
```ts
join: (...parts) => parts.join('/').replace(/\/+/g, '/')
```
This collapsed `memory://` → `memory:/`, breaking `existsSync` lookups against fake file keys that preserved `://`.

**Fix:**
```ts
join: (...parts) => parts.join('/').replace(/([^:/])\/+/g, '$1/')
```
This preserves `://` protocol schemes while still collapsing any spurious double-slashes between path segments.

---

## Files Changed in Integration Commit `7fcd1f9`

| File | Change |
|------|--------|
| `sidecar/workflows/w1_import.py` | Added `_safe_node_id`, `_estimate_word_count`, `_write_manuscript_nodes` helpers; 4-phase restructure of `node_write_to_project` chapter section |
| `src/ui-react/services/projectService.ts` | Manual integration: `ManuscriptNode`/`ManuscriptNodeType` import, `manuscriptDir` ensureDir, `nodes.json` persist, `manuscriptNodes` load with allowlisted types and stable ID fallback |
| `tests/test_w1_import_compiler.py` | Added `test_node_write_to_project_writes_manuscript_node_projection` including actual sample text assertion (韩立 must appear in chapter 1 .md) |
| `tests/e2e/p1/writing_manuscript_import_display.spec.ts` | Added 3 new tests across 2 describe blocks; fixed `fakePathModule.join` to preserve `://` |
| `communication/2026-06-05-w1-manuscript-canonical-pipeline-report.md` | Copied from worktree (original delivery report) |

---

## Test Results

| Suite | Command | Result |
|-------|---------|--------|
| Manuscript backend tests | `pytest tests/test_w1_import_compiler.py -k manuscript -q` | **12/12 PASS** |
| Full W1 regression | `pytest tests/test_w1_import_compiler.py tests/test_w1_supervisor_tools.py tests/test_w1_supervisor_policy.py tests/test_w1_quality_rubric.py -q` | **193/193 PASS** |
| UI build | `npm run ui:build` | **PASS** (tsc + vite, no errors) |
| Playwright manuscript spec | `npx playwright test writing_manuscript_import_display.spec.ts` | **6/6 PASS** |

---

## W1 Manuscript Pipeline — Final Data Contract

```
After W1 import completes node_write_to_project:

Phase 1 (pre-build):
  manuscript_scene_pairs ← built from manuscript_chapters

Phase 2 (early write — survives cancellation):
  writing/manuscript/nodes.json     ← ManuscriptNode tree (2 nodes per chapter)
  writing/manuscript/mn_{scene}.md  ← prose per chapter

Phase 3 (chapter proposals):
  S2 proposals for each chapter entity

Phase 4 (scene proposals):
  S2 proposals for each scene entity

After project reopen (openProject):
  manuscriptNodes ← loaded from writing/manuscript/nodes.json
    - non-array → []
    - allowlisted type validation (act/part/chapter_outline/scene_outline/note)
    - stable fallback ID for empty/missing id field
    - dedup via Set<string>
    - per-field type guards

Writing Studio Manuscript view:
  ManuscriptWorkspace reads manuscriptNodes from Zustand store
  loadManuscriptNodeContent reads writing/manuscript/{nodeId}.md on click
```

---

## Remaining Risk

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `ManuscriptNode.wordCount` for Latin content uses `split()` which may count poorly for languages between CJK and Latin (Japanese, Korean mixed) | Low | Only affects display word count; not blocking |
| content readability Playwright test depends on `globalThis.require` being mockable — any future sandboxing change (e.g., strict CSP) would break it | Low | Test design is sound; env-specific issue only |
| `nodes.json` is written with UTF-8 content per chapter; extremely large imports (500+ chapters) could produce many `.md` files — no pagination yet | Low | Not a current blocker; W1 test suite validates 50-chapter streaming |

---

## W7 Readiness from Manuscript Perspective

**W7 can proceed.** The ManuscriptNode pipeline is integrated and verified:

- Writing Studio Manuscript shows imported chapters immediately after project reopen
- Content files survive proposal cancellation  
- `openProject` normalizes defensively — no crashes on corrupted or missing `nodes.json`
- 193 W1 backend tests pass; UI build clean; 6/6 Playwright manuscript display tests pass

The only open Manuscript item is the Playwright content readability test asserting actual Chinese text (`韩立`) in the editor — this passed 6/6 in this session including the retry.
