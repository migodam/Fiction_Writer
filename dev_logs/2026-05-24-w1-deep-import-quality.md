# 2026-05-24 W1 Deep Import Quality Integration

Branch: `codex/w1-deep-import-quality-integration`

## Integrated Branches
- `codex/w1-packed-window-crossvalidate`
- `codex/w1-data-bugs-chapter-world`
- `codex/w1-language-branch-names`
- `codex/ui-mac-responsive-timeline`

## Changes
- Added deterministic W1 world category routing for `location`, `organization`, `item`, `rule`, `concept`, and `culture`.
- Added localized default world containers so Chinese imports route to Chinese-visible world sections instead of the first location/notebook.
- Prevented world entities such as `七玄门` from being written into the character registry.
- Seeded compact character cards from relationship, event, scene, and rolling cross-validation evidence to reduce under-extraction when the character scout is conservative.
- Increased W1 event extraction density and Timeline Architect budgets so Deep imports do not collapse to only a few canonical events.
- Routed mainline arcs such as protagonist origin, sect entry, and cultivation progress onto the main branch while keeping mentor/faction/secret arcs as side branches.
- Preserved chapter manuscript text on chapter proposals with deterministic `orderIndex`.
- Added stable World workspace selectors and a lightweight Save action for focused E2E coverage.

## Verification
- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py` passed.
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q` passed: 27 passed.
- `npm run ui:lint` passed.
- `npm run ui:build` passed.
- `npx playwright test tests/e2e/p0/navigation.spec.ts --config tests/playwright.config.ts` passed.
- `npx playwright test tests/e2e/p1/import_workflow.spec.ts --config tests/playwright.config.ts` passed: 18 passed.
- `npx playwright test tests/e2e/p1/world_model_containers.spec.ts --config tests/playwright.config.ts` passed.
- `npx playwright test tests/e2e/p1/timeline_interaction.spec.ts --config tests/playwright.config.ts` passed: 3 passed.

## Known Residuals
- `npm run sidecar:test` still fails in legacy `src/core` test suites unrelated to W1 (`ProjectMemory` legacy API expectations, failure-analysis string casing, router/PM legacy behavior). W1 targeted tests pass inside that run.
- Real DeepSeek V4 Pro import validation was not executed in this integration pass; run it against a copied 50-chapter project before merging this branch to `main`.
