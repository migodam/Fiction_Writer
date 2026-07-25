# Runtime Resume Budget Guard

## Changes

- Added one pure, model-aware W1 budget policy shared by workflow start and recovery.
- Normalized empty, partial, and legacy persisted budgets on every resume.
- Limited Flash runs to `$3` and Pro runs to `$8`.
- Enforced call, input-token, output-token, total-token, unknown-pricing, and missing-usage guards.
- Made resume overrides an intersection: callers may tighten persisted limits but cannot relax them.
- Rejected unknown keys, invalid types, negative values, `NaN`, and `Infinity` before worker launch.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_runtime_api.py tests/test_w1_harness_product_path.py`
  - `34 passed`
- `sidecar/.venv/bin/python -m pytest -q tests/test_agent_runtime.py tests/test_agent_runtime_checkpointer.py tests/test_harness_runtime.py tests/test_project_backend_runtime.py tests/test_runtime_api.py tests/test_w1_*.py`
  - `926 passed`
