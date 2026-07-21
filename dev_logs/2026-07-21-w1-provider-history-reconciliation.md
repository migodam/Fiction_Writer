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

## Validation

- W1/runtime regression suite: `766 passed`.
- Focused provider, budget, and backend contract suite: `58 passed`.
- Paid recovery harness unit checks: passed.
- Full repository suite: `818 passed`, with 11 unrelated legacy failures and 7 setup
  errors (missing legacy `tests/api_key.txt` and removed prototype `ProjectMemory` APIs).
- No provider request was made while implementing or testing this fix.
