# Import Text 18 Paid Resume Runner

## Scope

- Added `tests/electron/w1_import_text18_paid_resume.mjs`.
- Added cold-start reconciliation for unfinished provider intents in `sidecar/runtime/agent_runtime.py`.
- Added `--reconcile-only` to the runner for a zero-cost real sidecar cold-start check using a fresh no-credential Electron user-data directory.
- No package script was added; invoke the runner directly to keep the paid path conspicuous.

## Safety Contract

- Default invocation is static-only. It verifies the original Import Text 18 project, the original external source, and the contained raw source all hash to `6c7cfd49949e89cecb8b00a4bd9ab374e7393ff1b4fe84a0e8a809e060cb522d`; it makes no Electron launch, bridge call, or provider call.
- Paid execution requires both `--execute-paid` and `NARRATIVE_IDE_PAID_RESUME_USER_DATA`. The selected Electron provider/model must be `deepseek` / `deepseek-v4-flash`; the runner checks the configured credential exists but never logs or serializes it.
- Before the sole `runtimeResume` bridge call it copies the entire project, checkpoint, and available project/runtime SQLite databases to an external receipt directory. It requires an interrupted, source-compatible 4/10 run, no unknown calls, and the durable `$3` budget plus fail-closed pricing/usage controls.
- The runner polls durable events with a 20-minute hard wall-clock timeout. It fails on unknown outcome, authorization/credentials, source incompatibility, budget failure, or missing usage. It does not call the unknown-outcome authorization route and it never invokes package acceptance.
- Success requires a non-secret usage ledger with actual calls and cost no greater than `$3`, a durable 10/10 contiguous checkpoint/extraction prefix, pending proposals, and zero accepted proposals. The external receipt contains only status, timestamps, source hash, model, costs, counts, and backup filenames.

## Validation

- `node --check tests/electron/w1_import_text18_paid_resume.mjs`
- `node tests/electron/w1_import_text18_paid_resume.mjs --reconcile-only` -> PASS in 5.2s: real Electron/sidecar startup, interrupted + one pending unknown outcome, checkpoint preserved at 4/10; no resume, settings, API key, or provider call.
- `sidecar/.venv/bin/python -m pytest -q tests/test_agent_runtime.py` -> `18 passed`

## Paid Execution Result

- DeepSeek authentication returned HTTP 200.
- One explicit paid Resume was executed with the USD 3 ceiling.
- Five provider calls produced durable results; one remained in flight until the
  20-minute hard timeout. No retry was issued.
- The checkpoint remained atomically at 4/10; no package was accepted.
- Failure receipt: `/Users/migodam/narrative-ide-recovery-receipts/import-text18-2026-07-17T14-30-28-317Z/failure.json`.
- A real zero-cost cold start then reconciled the attempt to `interrupted`, with
  five results and one pending `unknown_outcome` human decision.

## Cold-Start Reconciliation

- On sidecar restart, running attempts become `interrupted` and unfinished provider intents become `unknown_outcome` with `runtime_interrupted`; completed provider results remain unchanged.
- The transition is transactional and idempotent. Recovery still requires an explicit human decision before any retry.
- Focused runtime coverage uses five durable provider results plus one unfinished intent and verifies the intent remains human-gated across repeated restart reconciliation.
