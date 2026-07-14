# W1 Claim-Local Evidence Review

## Scope

- Owned: `sidecar/workflows/w1_import.py`, `sidecar/supervisor/reviewers/fact_reviewer.py`, and focused evidence/fact tests.
- Preserved concurrent worktree changes. Did not edit `sidecar/supervisor/tools.py`, `sidecar/supervisor/organizer.py`, or diagnostics/live-smoke scripts.
- No network or model calls.

## Changes

- Supervisor evidence cards now validate source hashes and substring hashes against the final raw source before binding to canonical entities or events.
- Invalid/stale window spans are discarded. Valid cards reconstruct a bounded source clause from explicit evidence/notes when possible, otherwise from the canonical name or alias; cards dedupe by canonical entity and local substring hash.
- Final canonical objects and staged proposals preserve the validated `evidenceRefs`, `sourceSpan`, and `sourceSegmentId`; no-reference objects have stale source fields removed.
- Fact review aggregates all usable cards per entity under per-entity snippet/token budgets. Blank cards yield `evidence_unusable`, never a high mismatch. Chinese-aware name, character/bigram, and clause matching lead the decision; Jaccard is only a weak fallback.
- Added five-character and five-event Chinese real-shape coverage with a stale duplicate window, plus aggregation/unusable-evidence reviewer coverage.

## Verification

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_evidence.py tests/test_w1_reviewers_fact.py tests/test_w1_import_compiler.py
81 passed in 2.45s

sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/reviewers/fact_reviewer.py
passed

git diff --check
passed
```

## Artifact Note

The supplied live artifact was inspected read-only: its final `raw_source.txt` hash was `7b78ecaf...6503a84f`; prior cards were not rewritten. The regression reconstructs and validates final source spans deterministically without another paid live run.
