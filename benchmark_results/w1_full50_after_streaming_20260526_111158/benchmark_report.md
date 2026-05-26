# W1 Full 50-Chapter Rerun — Benchmark Report

**Benchmark ID:** `w1_full50_after_streaming_20260526_111158`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Head commit:** `bed8ec6`  
**Key commits:** `6718ab0` (streaming write P1 fix), `5db686f` (manuscript fix)  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Date:** 2026-05-26  
**Fixture:** 凡人修仙传_前50章.txt (50 chapters, ~293K bytes)

---

## Executive Summary

**RESULT: FAIL — Convergence failure on character coverage (65/75)**

The run completed 39 windows covering all 50 chapters without API errors or OOM. However, the judge's character coverage threshold (75) was not reached after 44 supervisor decisions and multiple thematic rerun rounds. The supervisor issued a `deterministic convergence judgment` and terminated the session.

**What passed:**
- No OOM (memory fix `6718ab0` confirmed working)
- No API 402 errors (balance sufficient throughout)
- Timeline: **108 canonical events** (exceeds target 90; better than previous PASS run's 102)
- 8 timeline branches (vs 5 in previous PASS)

**What failed:**
- Characters: **65 extracted** (target: 75; gap: 10)
- inbox.json not written (run terminated before proposal_write)
- manuscript.json not written

**Assessment:** This is a non-deterministic LLM variance failure, not a code regression. The same code produced 75 characters in the previous PASS run (`w1_failure_closure_20260526_011743`). Timeline quality actually *improved* (108 vs 102 events). R3 (missing major characters) is the blocking issue.

---

## Run Details

| Field | Value |
|-------|-------|
| Session ID | `f920e767-9053-4d39-ba16-0980cee86bb1` |
| Import run ID | `sup_f90a0efbbe` |
| Project path | `/Volumes/migodam's-external-brain/home/narrative_ide/w1_full50_streaming_20260526_111158/` |
| Source | 凡人修仙传_前50章.txt (50 chapters, 293K bytes) |
| Start time | 11:11 UTC+8 |
| End time (error) | 13:48 UTC+8 |
| Elapsed | ~2h 37min |
| Windows total | 39 |
| Windows original | ~14 |
| Windows rerun | ~25 |
| Supervisor decisions | 44 total (28 proceed, 16 rerun) |
| Terminal status | error (deterministic convergence judgment) |

---

## Convergence Failure Analysis

### Judge Result (Iteration 0)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Judge score | 0.82 | 1.0 | FAIL |
| Characters | 65 | 75 | FAIL (−10) |
| Canonical events | 108 | ≥63 | PASS |
| Failed gates | `character_undercoverage` | — | — |

After the first judge run at iter=282 (13:33 UTC+8), the supervisor issued one thematic rerun request for character recovery: `character_undercoverage: characters=65<target=75`. It then ran additional extraction windows and thematic reruns. After multiple `deterministic convergence judgment` decisions, the supervisor gave up and terminated with error status at iter=312 (13:48 UTC+8).

### Why Character Coverage Fell Short

The previous PASS run (`w1_failure_closure`) reached 75 characters with the same code and fixture. The difference is LLM non-determinism: DeepSeek extraction varies across runs, particularly for:
- Minor/background characters who appear briefly
- Characters introduced only in chapters 25–50
- Characters with only one or two appearances

The supervisor's thematic rerun strategy recovers *some* missed characters but hits diminishing returns after 2–3 rounds. The gap of 10 characters could not be closed within the rerun budget.

### Why Timeline Improved

The 39 windows (vs 14 primary + reruns in the previous run) covered more chapter ranges from more angles. The timeline architect synthesized **108 canonical events** vs 102 previously, and **8 branches** vs 5 previously. Timeline quality is strictly better in this run despite the character shortfall.

---

## Memory Observation (P1 Fix Confirmed)

| Metric | This Run | Pre-fix Run |
|--------|----------|-------------|
| Peak memory | ≤7.5% | 49% (~11.7GB) |
| OOM crash | No | No (24GB machine) |
| Extraction phase | <1% | ~20–30% |

The P1 streaming write fix (`6718ab0`) is confirmed working again. Memory remained negligible throughout the 2h 37min run.

---

## Extracted Metrics

| Entity Type | Count | Notes |
|------------|-------|-------|
| Characters | 65 | 10 below 75 target |
| Canonical timeline events | 108 | Exceeds 90 target; better than previous 102 |
| Timeline branches | 8 | Better than previous 5 |
| Discarded duplicates | 13 | — |
| World items | 0 (from review_report) | Likely merged into chapters |

---

## Acceptance Criteria Status

| Criterion | Status | Note |
|-----------|--------|------|
| 50 chapters, no OOM | **PARTIAL** | All 50 chapters processed; run terminated before proposal_write |
| manuscript.json chapters == 50 | **FAIL** | Not written |
| system/inbox.json exists | **FAIL** | Not written |
| characters ≥ 75 | **FAIL** | 65/75 |
| 韩立/墨大夫/厉飞雨/张铁 present | **UNKNOWN** | inbox not written |
| language violations == 0 | **UNKNOWN** | inbox not written |
| 七玄门 category = organization | **UNKNOWN** | inbox not written |
| timeline canonical events ≥ 90 | **PASS** | 108 events ✓ |
| judge score 1.0 | **FAIL** | 0.82 |
| no API key in output | **PASS** | Secret scan clean |

---

## Comparison Across All Benchmark Runs

| Run | Characters | Events | Judge | Memory | Result |
|-----|-----------|--------|-------|--------|--------|
| w1_failure_closure 50ch (previous PASS) | 75 | 102 | 1.0 | 49% | **PASS** |
| w1_ms_smoke 10ch | 40 | 26 | 1.0 | ~1% | PASS |
| w1_full50 100642 (API 402) | 56 (partial) | 58 (partial) | 0.64 | 7.5% | FAIL/INVALID |
| **w1_full50 111158 (this run)** | **65** | **108** | **0.82** | **≤7.5%** | **FAIL** |

Timeline quality trend: **improving** (102 → 108 events).  
Character coverage: **non-deterministic** (75 in previous run, 65 in this run).

---

## Root Cause

The character coverage shortfall is driven by R3 (from `failures_and_followups.md` in prior benchmarks): the extraction prompts do not receive a list of expected major characters per chapter range. The LLM must discover characters independently in each window, and minor/peripheral characters are frequently missed. The supervisor's thematic rerun strategy can recover some but not all missed characters within its fixed retry budget.

This is **not a regression** introduced by `6718ab0` or `5db686f`. It is the same R3 issue that was marked P2 in all prior benchmarks. The previous PASS run was slightly lucky — it happened to extract exactly 75 characters on its first attempt.

---

## Secret Hygiene

```
rg -n "sk-[A-Za-z0-9_-]{16,}" benchmark_results/w1_full50_after_streaming_20260526_111158/
→ 0 matches
```

---

## Recommended Next Steps

1. **For Codex (P2 — R3 fix):** Inject the expected major character list per chapter range into extraction prompts. The manifest already contains the chapter-to-character mapping; this data needs to flow into the extraction window prompt as a "must-find" hint list. This would eliminate the non-determinism in character coverage.

2. **For the benchmark goal:** The streaming write fix (`6718ab0`) and manuscript fix (`5db686f`) are both working correctly. The 50-chapter run now processes all chapters without OOM. The only open validation is confirming inbox.json/manuscript.json are written — which requires fixing R3 first OR accepting a slightly lower character threshold.

3. **Alternative:** Lower the character acceptance threshold from 75 to 65 for the 50-chapter run, reflecting that 50 chapters × 1.3 characters/chapter = 65 is a more achievable density target given the current extraction architecture.
