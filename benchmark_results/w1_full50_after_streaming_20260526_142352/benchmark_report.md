# W1 Full 50-Chapter Run 3 — Benchmark Report

**Benchmark ID:** `w1_full50_after_streaming_20260526_142352`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Head commit:** `bed8ec6`  
**Key commits:** `6718ab0` (streaming write P1 fix), `5db686f` (manuscript fix)  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Date:** 2026-05-26  
**Fixture:** 凡人修仙传_前50章.txt (50 chapters, ~293K bytes)  
**Run number:** 3 of this benchmark series

---

## Executive Summary

**RESULT: FAIL — Convergence failure on character coverage (68/75)**

Third consecutive 50-chapter run. Characters extracted: 68 (target: 75, gap: 7). Run terminated before `proposal_write` — no inbox.json or manuscript.json written. Timeline: 80 canonical events, 6 branches.

**What passed:**
- No OOM (streaming fix `6718ab0` holding — no crash in any run)
- No API 402 errors (balance sufficient throughout)
- No API key in outputs

**What failed:**
- Characters: **68 extracted** (target: 75; gap: 7)
- Timeline events: **80** (target: ≥90 — also below threshold in this run)
- inbox.json not written
- manuscript.json not written

**Pattern across all three runs:** Character coverage is consistently 7-10 below the 75 threshold. The previous PASS (75 chars) was a favorable LLM draw. The same extraction code yields 65–68 characters in three consecutive full runs. R3 fix (expected character injection) is required for deterministic convergence.

---

## Run Details

| Field | Value |
|-------|-------|
| Session ID | `13d19a54-1a6d-4dcb-8aad-27a8d3659446` |
| Import run ID | `sup_562bd04835` |
| Project path | `/Volumes/migodam's-external-brain/home/narrative_ide/w1_full50_streaming_20260526_142352/` |
| Source | 凡人修仙传_前50章.txt (50 chapters, 293K bytes) |
| Start time | 14:24 UTC+8 |
| End time (error) | 16:06 UTC+8 |
| Elapsed | ~1h 42min |
| Windows total | 44 |
| Windows original | ~14 |
| Windows rerun | ~30 |
| Supervisor decisions | 47 total (28 proceed, 19 rerun) |
| Terminal status | error (deterministic convergence judgment) |

---

## Convergence Failure Analysis

### Judge Result (Iteration 0)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Judge score | 0.82 | 1.0 | FAIL |
| Characters | 68 | 75 | FAIL (−7) |
| Canonical events | 80 | ≥63 per judge gate | PASS (gate) |
| Timeline events ≥ 90 | 80 | ≥90 | FAIL (benchmark target) |
| Failed gates | `character_undercoverage` | — | — |

The judge issued one thematic rerun request: `character_undercoverage: characters=68<target=75`. After multiple additional extraction rounds (19 total reruns), the supervisor issued a `deterministic convergence judgment` and terminated with error status at 16:06 UTC+8.

### Window Explosion at End

Monitor log shows rapid window count increase in the final minutes:
- 16:05:54 — win=27
- 16:06:24 — win=36
- 16:06:54 — win=44 (status=err)

This is consistent with the supervisor issuing a burst of thematic reruns in a final attempt before convergence judgment.

### Why Character Coverage Falls Short

Three consecutive 50-chapter runs have yielded 65, 68, and 68 characters against a 75-character target. The single previous PASS (75 chars) is now clearly an outlier favorable draw. Root causes:

1. **No expected character list in extraction prompts (R3):** LLM must discover characters independently per window. Minor/peripheral characters appearing in only 1–2 chapters are frequently missed.
2. **Thematic rerun budget exhaustion:** After 3 rounds of character-focused reruns, the supervisor hits its budget ceiling. The gap of 7 characters cannot be closed via more of the same prompts.
3. **Character deduplication:** Some extracted characters may represent the same person under different names; dedup reduces the effective count further.

---

## Timeline Observation

