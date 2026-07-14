# W1 Live Smoke Watchdog - 2026-07-13

## Scope

- Owned paths: `tools/w1_live_smoke_10ch.py`, `tests/test_w1_live_smoke_runner.py`, and this log.
- No sidecar production workflow, UI, Electron, or provider configuration was changed.
- No live API call was made and no provider key was read into test output.

## Changes

- Moved `run_streaming` consumption into a producer task that sends updates through an `asyncio.Queue`; the runner consumer can enforce wall-clock timeout while the stream awaits I/O without producing updates.
- Added a separate 15-second default heartbeat task (`--heartbeat-seconds`) that prints a flushed status line and atomically writes `heartbeat.json` with `elapsed`, `last_update_age`, `last_node`, and `update_count`.
- On timeout or terminal budget/auth update, the runner cancels and awaits the producer. Producer `CancelledError` is re-raised unless cancellation was explicitly initiated by the runner.
- `final_result.json` records `terminal.status: "timeout"` for watchdog timeouts.
- Added the outer-process hard-timeout recommendation: `gtimeout --signal=TERM --kill-after=30s 1830s <runner-command>`. GNU timeout exit code `124` means the outer timeout fired. This remains necessary if code blocks the entire Python event loop synchronously, since no asyncio task can run during that condition.

## Tests

- `sidecar/.venv/bin/python -m py_compile tools/w1_live_smoke_10ch.py` - passed.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_live_smoke_runner.py` - 11 passed.
- `git diff --check` - passed.

## Coverage Added

- Silent async generator times out and is cancelled.
- Heartbeat artifact is written with the required fields.
- Normal update flow records the latest node and update count.
- Runner persists a timeout terminal state to `final_result.json`.

## 2026-07-14 Cancellation Follow-up

- A single approved `deepseek-v4-pro` final run was attempted with the watchdog, `$8` cost ceiling, and 30-minute inner/outer deadlines.
- After 12 minutes the first provider request still had no settled usage (`0` calls, `0` tokens, `$0`); the run was stopped because the remaining deadline could not complete the expected extraction calls.
- Manual interruption exposed four pre-created extraction coroutines that had not yet been awaited. Budgeted extraction now creates each prompt coroutine lazily, so cancelling an in-flight paid call leaves no pending sibling coroutine and no `never awaited` warning.
- Added a cancellation regression asserting that only the active prompt is created before cancellation.
- Focused cancellation/budget tests: `10 passed`.
- Full W1 backend suite: `659 passed in 9.92s`.
