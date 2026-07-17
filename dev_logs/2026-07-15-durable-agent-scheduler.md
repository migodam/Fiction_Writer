# Durable Agent Scheduler

## Changes

- Added RuntimeStore migration 5 for durable task plans, task DAG state, dead letters, and memory records.
- Added transactional task claiming, dependency blocking, exact resource fence maps, stale-claim recovery, cancellation, and dead-letter recovery.
- Added RuntimeStoreScheduler, which reconstructs scheduling state from SQLite after restart.
- Added durable memory retention, provenance/confidence validation, secret and hidden-reasoning rejection, and deterministic compaction.
- Added interrupted attempt lifecycle handling for restarts and expired leases.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_agent_runtime.py tests/test_agentic_control.py tests/test_durable_agent_scheduler.py` -> `35 passed`.
- `sidecar/.venv/bin/python -m py_compile sidecar/runtime/agent_runtime.py sidecar/agentic/scheduler.py tests/test_agent_runtime.py tests/test_durable_agent_scheduler.py` -> passed.
- `git diff --check` -> passed.

## Shared-Surface Follow-up

- `sidecar/main.py` legacy recovery registration should set its newly created attempt to `interrupted` immediately after `create_attempt(...)`, because it represents recovered work rather than an actively leased worker.
