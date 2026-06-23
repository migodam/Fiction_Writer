# W1/W2 Fixback Acceptance — 2026-06-06

## Scope

- Accepted W1 Manuscript integration fixback.
- Accepted W2 granularity/token billing fixback.
- Updated stale `import_workflow.spec.ts` assertions from old radio/select UI to the new preset picker UI.
- Cleaned the W2 communication report so the top-level price table matches the corrected fixback pricing.

## Changes Made By Codex

| File | Change |
|------|--------|
| `tests/e2e/p1/import_workflow.spec.ts` | Replaced stale `w1-mode-*` and `w1-prompt-profile-select` expectations with `import-preset-list`, `preset-auto`, `preset-manuscript_focused`, and `preset-advanced` assertions. Preserved provider credential and custom payload coverage. |
| `communication/2026-06-05-w2-import-granularity-token-billing-report.md` | Corrected the top-level DeepSeek V4 price table and test summary to match the fixback implementation. |

## Verification

| Command | Result |
|---------|--------|
| `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -k manuscript -q` | `12 passed, 50 deselected` |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_token_ledger.py -q` | `13 passed` |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_tools.py tests/test_w1_supervisor_policy.py -q` | `112 passed` |
| `python -m py_compile sidecar/models/state.py sidecar/routers/workflows.py sidecar/workflows/w1_import.py sidecar/workflows/w1_run_events.py` | PASS |
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow_presets.spec.ts --reporter=list` | `9 passed` |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_token_cost.spec.ts --reporter=list` | `7 passed` |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts --reporter=list` | `6 passed` |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow.spec.ts --reporter=list` | `24 passed` |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/timeline_undo_transactions.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts --reporter=list` | `10 passed` |

## Acceptance Notes

- W1 Manuscript is now integrated in the current branch and verified through backend and Playwright tests.
- W2 preset payload regression is fixed; `extract_relationships=false` now reaches `w1:start`.
- W2 backend extraction toggles are wired through `w1_import.py` guards and supervisor tests pass.
- DeepSeek V4 prices now match the official DeepSeek V4 values recorded in the W2 report.
- W4 world drag/drop and W5 timeline undo transaction smoke tests remain green.

## Remaining Risks

- No live 10-chapter import was run in this acceptance pass.
- `docs/superpowers/` remains untracked and should not be staged unless explicitly scoped.
