# W1 Final Evidence Binding And Reviewer Sequencing

## Scope

- Owned changes: `sidecar/workflows/w1_import.py` and focused supervisor evidence coverage.
- Explicitly untouched: `sidecar/supervisor/tools.py`, `sidecar/supervisor/policy.py`, `sidecar/workflows/w1_run_events.py`, and the live smoke runner.
- No network or paid model calls were made.

## Artifact Trace

The Flash artifact at `system/imports/sup_51096b2887` contained an `evidence_cards.json` file, but its payload was an empty array. The pre-QA supervisor materialization depended only on `source_prompt_window_ids`; final character/event objects retained deterministic chunk anchors such as `first_seen_chunk` and `chunk_id`, while Timeline Architect and the final writer remap changed the entity set after that materialization. The Fact Reviewer therefore inspected pre-write objects with no resolvable cards, producing `evidence_missing` findings for every character and event.

## Changes

- Finalized character dedupe/remap before review and reused the same deterministic snapshot in proposal staging.
- Rebuilt supervisor evidence bindings after final remaps, resolving provenance from actual prompt-window IDs or real chunk anchors only.
- Required each emitted evidence card to carry a complete raw-source span; entities without a resolvable source window receive no fabricated reference.
- Added `evidenceRefs`, `sourceSpan`, and `sourceSegmentId` to staged character and timeline-event proposal data.
- Added a regression covering duplicate remap, final reviewer input, evidence-card resolution, and captured proposal payloads with no `evidence_missing` finding.

## Verification

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_compiler.py tests/test_w1_supervisor_evidence.py tests/test_w1_reviewers_fact.py
79 passed in 2.57s

sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py tests/test_w1_supervisor_evidence.py
passed

git diff --check
passed
```

## Notes

- `node_write_to_project()` retains its existing progressive-pop memory behavior by replacing the caller registry with the finalized snapshot before consuming it.
- The live Flash run was not repeated because the requested fix and regression validation are deterministic and must not make network or paid calls.
