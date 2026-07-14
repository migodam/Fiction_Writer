# W1 Authoritative Evidence Recovery

## Scope

- Changed: `sidecar/workflows/w1_import.py`
- Added focused regression: `tests/test_w1_supervisor_evidence.py`
- Preserved all existing dirty work. Did not edit `sidecar/supervisor/tools.py`, organizer code, or scripts.
- No network or model calls.

## Root Cause

The live-smoke artifact `live_smoke_20260713_023354_a667ca42` had final character/event IDs after dedupe and timeline finalization, but several final objects had only `[window ...]` notes or chapter labels. Their prompt-window spans carried a hash of the window-local text rather than the full raw source, so strict validation discarded every potential card. `char_4164f0ba` also bound a sentence selected from a note anchor that did not name `老张叔`, causing the remaining FactReviewer mismatch.

## Fix

- Recover an invalid prompt-window span from hash-valid final manifest segment offsets for that window's chunks.
- Recover final-item window provenance from explicit IDs, `[window ...]` notes, chunk fields, and chapter labels; only last-resort candidates that yield a real raw-source anchor become cards.
- Bind snippets to actual source clauses only. Character names are preferred as their identity claim; paraphrased titles/notes search meaningful contiguous source fragments before emitting a card.
- Persist a fresh raw-source hash and substring hash for every recovered span. Items still without an anchor remain unbound rather than receiving fabricated evidence.

## Regression

`test_final_evidence_rebuild_recovers_latest_smoke_ids_from_stale_window_spans` covers all eleven live-smoke findings:

- Characters: `char_c6c870c0`, `char_0ce896f2`, `char_0a7ef8f8`, `char_c4d00eee`, `char_c7ed8370`, `char_41854421`
- Remaining mismatch: `char_4164f0ba`
- Events: `event_4c66790e`, `event_3fa00f29`, `event_ab06693f`, `event_2ed9f858`

It asserts source-span hashes, bounded raw snippets, final-ID coverage, and zero `evidence_missing`, `evidence_entity_mismatch`, and `evidence_unusable` FactReviewer findings.

## Verification

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_compiler.py tests/test_w1_import_artifact_quality.py tests/test_w1_supervisor_evidence.py tests/test_w1_reviewers_fact.py
85 passed in 2.70s

git diff --check -- sidecar/workflows/w1_import.py sidecar/supervisor/reviewers/fact_reviewer.py tests/test_w1_supervisor_evidence.py tests/test_w1_reviewers_fact.py
passed
```
