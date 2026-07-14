# W1 Major Character Profile Backfill - 2026-07-13

## Scope

- Owned: `sidecar/supervisor/tools.py` and `tests/test_w1_supervisor_tools.py`.
- Not changed: `sidecar/workflows/w1_import.py`, reviewers, organizer, scripts, or supervisor policy.
- No network or provider call was made.

## Trace And Change

- Reviewed `live_smoke_20260713_020933_538641e3` at `/private/tmp/narrative_ide_w1_live_smoke/20260713_020933/project/system/imports/`.
- The 韩立 proposal had a grounded summary, provenance-tagged notes, and evidence refs but emitted `background: ""`; no `experience` was present.
- `reduce_entities` now canonicalizes `experience`/`experiences`, `personality_traits`/`traits`, and `evidence_refs`/`evidenceRefs` before review/proposal.
- For major/protagonist/main or densely mentioned characters with provenance, it backfills an empty background only from identity/origin/family notes or an identity/origin summary, and adds experience entries only from action/change notes. It never uses personality traits as profile facts.
- Backfilled fields retain their supporting refs in `profile_field_evidence`; original evidence refs remain preserved.

## Coverage

- Added a real-shape 韩立 regression covering field variants, evidence refs, identity/family background evidence, and action-note experience backfill.
- Added a sparse major-character case proving personality-only notes do not manufacture background or experience.

## Verification

- `python3 -m py_compile sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_tools.py` - passed: `79 passed in 0.61s`.
- `git diff --check -- sidecar/supervisor/tools.py tests/test_w1_supervisor_tools.py` - passed.
