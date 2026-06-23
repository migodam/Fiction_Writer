# W1 Wave 3 DeepSeek V4 Pro Validation

Date: 2026-05-02
Branch: `codex/w1-deepseek-v4-pro-validation`
Base: `codex/w1-import-timeline-integration`

## Validation Run

- Source project copied from `/Volumes/migodam's-external-brain/home/narrative_ide/Import_Test6`.
- Validation project: `/Volumes/migodam's-external-brain/home/narrative_ide/Import_Test6_W1V2_Validation_20260502_145524`.
- Original project was not modified.
- Source manuscript: `/Volumes/migodam's-external-brain/home/narrative_ide/novels/凡人修仙传_前50章.txt`.
- Model smoke passed for `deepseek-v4-pro` and `deepseek-v4-flash`.
- Full W1 run used `model=deepseek-v4-pro`, `prompt_profile=deep`, `import_mode=import_all`.
- Runtime: `7595.6s`.
- Final result: `50/50` chunks, `final_errors=[]`, `proposals_count=430`.

## Artifact Check

Import run id: `import_a574e4dbd71f`

- `manifest.json`: present.
- `prompt_windows.json`: present.
- `project_structure_digest.json`: present.
- `evidence_cards.json`: present.
- `reducer_artifact.json`: present.
- `timeline_architecture.json`: present.
- `review_report.json`: present.

## Before / After Diagnostics

Baseline Import_Test6, old `deepseek-v4-flash` run:

- Inbox proposals: `188`.
- Review report proposal total: `972`.
- Character summary outliers: `14`, max length `2065`.
- Canonical timeline events: `132`.
- Duplicate event clusters: `14`.
- Branches over budget: `branch_main=77`, `branch_import_conflict=32`.
- Mainline density: `77` events, share `0.5833`.

New DeepSeek V4 Pro run:

- Inbox proposals: `430`.
- Review report proposal total: `430`.
- Character summary outliers: `5`, max length `761`.
- Canonical timeline events: `51`.
- Duplicate event clusters: `0`.
- Branches over budget: `{}`.
- Branch distribution: `branch_main=24`, `branch_arc_bottle_secret=10`, `branch_arc_mentor_control=10`, `branch_arc_sect_entry=3`, `branch_arc_protagonist_origin=2`, `branch_arc_final_confrontation_prep=2`.
- Mainline density: `24` events, share `0.4706`.

## Validation Finding

Timeline topology and density goals passed, but character-card compaction was still incomplete in the long run:

- `韩立`: summary `761`, traits `58`.
- `墨大夫`: summary `590`, traits `30`.
- `厲師兄（使刀）`: summary `525`, traits `25`.

## Follow-Up Fix

Added reducer-level character-card compaction:

- Summary capped at `180` chars.
- Background capped at `160` chars.
- Role, physical description, speech style, and arc notes capped.
- Traits capped at `10`, with long sentence-like traits shortened.
- Open questions capped at `4`.
- Goals, fears, and secrets are cleared during import and reserved for later enrichment workflows.
- `node_write_to_project` also compacts before proposal write, so resumed/cached import state is guarded.

Applied to the actual generated character proposals from the validation project, this removed all proposal-level character outliers:

- Before compaction: `3` proposal outliers.
- After compaction: `0` proposal outliers.

## Verification

- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py` passed: `18 passed`.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py` passed.

## Residual Risks

- The full DeepSeek V4 Pro validation was run before the compaction patch, so the existing validation project still contains the pre-patch character proposals.
- A second full 50-chapter live run is not necessary for the reducer guardrail itself, but a short rerun or resume-based fixture can be used before main merge if we want fresh post-patch artifacts.
- Diagnostics still flags mixed-language character tag sets because the copied project contains legacy Chinese tags while the new run proposes English tags. This is not a timeline/runtime failure, but tag localization policy should be normalized in a later pass.
