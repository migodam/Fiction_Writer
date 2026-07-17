# Agent Runtime Resilience Documentation Log

**Date:** 2026-07-15
**Scope:** Durable runtime implementation and final integrated verification.

## Recorded Implementation

- Per-project `RuntimeStore` is SQLite WAL at `system/runtime/agent_runtime.db`; W0-W7 use a separate project-scoped durable LangGraph SQLite checkpointer.
- W1 has lineage/attempt isolation, cache identity, atomic checkpoint receipts, conservative legacy recovery, runtime recovery endpoints/IPC/UI, immutable checkpoint fork, and `ArtifactRef` v2 validation.
- Project package persistence uses prepared journal manifests, preimages, rename/commit markers, and idempotent recovery. It is not power-loss durable because the file bridge has no `fsync`.
- Runtime metadata implements redaction, budget ceilings, resource fence tokens, durable tool `unknown_outcome` records, and event cursors. Recovery Center provides the required retry-once/cancel human gate.

## Evidence Commands

```bash
pytest -q tests/test_agent_runtime.py tests/test_agent_runtime_checkpointer.py tests/test_agentic_control.py tests/test_runtime_api.py tests/test_w1_attempt_recovery.py tests/test_workflow_durable_checkpointers.py
npx playwright test tests/e2e/p1/import_recovery.spec.ts tests/e2e/p1/project_transaction_recovery.spec.ts
```

Final results recorded on 2026-07-17:

- Integrated W1/runtime pytest: **781 passed** in 7.93s.
- Package/recovery/SSE/transaction Playwright: **44 passed** in 11.1s.
- UI lint/build: **PASS**.
- Electron runtime smoke and sidecar lifecycle: **PASS**.
- Disposable real fixture: **PASS**, including 89-proposal acceptance and restart.
- Original benchmark repair-only: **PASS**, 89 pending and canonical hashes unchanged.
- Real Import Text 18 cold-start reconciliation: **PASS**, five results plus one human-gated unknown outcome.

The Python suite is durability/API evidence. The Playwright files cover mocked renderer/IPC recovery and transaction crash recovery, not live provider execution or actual import-fixture acceptance.

## Remaining External Gate

Import Text 18 cannot reach 10/10 until the user explicitly decides whether to
retry the single unknown DeepSeek call. Automatic retry is prohibited.
