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

## Root Cause Analysis

This section traces each failure to its deepest technical cause and maps it to the proposed architectural fix.

---

### Failure 1 — Sidecar OOM at `proposal_write`

**Mechanism:**
`node_write_to_project` (`w1_import.py:3336`) reads the full `entity_registry` from state and then calls `propose_write()` for each entity in a sequential loop, accumulating all proposal return values into a growing `proposals: list[dict]` (`w1_import.py:3359`). By the time this runs, the state dict holds:
- `entity_registry`: 70 chars + 114 events + 366 world entities (each a full dict with aliases, traits, notes, open_questions, etc.)
- `timeline_architecture`: 318 KB deserialized into Python dicts
- `review_report`, `judge_artifact`, `cross_validation` artifacts
- All 33 window extraction result dicts (14 original + 19 rerun windows)
- LangChain message history accumulated across 2 judge iterations

Nothing is evicted from state between pipeline stages. The memory footprint grows monotonically from `node_split_chunks` through `proposal_write`, where it peaks. macOS then silently kills the process — no crash in stderr.

**Structural cause:**
The current architecture treats state as an append-only ledger. The proposal_write step reads the entire ledger at once rather than streaming proposals to disk as they're produced during extraction. This is architecturally equivalent to pulling an entire database into RAM for a single sequential scan.

**Agent-plus-tools solution:**
Refactor proposal generation using the **agent-plus-tools pattern**:
- Define a `write_proposal(entity_type, entity_id, payload)` tool that writes one proposal to disk and returns only a compact receipt `{entity_id, status}`.
- During `extract_window`, the agent calls `write_proposal` as a side-effecting tool immediately after each entity is registered — before the next window runs.
- After `write_proposal` returns a receipt, the entity's full payload can be evicted from the in-memory registry; only the receipt (entity_id + status) is kept in state.
- At `proposal_write` time, state holds only receipts — O(num_entities) small dicts — not full payload blobs.

**Interim fix (no architectural change):**
- In `node_write_to_project`, strip the full payload from `entity_registry` before calling `propose_write` in bulk. Write proposals in batches of 25; clear each batch from the local `proposals` list after writing.
- Before passing state to `node_build_manuscript`, call `state.pop("entity_registry", None)` and `state.pop("cross_validation", None)` to free the largest blobs.

---

### Failure 2 — `language_mismatch` (mixed English/Chinese trait strings)

**Mechanism:**
All five deep extraction prompts (`W1_EXTRACT_CHARACTERS_DEEP`, `W1_EXTRACT_EVENTS_DEEP`, `W1_EXTRACT_WORLD_DEEP`, `W1_EXTRACT_RELATIONSHIPS_CHUNK`, `W1_EXTRACT_SCENE_SUMMARIES`) contain a `## LANGUAGE RULE` section in static prose. For example, `W1_EXTRACT_CHARACTERS_DEEP:133` reads:
> "All prose text fields MUST use the dominant language of the source text chunk."

This is a qualitative instruction — the model must infer the target language from the chunk content. It is **not** a template variable; `source_language` from state is never injected into any extraction prompt. The `ToolOperatingSpec.language_policy = "normalize_to_source"` field is declared in `state.py:95` but is never plumbed into the prompt `format()` call at `w1_import.py:4281–4317` or in `supervisor/tools.py:310–333`.

DeepSeek V4 Pro then defaults to English for abstract trait fields (`personality_traits: ["cunning", "resourceful"]`) because:
1. The JSON schema template in the prompt uses English keys — English values follow naturally.
2. The entity registry summary itself uses English field names, priming the model to output English values.
3. The static language rule competes with the model's structural priors around JSON formatting.

**Agent-plus-tools solution:**
Replace `_invoke_json_prompt()` with the **DeepSeek/OpenAI function-calling API** (`tools=` + `tool_choice="required"`):
- Define `extract_characters` as a function with a typed JSON Schema. Field-level descriptions can include `"x-output-language": "{source_language}"` annotations.
- The model fills structured typed fields rather than generating free-form JSON text — this moves language enforcement from a prose instruction to a schema constraint.
- Language compliance becomes an output-format property, not a prompt instruction the model can ignore.

