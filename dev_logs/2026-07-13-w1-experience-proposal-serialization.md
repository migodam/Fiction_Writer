# W1 Character Experience Proposal Serialization - 2026-07-13

## Scope

- Modified: `sidecar/workflows/w1_import.py`, `tests/test_w1_import_compiler.py`.
- No frontend, supervisor, network, provider, or live-import changes.

## Artifact Trace

- Inspected `/tmp/narrative_ide_w1_live_smoke/20260713_025442/project/system/inbox.json`.
- The final 韩立 and 墨大夫 character proposals included grounded `background`, notes, evidence references, and source spans, but omitted both `experience` and `experiences`.
- The supervisor profile backfill runs before proposal writing and supplies source-backed `experience` plus `profile_field_evidence`; the W1 create payload did not serialize either field.

## Change

- Added a write-boundary serializer that accepts both `experience` and `experiences`, deduplicates without adding claims, and emits frontend-compatible `Character.experience` rows with `id`, `chapter`, `fact`, and optional `evidence`.
- Preserved nonempty `profile_field_evidence` on character-create proposals. The Workbench acceptance consumer applies supported character-create fields directly.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_compiler.py::test_character_proposals_serialize_final_flash_experience_for_acceptance tests/test_w1_import_compiler.py::test_character_card_proposals_stay_slim_by_default tests/test_w1_import_compiler.py::test_matched_character_merge_writes_an_accepted_update_proposal` -> `3 passed`.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_import_compiler.py` -> `69 passed`.
- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py tests/test_w1_import_compiler.py` -> passed.
- `git diff --check -- sidecar/workflows/w1_import.py tests/test_w1_import_compiler.py dev_logs/2026-07-13-w1-experience-proposal-serialization.md` -> passed.
