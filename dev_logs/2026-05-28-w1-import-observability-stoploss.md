# W1 Import Observability and Stop-Loss Fix — 2026-05-28

## Summary

This session fixes a P0 product failure: W1 import could appear silent for long stretches because the UI only displayed chunk logs, while supervisor mode works on prompt windows and may not produce chunk output until a window finishes. A real import could therefore spend money while the user saw no meaningful activity.

The fix adds a real-time W1 activity feed, visible frontend activity status, stronger cancellation, shorter silent timeout behavior, and 402/budget-exhausted stop-loss messaging. No prompt behavior, import quality logic, or benchmark path was changed.

## Files Changed

- `sidecar/workflows/w1_run_events.py` — new in-memory activity feed with event ordering, active-call tracking, cancellation flag, status summary, and secret redaction.
- `sidecar/routers/workflows.py` — W1 status/console now expose activity fields; start stores background tasks; cancel cancels the task and emits activity.
- `sidecar/supervisor/policy.py` — supervisor streaming emits validation/planning/window/batch/reduce/repair/timeline/QA/judge/proposal_write activity events and checks cancellation before new work.
- `sidecar/supervisor/tools.py` — `extract_window` emits per-prompt start/success/fail events and 402 budget-exhausted events.
- `sidecar/workflows/w1_import.py` — legacy W1 path also emits basic activity events.
- `src/electron/main.js` — `w1:console` accepts `activity_after` and returns activity entries.
- `src/ui-react/services/electronApi.ts` — activity/status result types added.
- `src/ui-react/store.ts` — stores activity log/status, surfaces polling warnings, hard-cancels after 30 minutes instead of waiting 3 hours.
- `src/ui-react/components/ImportWorkflow.tsx` — adds Current AI Activity card, idle warning, connection warning, active API calls, elapsed/idle display, and budget-exhausted highlight.
- `src/ui-react/components/ImportConsole.tsx` — defaults to activity feed and keeps chunk logs as detail layer.
- `tests/test_w1_run_events.py` — unit coverage for event ordering, active calls, cancel flag, redaction.
- `tests/test_w1_supervisor_policy.py` — activity/cancel supervisor tests.
- `tests/test_w1_supervisor_tools.py` — prompt-level activity and 402 activity tests.
- `tests/e2e/p1/import_activity_status.spec.ts` — Playwright coverage for activity card, idle warning, and budget-exhausted UI.
- `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md` — documents the activity feed, status fields, cancellation, and silent-idle stop-loss.

## Product Behavior

- Users now see "Current AI Activity" while import is running, even if no chunks have completed.
- Activity shows phase/tool/window/chapter/prompt, active API calls, elapsed time, idle time, and the last message.
- The console now shows activity events before chunk logs exist.
- A 90-second idle period shows an amber warning instead of staying silent.
- A 30-minute hard timeout calls cancel to reduce silent spend risk.
- 402/insufficient balance appears as a red budget-exhausted stop-loss state.
- Cancel now attempts to stop the background task and prevents new window/rerun work from starting.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_run_events.py sidecar/routers/workflows.py sidecar/supervisor/policy.py sidecar/supervisor/tools.py sidecar/workflows/w1_import.py` — PASS
- `sidecar/.venv/bin/python -m pytest tests/test_w1_run_events.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py -q` — 135 passed
- `npm run ui:build` — PASS
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts --reporter=list` — 3 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow.spec.ts --reporter=list` — 21 passed

## Cost Ledger

- Live model/API calls: none
- full50 benchmark: not run
- Zero-cost tests only: Python unit/regression, TypeScript build, Playwright mocks
- Provider credentials used: none

## Deferred

- Precise dollar/token accounting is still not implemented; current UI shows active API calls and elapsed/idle time only.
- In-flight HTTP requests may not be interruptible at the transport level, but cancellation now prevents new work and cancels the background task.
- A future approved 10-chapter flash smoke should verify real provider behavior and 402 stop-loss in production-like conditions.
