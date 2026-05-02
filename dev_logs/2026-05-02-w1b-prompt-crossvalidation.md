# 2026-05-02 W1B Prompt Cross-Validation

## Scope
- Branch: `codex/w1-prompt-crossvalidate`
- Worktree: `/Volumes/migodam's-external-brain/Development/Narrative_IDE/.worktrees/w1-prompt-crossvalidate`
- Owned paths touched only: W1 prompt templates, W1 state contracts, W1 compiler doc, W1 prompt-contract tests, this dev log.

## Changes Made
- Rewrote the deep character prompt around alias/epithet reconciliation, source-language normalization, protagonist/mentor/antagonist/ally/minor story-function classification, importance calibration, `groupKey` hints, compact card limits, and anti-summary-bloat rules.
- Rewrote the deep event prompt around `eventClass`, `timelineClass`, `arcId`, `timelineLaneHint`, `causalPredecessorHints`, `forkMergeHint`, `dedupeKey`, `chapterRange`, `importanceScore`, merge hints, and canonical-event vs scene-beat separation.
- Expanded relationship and scene prompts with cross-validation signals for alias evidence, topology roles, contradiction hints, canonical event references, scene beat references, lane hints, arc IDs, and chapter ranges.
- Added the `W1_CROSS_VALIDATE_IMPORT` prompt contract and `CrossValidationArtifact` typed contract.
- Updated `dev_docs/W1_IMPORT_COMPILER.md` to describe the cross-validation artifact and prompt-level event/character contracts.
- Added prompt-contract tests to guard required fields and instructions.

## Test Results
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py` could not run in this worktree because `sidecar/.venv/bin/python` is absent.
- `sidecar/.venv/bin/python -m py_compile sidecar/prompts/w1_prompts.py sidecar/models/state.py` could not run in this worktree because `sidecar/.venv/bin/python` is absent.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py` passed: 10 passed.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m py_compile sidecar/prompts/w1_prompts.py sidecar/models/state.py` passed.
- `python3 -m py_compile sidecar/prompts/w1_prompts.py sidecar/models/state.py` passed.

## Integration Notes
- Runtime wiring for `W1_CROSS_VALIDATE_IMPORT` is intentionally not included on this branch to avoid duplicating Wave 1A window-builder or wider reducer work.
- `groupKey`, `story_function`, and event topology fields are prompt-level contract fields; existing reducers may ignore them until Integration Manager wires them into artifacts/proposals.
