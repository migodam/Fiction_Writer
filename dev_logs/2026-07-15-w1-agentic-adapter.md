# W1 Agentic Adapter

## Changes

- Added `sidecar/workflows/w1_agentic_adapter.py`, an isolated typed DAG adapter for validated W1 routes.
- Added durable RuntimeStore scheduling hooks, bounded tool choices, bounded Self-Ask, deterministic replan triggers, and concise decision records.
- Kept `sidecar/workflows/w1_import.py` unchanged because it is owned by another worker.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_agentic_adapter.py` -> `8 passed`.
- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_agentic_adapter.py tests/test_w1_agentic_adapter.py` -> passed.
- `git diff --check` -> passed.

## Follow-up Insertion

The exact integration insertion is reported in the delivery message; it belongs around the W1 streaming loop and is intentionally not applied here.
