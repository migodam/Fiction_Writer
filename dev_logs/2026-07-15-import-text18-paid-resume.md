# Import Text 18 Paid Resume Runner

## Scope

- Added `tests/electron/w1_import_text18_paid_resume.mjs`.
- Added cold-start reconciliation for unfinished provider intents in `sidecar/runtime/agent_runtime.py`.
- Added `--reconcile-only` to the runner for a zero-cost real sidecar cold-start check using a fresh no-credential Electron user-data directory.
- No package script was added; invoke the runner directly to keep the paid path conspicuous.

## Safety Contract

- Default invocation is static-only. It verifies the original Import Text 18 project, the original external source, and the contained raw source all hash to `6c7cfd49949e89cecb8b00a4bd9ab374e7393ff1b4fe84a0e8a809e060cb522d`; it makes no Electron launch, bridge call, or provider call.
- Paid execution requires both `--execute-paid` and `NARRATIVE_IDE_PAID_RESUME_USER_DATA`. The selected Electron provider/model must be `deepseek` / `deepseek-v4-flash`; the runner checks the configured credential exists but never logs or serializes it.
- Before the sole `runtimeResume` bridge call it copies the entire project, checkpoint, and available project/runtime SQLite databases to an external receipt directory. It requires an interrupted, source-compatible 4/10 run and the durable `$3` budget plus fail-closed pricing/usage controls; unknown calls remain forbidden unless the explicit one-retry flag authorizes exactly one pending call.
- The runner polls durable events with a 20-minute hard wall-clock timeout. It fails on unresolved unknown outcome, authorization/credentials, source incompatibility, budget failure, or missing usage. It never invokes package acceptance.
- `--authorize-retry-once` is valid only with `--execute-paid`. When selected, recovery must expose exactly one pending unknown outcome; the runner authorizes that call once using its decision key/attempt ID, refetches and verifies durable `authorize_retry_once`, then issues the existing single `runtimeResume`. Without the flag, unknown outcomes remain fail-closed. The runner never authorizes more than one call, accepts a package, or exposes decision keys or source text.
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

## Retry Authorization Change

- Added static argument validation and the opt-in `--authorize-retry-once` paid-only path.
- The post-resume monitor tolerates only historical unknown summaries with durable `decision_state == authorize_retry_once`; any pending, cancelled, or newly surfaced unknown fails immediately. Pre-authorization still requires exactly one pending unknown and makes exactly one decision call.
- Focused no-cost regression: `node tests/electron/w1_import_text18_paid_resume.mjs --unit-test` -> PASS; no Electron, API, credential, or paid execution.
- No paid or network execution was performed for this change; validation is limited to static syntax/argument checks.
