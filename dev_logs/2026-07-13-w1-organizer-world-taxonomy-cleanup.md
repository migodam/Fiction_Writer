# W1 Organizer World Taxonomy Cleanup - 2026-07-13

## Scope

- Owned production path: `sidecar/supervisor/organizer.py`.
- Focused regression path: `tests/test_w1_organizer.py`.
- Current Flash artifact inspected: `/private/tmp/narrative_ide_w1_live_smoke/20260713_020933/project/system/imports/live_smoke_20260713_020933_538641e3/organizer_output.json`.
- No network, provider, or paid model call was made.

## Changes

- Expanded deterministic character-registry matching to canonical names and aliases; added a narrow lexical `person_title` exclusion for forms such as `马副门主`, `王门主`, and `岳堂主`.
- Added deterministic `event_phrase` exclusion for event-registry names and explicit story-occurrence markers such as `测试`, `考核`, and `选拔`.
- Preserved organization, location, technique, and artifact routing: `七玄门`, `七绝堂`, `彩霞山`, `长春功`, and `墨玉令` remain World items in their respective containers.
- Added a current-Flash regression fixture that asserts both the exact exclusion reason/module and surviving item placement.

## Verification

- `sidecar/.venv/bin/python -m pytest -q tests/test_w1_organizer.py` - passed (`23 passed in 0.32s`).
- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/organizer.py tests/test_w1_organizer.py` - passed.
- `git diff --check -- sidecar/supervisor/organizer.py tests/test_w1_organizer.py` - passed.
