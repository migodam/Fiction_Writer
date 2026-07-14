# W1 Supervisor Character Dedupe - 2026-07-13

## Scope

- Owned production path: `sidecar/supervisor/tools.py`.
- Targeted test path: `tests/test_w1_supervisor_tools.py`.
- Forbidden paths untouched: `sidecar/supervisor/policy.py`, `sidecar/workflows/w1_import.py`, and `runner`.
- No live/provider/paid call was made.

## Changes

- Added deterministic pre-review character reduction to `reduce_entities` for candidates emitted from separate supervisor windows.
- Chinese name matching uses NFKC normalization and strips spacing/punctuation; candidate grouping records `character:<normalized-name>` as a stable dedupe key instead of grouping random `char_*` ids.
- A merge requires a shared alias, provenance-shaped evidence, overlapping window, or shared declared identity key. Exact normalized canonical names alone remain insufficient.
- Explicit identity-disambiguator conflicts and same-name candidates without corroboration remain separate and are recorded in `semantic_conflicts`.
- Merges preserve background, experience/experiences, aliases, traits/personality traits, notes, confidence, and evidence fields. Event and relationship character references are remapped to the surviving candidate.
- `reducer_artifact.json` now includes intra-import `duplicate_candidates` and `EntityMergeDecision/v1`-shaped `character_merge_decisions` before reviewer execution.

## Coverage

- Added a zero-cost fixture with 韩立 across three candidate records and 张铁 across two records. It verifies one surviving proposal per person, no field loss, stable key, decisions, and relationship remapping.
- The 韩立 fixture covers both shared-alias and overlapping-window identity evidence.
- Added same-name 王二 records with incompatible identity disambiguators to verify no accidental union and an audit conflict.

## Verification

- `python3 -m py_compile sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
- Isolated zero-dependency reducer-helper fixture - passed; verified merge, field union, event/relationship remap, and protected same-name collision.
- `git diff --check -- sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
- `pytest -q tests/test_w1_supervisor_tools.py::TestReduceEntities::test_merges_cross_window_characters_by_evidence_alias_and_stable_key` - not run: `pytest` is not installed in this environment.
- `python3 -m unittest tests.test_w1_supervisor_tools.TestReduceEntities.test_merges_cross_window_characters_by_evidence_alias_and_stable_key` - blocked at import: `langchain_core` is unavailable in the active interpreter.
