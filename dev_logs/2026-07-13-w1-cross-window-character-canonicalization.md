# W1 Cross-Window Character Canonicalization

## Scope
- Owned: `sidecar/supervisor/tools.py`, `tests/test_w1_supervisor_tools.py`, and the focused fixture under `tests/fixtures/`.
- Not changed: `sidecar/workflows/w1_import.py`, `sidecar/supervisor/policy.py`, `sidecar/workflows/w1_run_events.py`, or the smoke runner.

## Trace
- Reviewed live import artifact: `/tmp/narrative_ide_w1_live_smoke/20260713_013817/project/system/imports/sup_51096b2887`.
- Extraction enters `entity_registry` in `extract_window`, then flows through `reduce_entities`, `minor_repair`, and `proposal_write`.
- The artifact's `reducer_artifact.json` contained no cross-window character merge decisions. Its `cross_validation.json` also contained no duplicate character signal.
- `system/inbox.json` already contained one proposal each for 韩立, 张铁, 墨大夫, 舞岩, 岳堂主, and 王护法, showing that downstream write-time behavior could hide the missing deterministic reducer decision.

## Change
- Exact normalized canonical names now merge deterministically unless explicit identity-disambiguator evidence conflicts.
- Merges union aliases, background, experience, traits, notes, evidence, and preserve the maximum confidence.
- Event reference variants, synthesized relationships, and raw relationship candidate references are remapped to the selected canonical IDs before minor repair and proposal write.
- Added a regression fixture shaped from the live smoke identities and window provenance. It asserts one final write-input character per reported duplicate name while preserving two explicitly disambiguated 王二 identities.

## Verification
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_tools.py`
- Result: `77 passed in 0.68s`.
