# W1 Offline Replay Legacy Runtime Bridge

Date: 2026-07-25

## Changes

- Added a strict `w1-legacy-identity-bridge/v1` path to
  `tools/w1_offline_replay_attempt.py` for attempts that lack legacy
  `completed_domains` receipts.
- The bridge accepts only one matching W1 runtime run and verifies source hash,
  model, exact usage totals, all result-status tool calls, every response
  artifact path/hash, and start/success event pairs for every window/domain.
- Replay now runs the same deterministic registry/evidence/profile finalization
  used at proposal staging before compiling semantic coverage. Evidence-bound
  identity clauses can fill a character background; no generated prose is used.
- Tightened scene-event linkage: shared source chunks no longer create links.
  Source-span overlap or a shared evidence receipt is required.

## Canary Dry Run And Applied Package

- Project: `/tmp/narrative_ide_w1_flash_canary_retry_authorized_20260725/20260725_073831/project`
- Source attempt: `8d964bdb-e53d-4f88-910a-14980328da2b`
- Runtime bridge: verified for 3 windows x 5 domains, 22 result calls, and 22
  response artifact hashes. Runtime lineage `85fb53f1-6097-44fc-aded-7be39a70c701`
  differs from artifact lineage `lineage_6a5a451c45289c50e681f9d8` and is recorded
  as a legacy identity bridge.
- No provider was called during replay. The existing usage ledger remains 22
  calls, 190252 tokens, and USD 0.034208.
- The deterministic dry run now has zero semantic blocking findings. It keeps
  six `scene_missing_event_link` findings as warnings rather than fabricating
  event links from a shared chunk.
- The final applied replay attempt is
  `system/imports/lineage_6a5a451c45289c50e681f9d8/attempts/replay_99b38a49c8d4`.
  It has a new attempt manifest, verified copied usage ledger, raw source,
  staged manuscript projection, semantic report, proposal receipts, and an
  `offline_replay_receipts/receipt.json` with five hash-recorded backups.
- The package has 74 pending proposals: 19 characters, 1 timeline branch, 5
  timeline events, 7 World containers, 12 World items, 10 relationships, 10
  chapters, and 10 scenes. Canonical counts remain zero.
- The compiler graph is atomic, has 134 resolved edges, no blocking errors,
  and no dangling references. The replay tool now replaces only stale pending
  proposals belonging to the same W1 lineage after backing up Inbox; it rejects
  an empty Inbox, a non-atomic graph, or a mismatch between proposal receipts
  and the pending package instead of reporting a false `applied` result.
- All relationship proposals use the Chinese allowlist. `韩父` is not a World
  item, action labels are absent from the relationship table, and the
  Supervisor production path now uses the same evidence-backed relocation and
  fail-closed relationship normalization as offline replay.

## Verification

- `212 passed` across `tests/test_w1_semantic_coverage_compiler.py`,
  `tests/test_w1_semantic_review.py`, `tests/test_w1_import_compiler.py`,
  `tests/test_w1_offline_replay_attempt.py`, `tests/test_w1_supervisor_tools.py`,
  `tests/test_w1_supervisor_semantic_relocation.py`, and
  `tests/test_w1_import_diagnostics.py`.
- `python -m py_compile` and `git diff --check` passed.
- `tools/w1_import_diagnostics.py ... --lineage-id
  lineage_6a5a451c45289c50e681f9d8 --attempt-id replay_99b38a49c8d4
  --fail-on-threshold --format json` exited 0. Every diagnostic symptom flag
  is false.

## Remaining Review Notes

- The package intentionally remains `pending` for Workbench review; no
  canonical data was accepted.
- Six scene-to-event links remain review warnings because their source evidence
  does not prove an automatic link. This is deliberate fail-closed behavior.
- The quality reviewer records 12 thin character-card observations. They are
  warnings, not semantic blockers, and should be addressed in a later quality
  pass without weakening the proposal gate.
