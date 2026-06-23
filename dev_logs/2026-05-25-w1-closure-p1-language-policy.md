# W1 Closure P1 — Chinese Language Policy

**Date:** 2026-05-25
**Branch:** codex/w1-closure-p1-language-policy
**Author:** Claude Code

---

## Problem

The W1 benchmark run `20260525_085059` failed the `language_mismatch` judge gate at both judge iterations. `mixed_language_trait_sets=true` because all five deep extraction prompts contained only a static `## LANGUAGE RULE` section. DeepSeek V4 Pro ignored it for abstract JSON fields like `personality_traits`, outputting English values ("cunning", "resourceful") for Chinese source characters.

Two compounding bugs:
1. `source_language` from state was never injected into extraction prompt templates.
2. `minor_repair`'s Latin strip condition (`len(trait) > 6`) was stricter than `_symptom_flags`'s detection threshold (`re.search(r"[A-Za-z]{4,}")`), so short English words like "brave" (5 chars) triggered the gate flag but were not stripped.

---

## Changes Made

### `sidecar/prompts/w1_prompts.py`

Added `{source_language_label}` and `{language_policy}` template variables to all five deep extraction prompts:

- `W1_EXTRACT_CHARACTERS_DEEP`: replaced static `## LANGUAGE RULE` with parameterized `## OUTPUT LANGUAGE` block
- `W1_EXTRACT_EVENTS_DEEP`: replaced static `## LANGUAGE RULE` with parameterized `## OUTPUT LANGUAGE` block
- `W1_EXTRACT_WORLD_DEEP`: added `## OUTPUT LANGUAGE` block before Instructions; removed redundant "For Chinese source text, preserve Chinese labels" line (now covered by the parameterized block); kept the category normalization rules
- `W1_EXTRACT_RELATIONSHIPS_CHUNK`: added `## OUTPUT LANGUAGE` block before Instructions
- `W1_EXTRACT_SCENE_SUMMARIES`: added `## OUTPUT LANGUAGE` block before Instructions

Each block follows the pattern:
```
## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible string values ... MUST be written in {source_language_label}.
Fields that MUST remain in English (enum/internal keys): ...
```

### `sidecar/supervisor/tools.py` — `extract_window`

Before the `asyncio.gather` block, derived:
```python
_src_lang = state.get("source_language", "en")
_src_lang_label = "Chinese (Simplified)" if _src_lang == "zh" else "English"
_lang_policy = (state.get("tool_operating_spec") or {}).get("language_policy", "preserve_source")
```

Added `source_language_label=_src_lang_label, language_policy=_lang_policy` to all five `_invoke_json_prompt` calls.

### `sidecar/supervisor/tools.py` — `minor_repair`

Changed Latin strip condition from:
```python
if isinstance(trait, str) and re.search(r"[A-Za-z]{4,}", trait) and len(trait) > 6:
```
to:
```python
if isinstance(trait, str) and re.search(r"[A-Za-z]{4,}", trait):
```

Strip threshold now aligns exactly with `_symptom_flags` detection, eliminating false positives where short English words triggered the gate but were not cleaned.

### `sidecar/workflows/w1_import.py` — `node_process_chunks`

After `source_language = state.get("source_language", "en")` (line 4149), derived:
```python
_src_lang_label = "Chinese (Simplified)" if source_language == "zh" else "English"
_lang_policy = state.get("context", {}).get("language_policy", "preserve_source")
```

Added `source_language_label=_src_lang_label, language_policy=_lang_policy` to all five `_invoke_json_prompt` calls in the `asyncio.gather` block at ~line 4280.

### `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`

Added "Language Policy" subsection documenting the `source_language_label` + `language_policy` injection contract, including the table of enum/internal keys that must remain English.

### `dev_docs/W1_IMPORT_COMPILER.md`

Updated Character Card Requirements to note the new prompt variable injection contract for both call paths.

---

## Tests

### `tests/test_w1_supervisor_tools.py` — 3 new tests added

- `TestExtractWindowLanguageInjection.test_extract_window_passes_source_language_label_to_prompts`: verifies all 5 calls receive `source_language_label="Chinese (Simplified)"` when `source_language="zh"`
- `TestExtractWindowLanguageInjection.test_extract_window_uses_english_label_for_en_source`: verifies English label for en source
- `TestMinorRepairShortLatinStrip.test_strips_short_latin_traits_for_zh`: verifies "brave", "calm", "kind" are stripped while "勤奋" is kept
- `TestMinorRepairShortLatinStrip.test_language_gate_passes_after_minor_repair_cleans_all_traits`: end-to-end: run minor_repair, then `_symptom_flags`, assert `mixed_language_trait_sets=False`

**Result:** 29/29 passed

### `tests/test_w1_import_compiler.py` — 1 new test, 1 updated

- Updated `test_character_prompt_preserves_identity_group_and_card_contract`: added `{source_language_label}` and `{language_policy}` to `required_terms`
- New `test_all_five_deep_prompts_contain_language_policy_variables`: asserts both variables present in all five deep prompts

**Result:** 28/30 passed (2 pre-existing failures in `node_write_to_project` — `NameError: name 'proposals' is not defined` at line 3761; unrelated to this change)

---

## Fields That Intentionally Remain English

`eventClass`, `timelineClass`, `eventType`, `arcRole`, `causalRole`, `branchRole`, `forkMergeHint`, `arcId`, `category`, `importance`, `story_function`, `groupKey`, `directionality`, `status`, `topologyRole`, `container_hint`

---

## Remaining Risk for DeepSeek V4 Pro

Explicit `source_language_label` injection is a strong signal but not a guarantee. DeepSeek V4 Pro's structural priors (English JSON keys → English values) may still cause occasional English fallback for windows with sparse Chinese text. The `minor_repair` strip + `language_mismatch` thematic rerun path remains the safety net. Full architectural fix (function-calling API with typed schema) documented in `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_report.md`.
