# R1 W1 ChunkTruth Fail-Closed

## Delivered

- Added explicit W1 chunk truth values: `semantic_complete`, `manuscript_only`,
  `failed`, and `unknown_outcome`.
- Added a total receipt for characters, events, world, relationships, and
  scenes on every W1 extraction record.
- Checkpoints now derive their committed contiguous prefix only from
  `semantic_complete` receipts. Failed chunk text is retained as an artifact
  but is not resumable semantic state.
- Both legacy and supervisor extraction loops propagate `LeaseLostError` and
  `ProviderCallRequiresHumanConfirmation` to the router. Ordinary errors write
  a durable failure artifact and a failed extraction without committing it.
- Reviewer now reads durable checkpoint truth and `chunks/*_failures.json` in
  addition to the in-memory console log. Durable failures make the review fail.

## Tests

- Passed: `sidecar/.venv/bin/python -m pytest tests/test_w1_attempt_recovery.py tests/test_w1_import_chunk_truth.py tests/test_w1_import_compiler.py tests/test_w1_supervisor_evidence.py -q`
- Result: `111 passed`.
- Also ran the artifact/diagnostics quality group. One pre-existing diagnostic
  fixture failure remains in `tests/test_w1_import_artifact_quality.py`:
  `scene_nodes_with_content == 0` where the fixture expects `10`. R1 did not
  modify `tools/w1_import_diagnostics.py`, its fixtures, or manuscript layout.

## Follow-up Risk

- R2 must make semantic coverage and package acceptance reject the failed
  review, rather than merely surface it in Workbench.
- The diagnostics workstream must make fixture and attempt-aware manuscript
  projection discovery consistent before it becomes a release gate.