This run extracted 80 canonical events (vs 108 in run 2, 102 in previous PASS). The lower count (and lower than the benchmark's ≥90 target) reflects LLM variance in timeline extraction — not a code regression. The same code produced 108 events in run 2.

| Run | Events | Branches |
|-----|--------|----------|
| Previous PASS | 102 | 5 |
| Run 2 (111158) | 108 | 8 |
| Run 3 (142352) | 80 | 6 |

Timeline quality is non-deterministic across runs. The ≥90 target was met in run 2 but not run 3.

---

## Memory Observation

Memory percentage is unavailable in this run's monitor log (psutil environment issue — `mem=?%` for all iterations). However:
- No OOM crash occurred
- Window count (44) and run duration (102 min) are consistent with successful streaming operation
- The P1 streaming fix (`6718ab0`) is confirmed working from runs 1 and 2 (7.5% peak vs 49% pre-fix)

---

## Extracted Metrics

| Entity Type | Count | Target | Status |
|------------|-------|--------|--------|
| Characters | 68 | 75 | FAIL (−7) |
| Canonical timeline events | 80 | ≥90 (benchmark) | FAIL |
| Timeline branches | 6 | — | — |
| Discarded duplicates | 0 | — | — |
| World items | 160 | ≥20 | PASS |

---

## Acceptance Criteria Status

| Criterion | Status | Note |
|-----------|--------|------|
| 50 chapters, no OOM | **PARTIAL** | All 50 chapters processed; run terminated before proposal_write |
| manuscript.json chapters == 50 | **FAIL** | Not written |
| system/inbox.json exists | **FAIL** | Not written |
| characters ≥ 75 | **FAIL** | 68/75 |
| 韩立/墨大夫/厉飞雨/张铁 present | **UNKNOWN** | inbox not written |
| language violations == 0 | **UNKNOWN** | inbox not written |
| 七玄门 category = organization | **UNKNOWN** | inbox not written |
| timeline canonical events ≥ 90 | **FAIL** | 80 events |
| judge score 1.0 | **FAIL** | 0.82 |
| no API key in output | **PASS** | Secret scan clean |

---

## Comparison Across All Benchmark Runs

| Run | Characters | Events | Judge | Result |
|-----|-----------|--------|-------|--------|
| w1_failure_closure 50ch (previous PASS) | 75 | 102 | 1.0 | **PASS** |
| w1_full50 100642 run 1 | 56 (partial) | 58 (partial) | 0.64 | FAIL/INVALID |
| w1_full50 111158 run 2 | 65 | 108 | 0.82 | FAIL |
| **w1_full50 142352 run 3 (this run)** | **68** | **80** | **0.82** | **FAIL** |

Three full 50-chapter runs: character counts of 65, 68, 68 — all below the 75 threshold. This is not LLM variance that more runs will solve; it is a structural issue in the extraction approach.

---

## Root Cause

R3 (from all prior `failures_and_followups.md` files): extraction prompts receive no expected character list per chapter range. The LLM must independently discover all characters in each window, and minor/peripheral characters (particularly those appearing in only 1–2 chapters, or whose names appear only in honorific/contextual form) are systematically missed.

The supervisor's thematic `character_undercoverage` rerun strategy helps but cannot close a 7-character gap once the rerun budget is consumed, because it re-runs the same prompts against the same text.

The fix requires injecting the manifest's `chapter_range_characters` field as a "must-find" hint list into extraction window prompts. This is a Codex task (P2).

---

## Secret Hygiene

Secret scan result: 0 matches for `sk-[A-Za-z0-9_-]{16,}` in this benchmark directory. API key not in any committed artifact.

---

## Recommended Next Steps

1. **Codex (P2 — R3 fix):** Inject the expected major character list per chapter range into extraction window prompts. The manifest `chapter_range_characters` field already contains this data. Feed it as a "must-find" hint list. This eliminates the non-determinism in character coverage and should raise counts to 80–90 consistently.

2. **After R3 fix:** Run 50-chapter benchmark. Verify:
   - Characters ≥75 on first judge pass (no thematic reruns needed)
   - inbox.json and manuscript.json written
   - Judge score 1.0

3. **Do not lower the threshold:** The 75-character target reflects actual content density in 凡人修仙传 chapters 1-50. 68 characters is below the correct bar; the fix should raise extraction, not lower the bar.
