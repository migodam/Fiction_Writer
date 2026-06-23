# W1 Backend Import Quality — Delivery Report

**Branch:** `codex/w1-orchestrated-import-quality`  
**Date:** 2026-06-07  
**Status:** COMPLETE — all 6 tasks shipped, 291/291 tests passing, UI build clean

---

## Commits Shipped

| Commit | Change |
|---|---|
| `0cd2ac0` | fix: add language policy to W1_CLASSIFY_CHARACTER_TAGS for zh imports |
| `02db87c` | test: assert language_policy kwarg in tag classification test |
| `4ae2284` | fix: normalize zh relationship types via _ZH_CATEGORY_LABELS |
| `71edac8` | fix: wire organizer into supervisor pipeline with artifact output |
| `b47bba4` | fix: correct organizer step ordering in _policy_with_progress |
| `1de6ebb` | fix: strip English-dominant tag names in minor_repair for zh imports |
| `12042ea` | fix: add W3 PPP knobs to build_planner_proposal_prompt_context |
| `03862ab` | test: add windowing integrity tests and source_span to nodes.json |

---

## Task Summary

### Task A — Tag Language Policy ✅
**Files**: `sidecar/prompts/w1_prompts.py`, `sidecar/workflows/w1_import.py`

Added the standard `[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}` header to `W1_CLASSIFY_CHARACTER_TAGS` prompt, and injected `source_language_label` + `language_policy` (read from `state.get("context", {}).get("language_policy", "preserve_source")`) into the `node_classify_character_tags` call site. Now consistent with all other extraction prompts.

**Tests added**: `TestTagClassificationLanguagePolicy` — 2 tests in `test_w1_supervisor_tools.py`

---

### Task B — Relationship Type Normalization ✅
**Files**: `sidecar/workflows/w1_import.py`, `sidecar/prompts/w1_prompts.py`

Added `_ZH_CATEGORY_LABELS` dict (8 English category keys → canonical Chinese display labels) and `_normalize_relationship_type(raw_type, category, source_language) -> (display_type, source_label)` function. Applied in both `node_synthesize_relationships` main loop and `_fallback_relationships` closure. Raw LLM type (`解惑`, `选拔`, etc.) is preserved as `sourceLabel` field for transparency. Language policy now injected into `W1_SYNTHESIZE_RELATIONSHIPS` call.

**Result**: `解惑` + `category=mentor_disciple` → `type="师徒关系"`, `sourceLabel="解惑"`

**Tests added**: `TestRelationshipTypeNormalization` — 3 tests in `test_w1_supervisor_tools.py`

---

### Task C — Organizer in Supervisor Pipeline ✅
**File**: `sidecar/supervisor/policy.py`

Inserted organizer step (3c) in both `run_supervisor_policy` and `_policy_with_progress` (streaming path) between `reduce_world_entities` (3b) and `minor_repair` (4). The organizer filters out person names, module labels, and identity ranks from `entity_registry["world_detailed"]`. Writes `organizer_output.json` artifact when `project_path` + `import_run_id` are available.

**Review fix**: Spec review caught that `_policy_with_progress` originally had organizer running AFTER `minor_repair` and was missing the `reduce_world_entities` step — both corrected in fixup commit `b47bba4`.

**Legacy LangGraph path**: Already wired at `w1_import.py:5916` — no change needed.

**Tests added** (4 total):
- `TestOrganizerInSupervisorPipeline` in `test_w1_supervisor_policy.py` (3 tests: call-order, person-name exclusion, artifact written)
- `test_legacy_langgraph_includes_organize_world_items_node` in `test_w1_organizer.py`

---

### Task D — Tag Repair in minor_repair ✅
**File**: `sidecar/supervisor/tools.py`

Added tag name language validation block after existing Latin personality trait stripping. For `source_language == "zh"`: any `character_tags[].name` matching `r"[A-Za-z]{3,}"` is blanked to `""`. Count logged to `repair_log`. Serves as a safety net even after Task A prompt fix.

**Tests added**: `TestMinorRepairTagNameStrip` — 3 tests in `test_w1_supervisor_tools.py`

---

### Task E — Planner Context Builder Update ✅
**File**: `sidecar/supervisor/planner_llm.py`

Added 7 missing keys to `allowed_prompt_policy_patch_keys` in `build_planner_proposal_prompt_context`, bringing it into sync with `_PPP_ALLOWED_FIELDS` in `planner.py`. The 3 W3 knobs now exposed: `"reviewer_mode"`, `"rerun_scope"`, `"organizer_strictness"`. (Also added 4 other previously-missing knobs discovered during this check.)

**Tests added**: `test_planner_context_includes_organizer_strictness` in `test_w1_planner_proposal.py`

---

### Task F — Windowing Integrity Tests + source_span in nodes.json ✅
**Files**: `sidecar/workflows/w1_import.py`, `tests/test_w1_prompt_windows.py`, `tests/test_w1_import_compiler.py`

Added `"source_span": mc.get("source_span")` to the chapter_outline node dict written by `_write_manuscript_nodes`. Added 5 new tests:

| Test | What It Proves |
|---|---|
| `test_source_block_text_matches_manuscript_content` | `source_block["text"] == chunk["manuscript_content"]` exactly |
| `test_normal_chapters_never_get_oversized_split` | Small chapters never get `single_oversized_chapter_paragraph_split` |
| `test_oversized_chapter_split_has_explicit_metadata` | Oversized splits carry `split_index`/`total_splits` metadata |
| `test_supervisor_path_content_chain_integrity` | Chapter + scene proposal content == original manuscript_content |
| `test_manuscript_nodes_json_includes_source_span` | `nodes.json` entries carry `source_span.start` and `source_span.end` |

---

## Acceptance Criteria Verification

### Compile Check
```
python3 -m py_compile sidecar/workflows/w1_import.py \
  sidecar/supervisor/policy.py sidecar/supervisor/tools.py \
  sidecar/supervisor/planner_llm.py sidecar/prompts/w1_prompts.py
→ COMPILE OK
```

### Full Regression
```
291 passed in 2.98s
(tests/test_w1_supervisor_tools.py + test_w1_supervisor_policy.py +
 test_w1_organizer.py + test_w1_reviewers_quality.py +
 test_w1_import_compiler.py + test_w1_prompt_windows.py +
 test_w1_planner_proposal.py)
```

### Targeted New Tests
```
17 passed (all new tests by keyword filter)
```

### UI Build
```
✓ built in 2.69s — no frontend regressions
```

---

## What Was NOT Changed (Forbidden Writes)

- `sidecar/models/state.py` — untouched
- `src/ui-react/**` — untouched
- `dev_docs/` — untouched (no contract changes that invalidate docs)
- No live API/model calls

---

## Deferred (Requires Separate Lead Approval)

- **Task G (background_entries schema)**: Lead must confirm storing `background_entries` in freeform character dict is acceptable and that `W1_EXTRACT_CHARACTERS_DEEP` prompt change is in scope. Not blocked — can start immediately upon Lead approval.
- **Live 10-chapter provider import**: Requires explicit user approval before execution.
- **Full relationship UI grouping by category**: W2 scope.
- **`organizer_strictness` as planner-triggerable knob**: Requires W0 Lead approval.
