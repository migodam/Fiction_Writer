# W1 Runtime Lease Heartbeat

## Changes

- Added a lifetime-scoped async lease heartbeat to `sidecar/routers/workflows.py` for W1 runs.
- The heartbeat renews before silent provider work, continues while a run is running or paused, and races stream reads so a fenced lease interrupts a silent worker.
- Added test-only lease TTL and heartbeat interval configuration, with production defaults of 60 seconds and 20 seconds.
- Teardown now stops and joins the heartbeat task on normal completion, cancellation, and lease loss.

## Files Modified

- `sidecar/routers/workflows.py`
- `tests/test_w1_run_events.py`
- `dev_logs/2026-07-21-w1-runtime-lease-heartbeat.md`

## Validation

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_run_events.py -k 'heartbeats_during_silent or cancellation_stops_lease or heartbeat_fencing or consumes_unknown'` -> `4 passed, 25 deselected`.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_run_events.py` -> `29 passed`.
- `sidecar/.venv/bin/python -m py_compile sidecar/routers/workflows.py tests/test_w1_run_events.py` -> passed.
- `git diff --check` -> passed.
- Added deterministic coverage for silent work beyond TTL, heartbeat cleanup on cancellation, and replacement-owner fencing.
