# W1 Final Character Profile Write Boundary - 2026-07-13

## Scope

- Modified: `sidecar/supervisor/tools.py`, `tests/test_w1_supervisor_tools.py`.
- Explicitly untouched: `sidecar/workflows/w1_import.py`, `sidecar/supervisor/policy.py`, and scripts.
- No network, provider, or live-import call was made.

## Artifact Trace

- Inspected `/tmp/narrative_ide_w1_live_smoke/20260713_023354/project/system/imports/live_smoke_20260713_023354_a667ca42/`.
- The 韩立 final proposal retained grounded notes but had `background: ""` and no populated experience field.
- `reduce_entities` only invokes `_normalize_character_profile_fields` while merging a cross-window character group. `minor_repair` does not touch profile fields, and policy state merges preserve that registry through `proposal_write`.
- The final `proposal_write` synthesis path then constructed `write_input` without another profile normalization pass.

## Change

- Added an evidence-gated, registry-wide character-profile normalization pass immediately after synthesis and immediately before the final slim `write_input` is built.
- The write-boundary registry now retains canonicalized variants plus only source-supported background and experience entries, with `profile_field_evidence` preserved for both fields.

## Coverage And Verification

- Added a live-smoke-shaped 韩立 regression that captures final `write_input` and asserts evidence-backed background, experience, and field provenance.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_tools.py::TestProposalWriteCharacterProfileBoundary::test_final_write_input_backfills_live_smoke_han_li_profile tests/test_w1_supervisor_tools.py::TestProposalWriteSlimWriteInput::test_unneeded_keys_evicted_before_write tests/test_w1_supervisor_tools.py::TestReduceEntities::test_backfills_major_han_li_profile_from_real_shape_evidence_notes tests/test_w1_supervisor_tools.py::TestReduceEntities::test_does_not_invent_profile_fields_from_sparse_personality_only_notes` - passed: `4 passed in 0.58s`.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_tools.py` - passed: `80 passed in 0.69s`.
- `sidecar/.venv/bin/python -m compileall -q sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
- `git diff --check -- sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
