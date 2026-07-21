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

## Final Authorized Resume And Offline Repair

- The user explicitly authorized sending only the first 10 chapters of `Import Text 18`
  to `deepseek-v4-flash` with a hard USD 3 ceiling.
- The durable attempt completed all 16 DAG tasks and committed 10/10 chunks. Provider
  history contains seven normal results and one verified `retry_consumed` result.
- Final ledger: 8 calls, 35,805 input tokens, 33,351 output tokens, `$0.014351` total;
  `$2.985649` remains. No call was made during the subsequent repair or verification.
- The attempt produced 108 proposals. All remain `pending`; none crossed the proposal gate.
- A deterministic offline migration linked 27 character and 5 timeline-event proposals
  to evidence cards/source spans, generated 119 claim-local snippets, restored supported
  character background/experience fields, and removed three empty timeline branches.
- Migration receipt and immutable preimages:
  `system/imports/lineage_68b3fe6d3172718a45f6ca66/attempts/legacy_attempt_614123c9b409771fcdf06f0c/repair_receipts/20260721T034616Z/receipt.json`.
- Final diagnostics exited 0 with every symptom flag false: 10 staged chapters, 20
  manuscript nodes, 10 scene documents, zero dangling references, zero English tags,
  zero invalid relationships, zero World contamination, and zero evidence/profile gaps.
- Final regression: W1/runtime `782 passed`; UI build and lint passed. The full repository
  baseline still has the previously documented unrelated legacy failures/errors.
- Dedicated W1 Recovery/SSE/observability/package-acceptance Playwright gate: `44 passed`.
  The monolithic legacy E2E run was also sampled and reported `250 passed, 20 failed`;
  failures are concentrated in stale unscoped fixtures and old cross-workspace smoke
  selectors. They are recorded as test-debt rather than hidden as a green gate.
