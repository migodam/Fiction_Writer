# 2026-05-24 W1 Import UI Worker C

## Scope
- Upgraded the W1 Import modal profile selector with profile explanations for fast, balanced, deep, and custom.
- Added Custom expert mode controls for quality target, window sizing, character granularity, event density, topology depth, world strictness, validation strictness, rerun budget, and language policy.
- Wired `custom_profile_config` and `orchestrator_overrides` through UI store, Electron API typings, and the W1 router request/session shape.
- Added optional runtime status rendering for current tool, window, chapter range, orchestrator phase, judge score, rerun reason, converge status, and judge artifact summary.
- Registered new W1 selectors in `dev_docs/TEST_SELECTORS.txt`.

## Tests
- `npm run ui:lint` passed.
- `npm run ui:build` passed.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow.spec.ts` passed, 21/21.
- `sidecar/.venv/bin/python -m py_compile sidecar/routers/workflows.py` passed.

## Notes
- Deep and Custom now default to supervisor/orchestrator enabled from the UI payload.
- Sidecar changes were limited to `sidecar/routers/workflows.py` request/status coordination; supervisor policy/tool behavior remains Worker A scope.
