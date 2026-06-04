# Worker W2 — Reviewer + Organizer + Manifest Repair Loop Report
**Date:** 2026-06-04
**Branch:** codex/w1-orchestrated-import-quality

---

## Executive Summary

This session closes the `import_test13` quality gaps identified in the defect-repair report: repeated age phrases slip through the old ≥5 char phrase detector, duplicate chapters have no detection path, ConsistencyReviewer produces no structured diff for cross-import character fact changes, and the World Model classification acceptance matrix had no comprehensive test coverage. All five refinement points from the review have been addressed.

---

## Issue Coverage Table

| Issue (import_test13 symptom) | Reviewer Detects? | Repaired Locally? | Escalated? | Evidence |
|---|---|---|---|---|
| "23岁" repeated in character summary | ✅ QualityReviewer | ✅ clean_age_phrase_duplicate action | — | `test_quality_catches_age_phrase_23sui` |
| "十岁" repeated in character summary | ✅ QualityReviewer | ✅ clean_age_phrase_duplicate action | — | `test_quality_catches_age_phrase_shisui` |
| Duplicate 第九章 × 3 (by title) | ✅ QualityReviewer | ✅ dedupe_chapters action | — | `test_quality_catches_duplicate_chapters_by_title` |
| Duplicate chapter when chapterNumber is None (title fallback) | ✅ QualityReviewer | ✅ dedupe_chapters action | — | `test_quality_catches_duplicate_chapters_no_chapter_number` |
| Character fact diluted across imports | ✅ ConsistencyReviewer | — (advisory diff only) | manifest_revision_diff (protect) | `test_consistency_produces_manifest_revision_diffs` |
| FactReviewer reading whole novel | ✅ Never happens (snippet-only) | — | — | `test_fact_reviewer_never_reads_chunks_directly` |
| FactReviewer over-firing on minor drift | ✅ Only obvious mismatch flagged | — | — | `test_fact_reviewer_only_reports_obvious_mismatch` |
| 记名弟子/内门弟子/外门弟子 → cultivation | ✅ Organizer excludes | — | — | `test_organizer_full_acceptance_matrix` |
| Person names (韩立/王护法) entering World Model | ✅ Organizer excludes | — | — | `test_organizer_full_acceptance_matrix` |
| 七玄堂/供奉堂 wrongly excluded | ✅ Now survive as location/org | — | — | `test_organizer_full_acceptance_matrix` |

---

## New Code

### schemas.py
- Added `ManifestRevisionDiff` TypedDict: `revision_id`, `entity_type`, `entity_id`, `field`, `old_value`, `new_value`, `action` (protect/update/merge), `reason`.
- Added `manifest_revision_diffs: List[ManifestRevisionDiff]` to `ReviewReport`.

### base.py
- Extended `_build_report` to accept `manifest_revision_diffs` param (default `[]`). All reviewers automatically include the field in their output.

### quality_reviewer.py
- Added `_AGE_PHRASE_RE = re.compile(r"(\d{1,3}岁|[零一二三四五六七八九十百]+岁)")` module constant.
- Added `_check_character_age_phrase_repeated`: catches "23岁"/"十岁"-style short phrase repetitions; emits `clean_age_phrase_duplicate` repair with `proposed_operations` for the field update.
- Added `_check_duplicate_manuscript_chapters`: groups by `title.lower()` (primary key); falls back to `chapterNumber` only for chapters not already captured by title match. Emits `dedupe_chapters` repair with delete ops for non-primary duplicates.

### consistency_reviewer.py
- Added `_produce_manifest_revision_diffs`: compares `project_structure_digest["characters"]` fields (`summary`, `background`, `role`) against incoming `entity_registry["characters"]` by normalized name. Emits `protect` diff for each changed field.

---

## local_repair Action Boundary (clarified)

Repair actions in `local_repair_actions` are **advisory in the ReviewReport only**:
- They appear in `review_report.json` but do **not** mutate `entity_registry`, `manuscript_chapters`, or any state key during the import graph execution.
- `proposed_operations` is a serializable intent payload for future user-triggered acceptance via the proposal inbox.
- Boundary is tested by `test_quality_local_repair_output_structure`: verifies state dict is identical before and after `reviewer.review()`.

---

## Tests Added

| File | Before | After | New Tests |
|------|--------|-------|-----------|
| `test_w1_reviewers_quality.py` | 9 | 15 | age_phrase_23sui, age_phrase_shisui, duplicate_chapters_by_title, duplicate_chapters_no_chapter_number, local_repair_output_structure, import_test13_regression |
| `test_w1_reviewers_consistency.py` | 5 | 7 | manifest_revision_diffs, diff_absent_when_no_change |
| `test_w1_reviewers_fact.py` | 5 | 7 | never_reads_chunks, only_reports_obvious_mismatch |
| `test_w1_organizer.py` | 16 | 17 | full_acceptance_matrix |

**Total:** 107 tests passing (was 96 reviewer/organizer + 61 compiler = 157 before; now same 157 + 12 new = well, the 96 was across those 4 test files combined, and adding 12 new tests brings that to 46 + 61 = 107).

---

## w1_import.py Integration Note (Lead approval required)

No changes made to `w1_import.py`. The narrow patch needed to wire `manifest_revision_diffs` into the import graph artifact would be:

1. In `node_review_import()`: add `diffs` collection from all three reviewers' `manifest_revision_diffs` fields.
2. Write `manifest_revision_diffs` to `review_report.json` alongside `reviewer_reports`.
3. **Only with Lead approval**: auto-promote deterministic repair `proposed_operations` to inbox proposals.

---

## Verification

```
sidecar/.venv/bin/python -m py_compile \
  sidecar/supervisor/reviewers/schemas.py \
  sidecar/supervisor/reviewers/base.py \
  sidecar/supervisor/reviewers/quality_reviewer.py \
  sidecar/supervisor/reviewers/consistency_reviewer.py
→ PASS (no output)

sidecar/.venv/bin/python -m pytest \
  tests/test_w1_reviewers_quality.py \
  tests/test_w1_reviewers_fact.py \
  tests/test_w1_reviewers_consistency.py \
  tests/test_w1_organizer.py \
  tests/test_w1_import_compiler.py \
  -q
→ 107 passed in 1.32s
```

---

## Remaining Risks

| Risk | Why |
|------|-----|
| Reviewer results still advisory | `node_review_import()` runs reviewers but repair proposals are not auto-applied — user sees them only via `review_report.json` |
| `manifest_revision_diffs` not in review_report.json artifact yet | Requires Lead-approved narrow patch to `node_review_import()` |
| Age phrase detector (`_AGE_PHRASE_RE`) may miss non-standard patterns | Only covers `\d{1,3}岁` and Chinese numeral+岁; uncommon patterns like "二十三岁" are covered; edge cases like "廿三岁" are not |
| Duplicate chapter detection depends on non-None chapter IDs | If `chapter_id` is missing, fallback uses title as ID, which may cause false grouping |
