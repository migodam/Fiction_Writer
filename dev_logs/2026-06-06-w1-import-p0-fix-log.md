# W1 Import P0 Fix Log — 2026-06-06

## Scope

Fixed the P0 gaps reported after `import_test15`: manuscript projection missing, reviewer world reclassification not applying, graph label overlap, and undo restoring pre-import project state.

## Changes

- Added deterministic Manuscript projection repair in `projectService`: when `manuscriptNodes` are empty but chapters/scenes exist, generate chapter and scene outline nodes.
- Prevented `memory://` projects from being written as local `memory:/` directories.
- Added scene-content fallback for Manuscript node loading.
- Prevented W1 `_write_manuscript_nodes()` from overwriting an existing non-empty `nodes.json` with an empty node list.
- Normalized `reclassify_world_item` reviewer operations and added a frontend applier for that operation.
- Added Reviewer activity feed events for quality/fact/consistency reviewer phases and repair proposal preparation.
- Accepted import packages no longer push a normal undo snapshot, preventing the next Cmd+Z from restoring the entire pre-import project.
- Added/validated radial relationship graph layout and readable edge labels from the graph worker patch.
- Added tests for manuscript projection repair, post-import undo safety, and world item reclassification package acceptance.

## Tests

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/tools.py sidecar/supervisor/organizer.py sidecar/supervisor/reviewers/quality_reviewer.py` — PASS
- `npm run ui:build` — PASS
- `sidecar/.venv/bin/python -m pytest tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py -q` — 55 passed
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q` — 62 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts --reporter=list` — 8 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/global_undo.spec.ts --reporter=list` — 5 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts --reporter=list` — 11 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts tests/e2e/p1/graph_sidebar_linkage.spec.ts --reporter=list` — 5 passed
- `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` — 5/5 passed; secret scan clean; live smoke gated/skipped

## Remaining

- Full OneNote-like World Model category tree UI is still a follow-up.
- Full Command/Patch undo architecture remains a larger refactor; this P0 closes the import-package rollback regression.
- Real first-10-chapter smoke still needs user-approved provider key and cost approval.