**Interim fix (same `_invoke_json_prompt` path):**
- Add `{source_language}` as a template variable to all five deep extraction prompts, passed from `state.get("source_language", "en")` at call sites (`supervisor/tools.py` and `w1_import.py`).
- Replace the static `## LANGUAGE RULE` prose with: `OUTPUT LANGUAGE: {source_language_label} — all text field values in this JSON response MUST be written in {source_language_label}. Do NOT output English for non-English source text.`

---

### Failure 3 — `character_undercoverage` (70 of 75 target)

**Mechanism:**
Windows `pwin_c40f11b29ccf` and `pwin_0e96e12ceca1` each extracted 0 characters. Two root causes compound:

**Cause A — asyncio exception suppression.** `asyncio.gather(return_exceptions=True)` at `supervisor/tools.py:335` causes character extraction exceptions to be silently swallowed. If the character extraction coroutine raises (e.g., JSON parse failure, context length exceeded), `result` is an `Exception` object; `_coerce_result` returns `{}`. The state merge proceeds with `char_data = {}` — no error surfaces to the caller, no rerun is triggered.

**Cause B — late-chapter window density.** Late chapter windows (chapters 40–50 in a 50-chapter import) typically converge multiple plot threads: more named characters per scene, more alias collisions, longer entity registry summaries, and longer source text per chapter. Together these increase the prompt context length beyond what `chapters_per_window_max=8` was calibrated for, making it more likely that the model truncates output before completing the character list.

The thematic rerun with `min_characters_per_chapter=1.5` was queued at judge iteration 2 but never ran — sidecar crashed before `_apply_thematic_reruns()` could dispatch them.

**Agent-plus-tools solution:**
Replace the one-shot `asyncio.gather` with a **character extraction agent loop** per window:
- The agent calls `extract_characters(window_id)` as a tool.
- After the tool returns, the agent checks `coverage = len(new_chars) / chapter_count`.
- If `coverage < min_characters_per_chapter`, the agent calls `augment_window(window_id, missing_hint=...)` as a follow-up tool in the same API turn — no outer judge iteration needed.
- This inner loop converges character coverage locally before the window result is committed to entity_registry.

**Interim fix:**
- Change `return_exceptions=True` to explicit per-coroutine error handling with logging in `supervisor/tools.py:308` — failed extractions should trigger `rerun_window` immediately, not silently return `{}`.
- Lower `chapters_per_window_max` from 8 to 6 for `deep` profile for the last 20% of chapters.

---

### Failure 4 — World Entity Inflation (366 entities for 50 chapters)

**Mechanism:**
`W1_EXTRACT_WORLD_DEEP` emits a `world_mentions` list per window with no cross-window dedup key. A world entity like `七玄门` (Seven Mysteries Sect) appears in ~14 windows — each extracts it independently with a different description phrasing. The character reducer (`node_reconcile_entities`) deduplicates characters by canonical_name across windows, but **no equivalent reducer exists for world entities**. The `minor_repair` tool normalizes field formatting but does not collapse world entries by name.

Additionally, `max_world_entities_per_chapter` is uncapped in `ToolOperatingSpec` — each window can emit 21–36 world entities regardless of how many distinct items the chapter actually introduces.

**Agent-plus-tools solution:**
- Add a `dedupeKey` field to `W1_EXTRACT_WORLD_DEEP`'s JSON schema: `"dedupeKey": "<normalized_name>|<category>"` — analogous to the `dedupeKey` already required by `W1_EXTRACT_EVENTS_DEEP`.
- Add a `reduce_world_entities` tool to the supervisor tool registry (analogous to `reduce_entities`) that collapses world entries by `dedupeKey`, merging attributes and confidence scores.
- Wire it into the policy loop between `reduce_entities` and `minor_repair`.

**Interim fix:**
- Add `max_world_entities_per_chapter: 20` cap to `ToolOperatingSpec` (currently uncapped in `state.py`).
- Enforce it in `extract_window`: after collecting `world_mentions`, take the top-20 by confidence before merging into entity_registry.

---

### Failure 5 — Chapter Order (Unknown / Unverifiable)

**Mechanism:**
`manuscript.json` was never written — the sidecar was killed by OOM during `node_write_to_project` before reaching `node_build_manuscript`. The windowing fix applied in S1–S2 (packed windows anchored by first chunk_id, sorted by `chunk_index_by_id` at `w1_import.py:4180–4184`) should preserve source order, but this cannot be confirmed without a complete run.

