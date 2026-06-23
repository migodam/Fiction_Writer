# 2026-05-02 W2A Timeline Topology

## Scope
- Worktree: `.worktrees/w1-timeline-topology-v2`
- Branch: `codex/w1-timeline-topology-v2`
- Owned backend scope only: W1 timeline reducer/topology artifact, state contract, compiler tests, and compiler doc.

## Changes
- Preserved timeline scout fields from chunk extraction into event candidates: `eventClass`, `timelineClass`, `arcId`, `timelineLaneHint`, `causalPredecessorHints`, `forkMergeHint`, `dedupeKey`, `chapterRange`, `importanceScore`, `character_names`, and merge hints.
- Added deterministic semantic event reduction before proposal write:
  - candidate classifications: `canonical_event`, `scene_beat`, `background_reference`
  - duplicate merge signatures using exact signature plus dedupe/participants/chapter/normalized semantic title
  - explicit merge/discard reasons in `timeline_architecture.json`
- Expanded topology artifacts with event classifications, scene beats, background references, fork/merge anchors, branch rank/lane metadata, density classes, and root-branch policy hints.
- Improved branch inference to prefer arc/lane hints, then theme/location/participant fallbacks, keeping root/mainline for arc-level turning points or fallback.
- Preserved Timeline Architect branch-local `orderIndex` when writing timeline event proposals.

## Tests
- Passed: `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py`
- Passed: `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/models/state.py sidecar/prompts/w1_prompts.py`

## Residual Risks
- Semantic duplicate normalization is deterministic and covered for known Import_Test6-style 韩立 origin variants, but broader synonym coverage will improve with live Wave 3 validation.
- Full `npm run sidecar:test` remains outside this gate because the integration baseline notes legacy `src.core` failures; W1-targeted tests are green.
