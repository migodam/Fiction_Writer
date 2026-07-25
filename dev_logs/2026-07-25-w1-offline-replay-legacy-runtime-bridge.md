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

## Canary Dry Run

- Project: `/tmp/narrative_ide_w1_flash_canary_retry_authorized_20260725/20260725_073831/project`
- Source attempt: `8d964bdb-e53d-4f88-910a-14980328da2b`
- Runtime bridge: verified for 3 windows x 5 domains, 22 result calls, and 22
  response artifact hashes. Runtime lineage `85fb53f1-6097-44fc-aded-7be39a70c701`
  differs from artifact lineage `lineage_6a5a451c45289c50e681f9d8` and is recorded
  as a legacy identity bridge.
- No provider was called. The existing usage ledger remains 22 calls, 190252
  tokens, and USD 0.034208.
- Semantic gate remains blocked by relation data: 2 missing endpoints, 1 action
  relationship, and 14 relationship types outside the Chinese long-term
  allowlist. No `--apply` was run, so no new pending package or receipt was
  created for this version.

## Verification

- `270 passed` across the W1 replay/compiler/supervisor/semantic targeted suite.
- `python -m compileall` and `git diff --check` passed.
