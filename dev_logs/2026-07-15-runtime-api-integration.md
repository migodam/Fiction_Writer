# Runtime API Integration

## Scope

- Added the project-scoped durable runtime API and W1 event bridge.
- Preserved the legacy W1 endpoints and the existing W3-compatible stream fallback.
- Added app-lifecycle-owned sync and async LangGraph SQLite saver factories.

## Changes

- `RuntimeStore` now stores redacted run configuration, query/status helpers, tool-call queries, public decision IDs, forked attempts, and restart lease invalidation.
- W1 start verifies the CLI project root with `realpath`, creates a lineage/run/attempt, uses the attempt as the compatibility session ID, leases it, and mirrors legacy activity into monotonic durable events.
- Runtime controls are idempotent; resume records only redacted configuration and reports `needs_credentials` when no ephemeral key is provided.
- `/workflow/stream` replays runtime events by `Last-Event-ID` or `afterSequence` while leaving the no-attempt legacy stream available.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_runtime_api.py tests/test_agent_runtime.py tests/test_agent_runtime_checkpointer.py tests/test_w1_run_events.py tests/test_w1_attempt_recovery.py` -> `35 passed`.
- `sidecar/.venv/bin/python -m compileall -q sidecar/main.py sidecar/routers/runtime.py sidecar/routers/status.py sidecar/routers/workflows.py sidecar/runtime sidecar/workflows/w1_run_events.py` -> passed.
- `git diff --check` -> passed.

## Remaining Integration

- Existing workflow graph constructors still use their current in-memory checkpointers. The app now owns project-scoped sync/async SQLite saver factories for subsequent graph-by-graph adoption without connection lifetime hazards.
