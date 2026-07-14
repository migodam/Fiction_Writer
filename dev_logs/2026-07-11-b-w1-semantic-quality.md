# W1 Semantic/Data Quality - Worker B

## Scope
- Owned semantic reconciliation, Chinese tag localization, relationship ontology, and deterministic world organizer routing.
- Preserved concurrent A1 source-span/proposal-gate work and did not modify forbidden UI, Electron, project service, run-events, or runner paths.

## Changes
- Added `EntityMergeDecision/v1` reducer evidence for matched characters. Aliases, background, experience records, traits, notes, confidence, physical description, speech style, and arc notes are field-specific merge decisions; divergent text becomes an explicit conflict diagnostic.
- Chinese tags now translate known English editorial labels while preserving source metadata. Unknown English labels are rejected into `tag_rejections`; no Chinese-source tag is blanked.
- Added relationship ontology metadata and direction-aware dedupe. Chinese false labels such as `解惑`, `选拔`, and descriptive epithets are demoted instead of becoming relationship types.
- Organizer now emits stable notebook IDs (`world_container_<key>`) and item `containerId`s; W1 proposal write receives those targets. Organization classification wins over overlapping location characters (for example `七玄门`).

## Verification
- `python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/organizer.py sidecar/supervisor/tools.py`
  - Passed.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_semantic_quality.py tests/test_w1_organizer.py tests/test_w1_supervisor_tools.py`
  - Passed: `100 passed in 0.56s`.

## Residual Risk
- Entity merge decisions remain proposal/review evidence rather than automatic canonical mutations, preserving the Workbench acceptance gate.
