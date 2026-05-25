# Failures and Follow-ups

## BLOCKER: Sidecar OOM at proposal_write

**Symptom:** Sidecar process killed by OS after ~21 minutes during `proposal_write`. `inbox.json` and `manuscript.json` never written. No crash in stderr — silent kill.

**Root cause:** State dict at `proposal_write` time holds entity_registry (70 chars + 114 events + 366 world), full timeline_architecture (318KB deserialized), review_report, and all window extractions simultaneously. Memory peaks beyond macOS limit.

**Fix:**
- Batch-write proposals from entity_registry to disk in `node_write_to_project` rather than accumulating in one state blob
- Clear entity_registry sub-dicts from state before passing to downstream nodes
- Or: write a stripped-down proposal list early and use artifact paths instead of in-memory data

---

## STILL FAILING: language_consistency

**Symptom:** `language_mismatch` gate failed at both judge iterations (iteration 1 and 2). `mixed_language_trait_sets=true` in final snapshot.

**Root cause:** `W1_EXTRACT_CHARACTERS_DEEP` and sibling prompts generate English-language trait strings (e.g. `personality_traits: ["cunning", "resourceful"]`) for Chinese characters. ToolOperatingSpec declares `language_policy: normalize_to_source` but this field is not injected into extraction prompt templates.

**Fix:**
- Add `OUTPUT_LANGUAGE={source_language}` variable to all extraction prompt templates
- Wire `source_language` from state into prompt format kwargs in `extract_window`
- Add a post-extraction normalization pass that translates Latin trait strings for zh-source imports

---

## character_undercoverage (near-miss: 70/75)

**Symptom:** 5 characters below the 75-character target after 2 judge iterations. Windows `pwin_c40f11b29ccf` and `pwin_0e96e12ceca1` each extracted 0 characters.

**Fix options:**
- Reduce `chapters_per_window_max` from 8 to 6 for `deep` profile so later chapter ranges aren't too dense
- The thematic rerun with `min_characters_per_chapter=1.5` was queued but never ran (crash) — on next run this should close the gap

---

## UNKNOWN: chapter_order

**Symptom:** Cannot verify. `manuscript.json` was not written (crash before proposal_write).

**Action:** Run a short 10-chapter import to verify chapter ordering before the next full 50-chapter benchmark.

---

## world_entity_inflation

**Symptom:** 366 world entities for 50 chapters. Likely many undeduped aliases and partial entries.

**Fix:**
- Add `max_world_entities_per_chapter` cap to ToolOperatingSpec (currently uncapped)
- Add a world entity reducer analogous to the character reducer
- Reduces memory footprint at proposal_write time (partially addresses OOM)