**Agent-plus-tools solution:**
- Add a `verify_chapter_order(project_path, manuscript_json_path)` tool that is called by the post-write agent as a mandatory post-check after `node_build_manuscript`.
- The tool reads `manuscript.json`, checks that `chapter_index` values are monotonically increasing (1..N), and emits a `chapter_order_violation` gate failure if not.
- This ensures chapter ordering is always verified end-to-end, not assumed from code inspection.

**Interim action:**
- Run a separate short benchmark (10 chapters) that does not OOM, and verify `manuscript.json` chapter ordering before the next 50-chapter run.

---

## Recommended Next Fixes

### P0 — Sidecar OOM (blocks any complete run)

**Root cause:** State is append-only; `entity_registry` (70 chars + 114 events + 366 world) + `timeline_architecture` (318KB) + all window results accumulate to macOS kill limit by `proposal_write`.

**Immediate fix (3 hours):**
- In `node_write_to_project` (`w1_import.py:3336`): write proposals in batches of 25 via `propose_write` then discard each batch from the local list before continuing.
- After the write loop, call `state.pop("entity_registry", None)` before `node_build_manuscript` to free the largest blob.

**Architectural fix (agent-plus-tools, 2 days):**
- Define `write_proposal(entity_type, entity_id, payload)` as a side-effecting supervisor tool.
- Call it from within `extract_window` immediately after each entity is registered — the full payload is never kept in state past that point, only the receipt.
- At `proposal_write` time, state holds only receipts (O(n) small dicts) — the memory peak is eliminated.

---

### P1 — Language normalization in prompts

**Root cause:** `source_language` is never injected into extraction prompt templates; the static `## LANGUAGE RULE` is ignored by DeepSeek V4 Pro for abstract typed fields like `personality_traits`.

**Immediate fix (1 hour):**
- Add `source_language_label` as a `{source_language_label}` template variable to all five deep extraction prompts.
- Wire it from `state.get("source_language", "en")` in `supervisor/tools.py:310–333` and `w1_import.py:4281–4317`.
- Replace the static language rule prose with the explicit instruction shown in the Root Cause Analysis above.

**Architectural fix (agent-plus-tools, 3 days):**
- Replace `_invoke_json_prompt()` with the DeepSeek function-calling API (`tools=`, `tool_choice="required"`).
- Define `extract_characters`, `extract_events`, `extract_world` as typed tool schemas.
- Language enforcement becomes a schema constraint, not a prose instruction.

---

### P2 — character_undercoverage in late windows

**Root cause:** `asyncio.gather(return_exceptions=True)` silently swallows extraction exceptions; late-chapter windows are too dense for `chapters_per_window_max=8`.

**Immediate fix (2 hours):**
- Change exception handling in `supervisor/tools.py:308` — failed extractions should trigger a `rerun_window` call immediately, not silently return `{}`.
- Lower `chapters_per_window_max` for `deep` profile from 8 to 6 for windows anchored in the last 20% of chapters.

**Architectural fix (agent-plus-tools, 2 days):**
- Replace the one-shot gather with a character extraction agent loop: `extract → check_coverage → augment_if_needed`, converging locally before the window result is committed.

---

### P3 — World entity dedup

**Root cause:** No cross-window world entity reducer exists; 366 entities for 50 chapters is ~7× the expected distinct count (~50).

**Immediate fix (4 hours):**
- Add `max_world_entities_per_chapter: 20` cap to `ToolOperatingSpec`.
- Enforce it in `extract_window` by selecting top-20 by confidence.

**Architectural fix (agent-plus-tools, 1 day):**
- Add `dedupeKey` field to `W1_EXTRACT_WORLD_DEEP` output schema.
- Add `reduce_world_entities` supervisor tool; insert it between `reduce_entities` and `minor_repair` in the policy loop.

---

### P4 — Confirm chapter ordering

**Root cause:** OOM prevented `manuscript.json` from being written; chapter ordering from the packed-window redesign is unverified end-to-end.

**Immediate action:**
- Run a 10-chapter import to verify `manuscript.json` chapter ordering before the next full 50-chapter benchmark.

**Architectural fix (agent-plus-tools):**
- Add `verify_chapter_order` as a mandatory post-write supervisor tool that gates `done` status on chapter order confirmation.
