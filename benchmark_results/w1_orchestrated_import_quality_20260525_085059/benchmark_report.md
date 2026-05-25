# W1 Orchestrated Import Quality V2 — Benchmark Report

**Overall Status:** WARNING (partial run — sidecar OOM before proposal_write)
**Run Timestamp:** 20260525_085059
**Branch:** codex/w1-orchestrated-import-quality
**Duration:** ~21 min (extraction + reduce + architect + qa_review + 2 judge iterations; crashed at proposal_write)

---

## Executive Summary

The orchestrated import (`use_supervisor=true`, `use_orchestrator=true`, `prompt_profile=deep`) ran two full judge iterations against the first-50-chapter Chinese novel fixture. Extraction, reduction, timeline architecture, QA review, and two rounds of judge evaluation all completed successfully. The sidecar process was killed by the OS (OOM) during `proposal_write`, so `inbox.json` and `manuscript.json` were never written — proposals exist in memory but could not be committed.

**Three of the five previous failure symptoms are confirmed FIXED. One (language consistency) still fails. One (chapter order) cannot be verified due to crash.**

Two root-cause bugs were discovered and fixed during this benchmark session:
1. `_write_import_artifact` — only created import run dir, not subdirectories like `windows/` → all 14 window extractions failed silently in the previous run
2. `extract_window` — read `window.get("text", "")` (always empty) instead of assembling text from `state["chunks"]` via `chunk_ids`

These fixes are committed to `codex/w1-orchestrated-import-quality`.

---

## Run Configuration

| Field | Value |
|-------|-------|
| Source file | `凡人修仙传_前50章.txt` (first 50 chapters) |
| Import mode | `import_all` |
| Prompt profile | `deep` |
| Model | `deepseek-chat` (DeepSeek V4 Pro) |
| use_supervisor | true |
| use_orchestrator | true |
| Judge pass threshold | 0.85 |
| Rerun budget | 2 |
| Branch | codex/w1-orchestrated-import-quality |
| Import run ID | `sup_2d42990ac3` |

---

## Artifact Paths

| Artifact | Status | Size |
|----------|--------|------|
| `manifest.json` | written | 27,247 B |
| `prompt_windows.json` | written | 9,330 B |
| `tool_operating_spec.json` | written | 423 B |
| `judge_artifact.json` | written | 16,712 B |
| `timeline_architecture.json` | written | 318,451 B |
| `review_report.json` | written | 4,199 B |
| `supervisor_decisions.json` | **MISSING** — not yet written when crash occurred |
| `window_metrics.json` | **MISSING** — not yet written when crash occurred |
| `cross_validation.json` | **MISSING** — not yet written when crash occurred |
| `inbox.json` | **MISSING** — proposal_write crashed |
| `manuscript.json` | **MISSING** — proposal_write crashed |

---

## Metrics Table

| Metric | Value |
|--------|-------|
| Duration | ~21 min (partial) |
| Characters extracted | **70** |
| Canonical timeline events | **114** |
| Timeline branches | **4** (main, antagonist, training, faction) |
| Main branch events | **~47** |
| Side branch events | ~67 |
| Discarded duplicates | 11 |
| World entities | **366** |
| Missing groupKey count | 0 |
| Org chars in registry | 0 |
| Mixed language traits | **YES** (language_mismatch gate) |
| Judge score | **0.64** (threshold: 0.85) |
| Judge passed | **false** |
| Judge iterations | 2 |
| Thematic reruns requested | character_undercoverage, language_mismatch |

---

## Previous Failure Comparison

| Symptom | Previous | Current | Status |
|---------|----------|---------|--------|
| Character count | 4 | 70 | **[FIXED]** |
| Timeline density (main branch) | 3 events | ~47 main branch events | **[FIXED]** |
| Chapter order | Out of order | Unknown (crash before write) | **[UNKNOWN]** |
| Language consistency | Mixed Eng/Zh | language_mismatch gate failed at iteration 2 | **[STILL FAILING]** |
| World routing (≥3 branches) | 1 collapsed | 4 semantic branches | **[FIXED]** |

---

## Judge Artifact Summary

- **Score:** 0.64 / 1.0 (pass threshold: 0.85)
- **Passed:** false
- **Failed gates:**
  - `character_undercoverage` — 70 chars < target 75 (5 chars short after 2 rerun iterations)
  - `language_mismatch` — source_language=zh but mixed-language trait fields detected
- **Thematic rerun requests (iteration 2):**
  - `character_undercoverage` targeting windows `pwin_c40f11b29ccf`, `pwin_f4fbee39d96c`, `pwin_0e96e12ceca1` with `min_characters_per_chapter=1.5`
  - `language_mismatch` targeting windows `pwin_839f45621a38`, `pwin_96a902fd924a`, `pwin_f4fbee39d96c` with `language_policy=normalize_to_source`
- **Converge status:** failed (sidecar crashed before reruns could execute)
- **Note:** Both gates were within 1 iteration of passing — 70/75 chars (93%) and language reruns had just been dispatched

---

## Timeline Quality Analysis

