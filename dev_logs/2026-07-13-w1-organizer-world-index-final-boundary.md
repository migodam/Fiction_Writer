# W1 Organizer Final World Index Boundary - 2026-07-13

## Scope

- Production change: `sidecar/supervisor/policy.py` only.
- Focused regression: `tests/test_w1_supervisor_policy.py`.
- Read-only artifact trace: `/tmp/narrative_ide_w1_live_smoke/20260713_023354/project/system/imports/live_smoke_20260713_023354_a667ca42/`.
- No network or provider call was made.

## Root Cause And Change

- The artifact's `organizer_output.json` already excluded `马副门主` with `reason: person_title`, but the final inbox still emitted it as an organization.
- Both supervisor paths replaced only `entity_registry["world_detailed"]` after `organize_project_content()`. The old flat `entity_registry["world"]` index retained LLM classifications, and `node_write_to_project()` iterates that stale index when creating world-item proposals.
- The normal and streaming policy paths now rebuild both `world` and `world_detailed` from the same final organizer survivors. The flat index uses the organizer's normalized category.
- The live-shape regression starts with organization-typed `马副门主` and alias `二愣子` in both indexes, captures the state given to `proposal_write`, and verifies they are absent while `七玄门` and `七绝堂` remain.

## Verification

- Focused regression before the fix: `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_policy.py -k organizer_replaces_stale_world_index_before_proposal_write` -> failed as expected because the stale flat index retained `马副门主` and `二愣子`.
- Focused organizer paths after the fix: `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_policy.py -k organizer && sidecar/.venv/bin/python -m pytest -q tests/test_w1_organizer.py` -> `4 passed`, then `23 passed`.
- Full relevant suites: `sidecar/.venv/bin/python -m pytest -q tests/test_w1_supervisor_policy.py tests/test_w1_organizer.py` -> `73 passed in 0.53s`.
- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py tests/test_w1_supervisor_policy.py` -> passed.
- `git diff --check -- sidecar/supervisor/policy.py tests/test_w1_supervisor_policy.py` -> passed.
