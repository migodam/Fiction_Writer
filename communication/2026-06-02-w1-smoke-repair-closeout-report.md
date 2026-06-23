# W1 Smoke Repair — Closeout Patch Report

**Date:** 2026-06-02  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Author:** Claude Code (Closeout Patch Worker)  
**Scope:** Fixes for three P1/P2 acceptance gaps identified by Codex review; final gate verification.

---

## Executive Verdict

**PASS**

All three acceptance gaps are closed. The targeted W1 pytest suite now passes 226/226 (was 223/224 before). All 19 Playwright specs pass (was 18/19 before). The TypeScript build passes clean.

---

## Gaps Closed

### Gap 1 — Organizer not wired into W1 import graph

**Root cause:** `organize_project_content()` in `sidecar/supervisor/organizer.py` was never imported or called from the W1 pipeline. The organizer's world-item contamination filtering, categoryPath enrichment, and module routing were silently bypassed on every import.

**Fix:**
- Added `from sidecar.supervisor.organizer import organize_project_content, OrganizerInput` to `sidecar/workflows/w1_import.py`
- Wrote `async def node_organize_project(state: ImportState) -> dict` (lines ~3633–3680 in `w1_import.py`):
  - Builds `OrganizerInput` from `entity_registry["world_detailed"]`, `entity_registry["characters"]`, `entity_registry["events"]`, `state["relationships"]`, `state["timeline_architecture"]`, `state["source_language"]`
  - Calls `organize_project_content(organizer_input)`
  - Removes excluded items (module contamination, person names) from `world_detailed`
  - Enriches surviving items with `categoryPath`, `parentId`, `container_key` from the organizer output
  - Returns `{"entity_registry": updated_registry}`
- Registered node: `builder.add_node("organize_world_items", node_organize_project)`
- Inserted edge: `architect_timeline → organize_world_items → generate_import_todos` (replacing `architect_timeline → generate_import_todos`)

**Test:** Added `test_node_organize_project_filters_and_enriches` to `tests/test_w1_organizer.py` — verifies contamination item removal and categoryPath enrichment for a minimal state.

---

### Gap 2 — Reviewer repair package "Accept Package" does not clear inbox

**Root cause:** `pruneDanglingProposalReferences` in `src/ui-react/services/projectService.ts` called `.filter()` on character array fields (`tagIds`, `linkedSceneIds`, `linkedEventIds`, `linkedWorldItemIds`) that can be `undefined` on minimal entities injected by the repair flow. The `TypeError` silently aborted the Zustand state update, leaving proposals in the inbox.

The same `undefined`-array risk existed for `scene`, `chapter`, `timeline_event`, and `world_item` pruning paths.

**Fix:** Added `|| []` guards to all `.filter()` calls on entity array fields in `pruneDanglingProposalReferences` (lines 1684–1716 of `projectService.ts`). No behavior change for fully-formed entities; prevents TypeError for partially-formed ones.

**Test:** `workbench_reviewer_repair_package.spec.ts:329` ("accepting op:update repair package updates existing character field") now passes.

---

### Gap 3 — Tool registry test stale (expected 11 tools, registry has 17)

**Root cause:** `test_build_tool_registry_returns_all_ten_tools` in `tests/test_w1_supervisor_tools.py` was written before the six reviewer/organizer tools were added in commit `8854a64`. The test expected 11 tools; the registry has 17.

**Fix:** Updated expected set to include all 17 tools (`run_quality_review`, `run_fact_review`, `run_consistency_review`, `rerun_targeted_window`, `repair_import_artifacts`, `write_proposal_package` added alongside the original 11). Renamed method to `test_build_tool_registry_returns_all_seventeen_tools`.

---

## Test Gate Results (After Patch)

| Test Suite | Command | Before | After |
|------------|---------|--------|-------|
| pytest (targeted) | 8 W1 test files, `-q` | 223 PASS, 1 FAIL | **226 PASS, 0 FAIL** |
| TypeScript build | `npm run ui:build` | PASS | **PASS** |
| Playwright: workbench repair | `workbench_reviewer_repair_package.spec.ts` | 9/10 PASS | **10/10 PASS** |
| Playwright: world organizer | `world_model_organizer.spec.ts` | 4/4 PASS | **4/4 PASS** |
| Playwright: token cost | `import_token_cost.spec.ts` | 5/5 PASS | **5/5 PASS** |

---

## Files Changed

| File | Change |
|------|--------|
| `sidecar/workflows/w1_import.py` | Added organizer import, `node_organize_project()` function, node registration, new edge `architect_timeline → organize_world_items → generate_import_todos` |
| `src/ui-react/services/projectService.ts` | Added `|| []` guards to all array `.filter()` calls in `pruneDanglingProposalReferences` |
| `tests/test_w1_supervisor_tools.py` | Updated expected tool count from 11 to 17, renamed test method |
| `tests/test_w1_organizer.py` | Added `test_node_organize_project_filters_and_enriches` |

---

## Remaining Work

None — all three gaps are closed. The branch is ready for Electron manual smoke with a fresh import.

**Prerequisite for manual smoke:** Run a fresh W1 import (the `import_test11` project data is stale pre-fix; the split files on disk pre-date all Workers A–G fixes).