- **4 semantic branches** extracted: `branch_import_main`, `branch_theme_antagonist`, `branch_theme_training`, `branch_theme_faction`
- **114 canonical events** total; ~47 on main branch
- **11 discarded duplicates** (semantic dedup working correctly — see duplicate merge log in review_report)
- **Timeline architect ran successfully** — 318KB artifact with full branch/event topology
- Main branch density policy warning: "84 canonical events → converted lower-importance events to scene beats" (first pass); "47 canonical events" after architect pass
- `timeline_mainline_overdense` flag: **true** — density pruning is aggressive; some arc-level events may be demoted
- No missing `branchId` / `parentBranchId` fields observed in branch list

---

## Character Extraction Analysis

- **70 characters extracted** (target: 75; 5 short after 2 rerun iterations)
- Key character presence (from cross-validation `missing_majors` field — not directly from inbox since it wasn't written):
  - 韩立 (protagonist): **likely present** — flagged missing in 1 window, `missing_major_characters_count=0` in final judge snapshot
  - 墨大夫: **likely present** — flagged missing in 1 window (`pwin_96a902fd924a`) but judge sees 0 missing majors overall
  - 厉飞雨: **likely present** — not flagged missing in any window
  - 张铁: **likely present** — flagged missing in 2 windows but present globally (missing_major_characters_count=0)
- `org_chars_in_registry: 0` — no organizations mis-routed into the character registry
- `missing_groupkey_count: 0` — all characters have valid groupKey assignments
- 33 window extraction files written (14 original + ~19 rerun windows across 2 judge iterations)

---

## World Ontology Analysis

- **366 world entities** extracted (target minimum: 20 — far exceeded)
- `world_category_policy: full_attributes` enabled in tool_operating_spec
- Containers and items by category: **unknown** — inbox.json not written
- 七玄门 category: **unknown** — inbox.json not written
- Per-window world extraction was strong: individual windows yielded 21–36 world entities each
- Risk: 366 entities is very high for 50 chapters; dedup/reducer may have under-collapsed world entities

---

## Chapter/Manuscript Preservation Analysis

- **Unknown** — `manuscript.json` was not written (sidecar crashed before `proposal_write`)
- Chapter ordering cannot be verified
- Source text preservation cannot be verified
- This is the primary unresolved question for a follow-up run

---

## Language Consistency

- **Source language:** Chinese (zh)
- **Mixed-language trait sets detected:** YES
- `language_mismatch` gate failed at both judge iterations despite `language_policy: normalize_to_source` being set in tool_operating_spec
- Root cause: the extraction prompts generate some English-language personality trait strings for Chinese characters; the language_policy field in ToolOperatingSpec is declared but the prompts don't use it as an explicit output constraint
- The thematic rerun requested `language_policy=normalize_to_source` as a parameter override, but those reruns never executed (sidecar crashed before they ran)

---

## Residual Risks

1. **Sidecar OOM at proposal_write** — the single biggest blocker. With 70 chars + 114 events + 366 world entities all in one state dict at proposal_write time, memory peaks. Fix options:
   - Stream proposals to disk in batches instead of accumulating in state
   - Reduce world entity count via stronger dedup (366 is inflated)
   - Increase sidecar memory limit or run on a machine with more RAM

2. **character_undercoverage (70 < 75)** — 5 characters short. Window-level gaps (`pwin_c40f11b29ccf`, `pwin_f4fbee39d96c`, `pwin_0e96e12ceca1` each extracted 0–1 chars). Thematic reruns were queued but didn't execute.

3. **language_mismatch** — prompts generate English trait strings despite Chinese source. The `language_policy` field in ToolOperatingSpec has no corresponding prompt instruction. The extraction prompts need an explicit "output must be in {source_language}" constraint injected.

4. **World entity inflation** — 366 entities for 50 chapters is likely over-extracted. Stronger world dedup or a `max_world_entities_per_chapter` cap in the ToolOperatingSpec would help.

5. **Chapter order unknown** — manuscript.json was never written; chapter ordering fix from the windowing redesign (W1 packed windows S1–S3) cannot be confirmed verified end-to-end.

---

## Recommended Next Fixes

### P0 — Sidecar OOM (blocks any complete run)
- `node_write_to_project` / `proposal_write`: batch-write proposals to disk rather than accumulating in state; clear entity_registry from state before writing
- Alternatively: write a stripped version of state to proposal_write (only proposals, not full entity_registry + timeline_architecture simultaneously)

### P1 — Language normalization in prompts
- `W1_EXTRACT_CHARACTERS_DEEP` and related prompts: add explicit `OUTPUT LANGUAGE: {source_language}` instruction
- Wire `source_language` from state into the prompt template (currently prompts hardcode no language constraint)

### P2 — character_undercoverage in late windows
- Windows `pwin_c40f11b29ccf` and `pwin_0e96e12ceca1` extracted 0 characters each
- Check if these chapter ranges are less character-dense or if prompt context window is too full
- Consider lowering `chapters_per_window_max` for the last few windows

### P3 — World entity dedup
- 366 entities likely includes many duplicates (different spellings, aliases, partial names)
- Add a world entity dedup step analogous to the character reducer
- Or add `max_world_entities_per_chapter` cap in ToolOperatingSpec (currently uncapped)

### P4 — Confirm chapter ordering
- Run a separate test importing 10 chapters to verify chapter ordering before another 50-chapter run
- The windowing fix (S1–S2 packed windows) should preserve order but needs end-to-end verification with manuscript.json written
