# R1 W1 ChunkTruth And Fail-Closed Report

## Result

R1 fixes the specific Import Test 18 failure chain where a lost lease became an
empty extraction, then an apparently completed checkpoint and a passing review.

The new invariant is simple:

```text
semantic_complete receipt -> eligible for checkpoint commit and resume
anything else             -> never committed as semantic progress
```

## What Changed

- `sidecar/workflows/w1_truth.py` defines the shared truth and domain receipt
  contract.
- `w1_recovery.py` writes all truth receipts but stores only the contiguous
  semantic-complete extraction prefix as resumable state.
- `w1_import.py` preserves source text for normal extraction errors, records a
  durable failure artifact, rolls back partial registry changes, and keeps that
  chunk out of committed progress.
- Lease loss and unknown billable provider outcomes now escape both extraction
  paths, allowing the existing router recovery states to take over.
- Import review scans durable failure artifacts and checkpoint truth after a
  process restart, rather than trusting `_chunk_log` alone.

## Verification

`111` targeted W1 recovery, compiler, chunk-truth, and supervisor-evidence
tests pass. New regression coverage verifies both W1 paths, lease propagation,
provider human confirmation, checkpoint-derived commit eligibility, and review
after in-memory log loss.

## Residual Risks And Handoff

- A failed chunk now blocks semantic completion, but R2 still needs to make the
  Semantic Coverage Compiler and package acceptance treat the failed review as
  a hard acceptance gate.
- The existing artifact-quality fixture has a separate failure in diagnostics'
  manuscript projection discovery. It was observed during this work but is
  outside R1's assigned write scope.
- This change does not retry or resend paid provider calls. Unknown outcomes
  continue to require the existing human-confirmation flow.
