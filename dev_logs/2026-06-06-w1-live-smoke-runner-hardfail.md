# W1 Live Smoke Runner + Hard-Fail Guard — 2026-06-06

## Scope

- Added a gated direct 10-chapter W1 smoke runner.
- Used the prepared `凡人修仙传_前10章.txt` fixture.
- Fixed supervisor policy so extraction-wide API/model failures stop before proposal write.
- Re-ran backend/frontend gates and updated communication report.

## Key Files

- `tools/w1_live_smoke_10ch.py`
- `sidecar/supervisor/policy.py`
- `tests/test_w1_supervisor_policy.py`
- `tests/e2e/p1/import_activity_status.spec.ts`
- `communication/2026-06-06-w1-import-p0-bug-checklist.md`
- `communication/2026-06-06-w1-live-smoke-runner-and-hardfail-report.md`

## Smoke Attempts

- `/tmp/narrative_ide_w1_live_smoke/20260606_044105`: exposed old false-success behavior after connection failures.
- `/tmp/narrative_ide_w1_live_smoke/20260606_044555`: after policy fix, run correctly ended as hard fail with zero proposals.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py tools/w1_live_smoke_10ch.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_artifact_quality.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_organizer.py tests/test_w1_reviewers_quality.py -q`
- `npm run ui:build`
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts tests/e2e/p1/global_undo.spec.ts --reporter=list`
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/world_hierarchy.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts --reporter=list`
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts tests/e2e/p1/import_workflow.spec.ts tests/e2e/p1/import_quality_status.spec.ts --reporter=list`

## Notes

- External DeepSeek live execution was not completed because Codex security review blocked sending local manuscript content to an external API without explicit user approval.
- This is a correct safety boundary. User can run the Electron smoke manually, or explicitly approve a risk-aware external API run in a later turn.

## Continuation Fixes

- Added `_quality_probe_failures()` and `_smoke_result_exit_code()` to make the live runner fail non-zero when output quality is unacceptable even if the workflow reports `done`.
- Added `tests/test_w1_live_smoke_runner.py`.
- Fixed `run_supervisor_policy()` and streaming policy so `budget_exhausted` stops before reduce/judge/proposal_write.
- Strengthened `TestPolicyBudgetExhaustedStop` to assert `judge_import` and `proposal_write` are not called.
- Added real `Meta+Z` Playwright coverage for post-import undo.

## Continuation Verification

- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_live_smoke_runner.py tests/test_w1_import_artifact_quality.py -q` -> 54 passed.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/global_undo.spec.ts --reporter=list` -> 6 passed.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_smoke_acceptance.spec.ts tests/e2e/p1/world_item_drag_drop.spec.ts tests/e2e/p1/world_hierarchy.spec.ts --reporter=list` -> 10 passed.
- `npm run ui:build` -> PASS.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/writing_manuscript_import_display.spec.ts tests/e2e/p1/global_undo.spec.ts tests/e2e/p1/character_relationship_flow_layout.spec.ts tests/e2e/p1/import_activity_status.spec.ts --reporter=list` -> 20 passed.

## Timeout / Token Ledger Follow-Up

- Root cause: frontend W1 polling used a fixed 30-minute wall-clock loop and cancelled regardless of token/activity progress.
- Fix: 30-minute cancellation now requires true silence: no active API calls, idle for 30 minutes, no token progress for 30 minutes, and no activity progress for 30 minutes.
- Safety retained: 4-hour absolute timeout.
- Verification: `npm run ui:build` PASS; `import_activity_status.spec.ts`, `import_token_cost.spec.ts`, and `import_workflow.spec.ts` -> 35 passed.
