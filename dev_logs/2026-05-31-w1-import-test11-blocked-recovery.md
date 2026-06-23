# W1 Import Test 11 Blocked Recovery — 2026-05-31

## Scope

- Investigated `import_test11` after Accept All left 64 pending/blocked import proposals.
- No live model/API calls were made.
- No full50 benchmark was run.
- Real project data was inspected but not mutated by this fix pass.

## Findings

- The project had already accepted 121 import proposals into canonical data.
- The remaining 64 pending proposals were all blocked:
  - 36 `timeline_event` proposals referenced missing branch `branch_main`.
  - 17 `character` proposals referenced events that were also blocked.
  - 10 `chapter` proposals were duplicates of already accepted chapters.
  - 1 `world_settings` proposal was unsupported by the Workbench safety applier.
- Canonical timeline branches contained one root branch: `branch_item` / `韩立修仙之路`.
- Import artifacts showed Timeline Architect had emitted event branch IDs as `branch_main`, while the accepted canonical branch used `branch_item`.

## Fixes

- Future W1 proposal writing now normalizes stale event branch IDs to the imported root branch before proposing timeline events.
- Workbench import acceptance now remaps stale imported event branch IDs to the current root branch when the referenced branch is missing.
- Duplicate `create` proposals from import are treated as idempotent success, so already accepted chapters do not stay blocked forever.
- `world_settings` is now a supported singleton update target in the Workbench safety applier.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q` — 47 passed
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py -q` — 72 passed
- `npm run ui:build` — passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_smoke_acceptance.spec.ts --reporter=list` — 3 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_proposal_safety.spec.ts --reporter=list` — 5 passed

## Expected Manual Check

Open `import_test11`, go to Workbench, and click Accept All again. The stale 64 import proposals should no longer remain blocked for the previous branch/duplicate/world-settings reasons.
