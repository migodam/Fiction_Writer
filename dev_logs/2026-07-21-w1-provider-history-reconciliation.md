# W1 Provider History Reconciliation

## Incident

An interrupted `Import Text 18` resume had a verified provider response artifact,
but its checkpoint skipped the node that would normally read that cache entry.
The authorized unknown call therefore remained unresolved and blocked the next
paid operation.

## Changes

- Restore durable provider-call usage immediately after the W1 budget ledger is configured.
- Consume an authorized unknown only when model, message hash, lineage, version hashes,
  artifact contract, artifact hash, and filesystem safety checks all match.
- Keep authorized unknown calls without a verified artifact behind the existing human gate.
- Make identical budget configuration idempotent so standard and supervisor entry points
  cannot reset restored usage.
- Allow the paid recovery harness to reuse an already durable authorization and monitor
  only events emitted after the current resume action.
- Added atomic task-claim heartbeats that renew the DAG claim and every resource fence.
- W1 now heartbeats the active durable task while an async node is silent, including
  long provider calls, and records a fenced run as `interrupted` instead of leaving it
  visibly `running`.

## Validation

- W1/runtime regression suite: `766 passed`.
- Focused provider, budget, and backend contract suite: `58 passed`.
- Paid recovery harness unit checks: passed.
- Full repository suite: `818 passed`, with 11 unrelated legacy failures and 7 setup
  errors (missing legacy `tests/api_key.txt` and removed prototype `ProjectMemory` APIs).
- No provider request was made while implementing or testing this fix.

## Paid Resume Observation

- The first post-fix resume safely reconciled the prior unknown result and restored five
  historical calls into the budget ledger.
- One new DeepSeek V4 Flash call completed and was persisted. Total observed usage was
  18,337 input tokens and 30,562 output tokens, costing `$0.011125` under the configured
  price table.
- This exposed a separate 30-second DAG task-claim expiry during
  `synthesize_relationships`; no response was lost and no call remained unknown.
- The run was stopped with checkpoint/canonical data unchanged and a failure receipt at
  `/Users/migodam/narrative-ide-recovery-receipts/import-text18-2026-07-21T03-20-08-203Z/failure.json`.
- Task-claim heartbeat coverage was added before another paid resume. Updated W1/runtime
  regression suite: `772 passed`.
