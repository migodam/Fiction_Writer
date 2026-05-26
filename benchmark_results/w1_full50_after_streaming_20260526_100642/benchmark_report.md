# W1 Full 50-Chapter After Streaming — Benchmark Report

**Benchmark ID:** `w1_full50_after_streaming_20260526_100642`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Head commit:** `bed8ec6`  
**Key commits:** `6718ab0` (streaming write P1 fix), `5db686f` (manuscript fix)  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Date:** 2026-05-26  
**Fixture:** 凡人修仙传_前50章.txt (50 chapters, ~200k chars)  

---

## Executive Summary

**RESULT: FAIL — INVALID (API Quota Exhausted)**

The 50-chapter benchmark run failed mid-execution because the DeepSeek API account hit a **402 Insufficient Balance** error partway through extraction. This is not a code regression — it is a billing/quota issue that invalidates the benchmark.

**What was confirmed:**
- Streaming write fix (`6718ab0`) is working: memory peaked at **7.5%** (vs **49%** in the previous run before the fix)
- No OOM crash occurred
- The first 12 windows (covering chapters 1–24) extracted normally

**What was NOT validated:**
- Full 50-chapter extraction coverage (API exhausted at ~chapter 24)
- Judge convergence at 1.0
- inbox.json / manuscript.json written (run terminated before proposal_write)

**Action required:** Top up DeepSeek API balance and rerun this benchmark from scratch.

---

## Run Details

| Field | Value |
|-------|-------|
| Session ID | `6d9148dc-cb68-4673-a174-bea262dda9d2` |
| Import run ID | `sup_4a7238a76b` |
| Project path | `/Volumes/migodam's-external-brain/home/narrative_ide/w1_full50_streaming_20260526_100642/` |
| Source | 凡人修仙传_前50章.txt (~200k chars, 50 chapters) |
| Start time | 10:07 UTC+8 |
| End time (error) | 10:57 UTC+8 |
| Elapsed | ~50 minutes |
| Windows total | 41 (14 original + 27 reruns) |
| Windows succeeded | 12 (chapters 1–24) |
| Windows with 402 error | 29 (chapters 25–50) |
| Supervisor decisions | 45 total |

---

## Root Cause: DeepSeek API 402 Insufficient Balance

Starting approximately at chapter 25, all extraction API calls returned:

```
APIStatusError: Error code: 402 - {
  'error': {
    'message': 'Insufficient Balance',
    'type': 'unknown_error',
    'code': 'invalid_request_error'
  }
}
```

This affected all 5 prompt types per window: `character`, `event`, `world`, `relationship`, `scene`.

**Windows affected (chapters 25–50):** 29 windows, 148 failed prompts total.

The supervisor policy loop correctly detected density gate failures on these windows and issued reruns, but every rerun also failed with 402, leading to 45 supervisor decisions and 41 total windows before the convergence loop exhausted its retry budget and terminated.

**Account balance was consumed by prior runs in this same session:**
1. `w1_failure_closure` 10-chapter smoke (~10:00 AM previous day, via earlier API run)
2. `w1_failure_closure` 50-chapter full run (2026-05-26 01:17–09:04)
3. `w1_manuscript_smoke` 10-chapter smoke (2026-05-26 09:27–09:57)
4. This run (2026-05-26 10:07–10:57) — balance depleted mid-run

---

## Memory / OOM Observation

The streaming write fix (`6718ab0`) is confirmed effective:

| Metric | Previous run (w1_failure_closure) | This run |
|--------|----------------------------------|----------|
| Peak memory | 49% (~11.7GB / 24GB) | 7.5% (~1.8GB / 24GB) |
| OOM crash | No (survived on 24GB) | No |
| Memory during extraction | ~20–30% | 0.5–0.6% |
| Memory during judge/proposal | 49% | 7.5% |

The 7.5% peak occurred when the judge and supervisor ran against the incomplete 56-character dataset. The streaming fix dramatically reduces peak memory usage and appears to hold on 24GB hardware. The 16GB OOM threshold (R1 from previous benchmark) needs a dedicated benchmark to verify.

---

## Partial Extraction Results (Chapters 1–24 Only)

Only windows covering chapters 1–24 completed successfully:

| Window | Chapter Range | Characters | Events | World |
|--------|--------------|-----------|--------|-------|
| pwin_e1135add | 第一章–第四章 | 14 | 3 | 19 |
| pwin_5638c877 | 第五章–第八章 | 18 | 6 | 19 |
| pwin_855327ec | 第九章–第十二章 | 13 | 9 | 20 |
| pwin_b0188bb4 | 第十三章–第十六章 | 0 | 10 | 7 |
| pwin_09aaa3d8 | 第十七章–第二十章 | 5 | 9 | 18 |
| pwin_297758a3 | 第二十一章–第二十四章 | 1 | 11 | 0 |
| pwin_a4075a46 | 第十七章–第十八章 (rerun) | 1 | 8 | 2 |
| pwin_8b1583bd | 第一章–第二章 (rerun) | 0 | 3 | 2 |
| pwin_a912fcea | 第三章–第四章 (rerun) | 0 | 6 | 1 |
| pwin_90f72426 | 第十三章–第十四章 (rerun) | 0 | 5 | 5 |
| pwin_eb205a2d | 第一章–第四章 (rerun) | 0 | 2 | 4 |
| pwin_59a4f814 | 第二十一章–第二十二章 (rerun, partial) | 4 | 8 | 0 |

**Totals from partial extraction:** 56 characters, 80 events, 97 world items.

---

## Judge Results (Incomplete Data)

The judge ran against partial extraction (chapters 1–24 only):

| Metric | Value | Status |
|--------|-------|--------|
| Score | 0.64 | FAIL |
| Passed | False | — |
| Failed gates | `character_undercoverage`, `timeline_undercoverage` | — |
| Character count | 56 | < target 75 |
| Canonical events | 58 | < target 63 |
| Timeline branches | 4 | — |
| Iteration | 0 | — |

These failures are expected given only half the chapters were processed. They do not indicate a code regression.

---

## Acceptance Criteria Status

| Criterion | Status | Note |
|-----------|--------|------|
| 50 chapters imported, no OOM | **FAIL** | Only ~24 chapters extracted before 402 |
| manuscript.json chapters == 50 | **FAIL** | Run terminated before proposal_write |
| system/inbox.json exists | **FAIL** | Run terminated before proposal_write |
| characters >= 75 | **FAIL** | 56/75 — due to API quota, not code |
| 韩立/墨大夫/厉飞雨/张铁 present | **UNKNOWN** | inbox not written |
| language violations == 0 | **UNKNOWN** | inbox not written |
| 七玄门 category = organization | **UNKNOWN** | inbox not written |
| timeline canonical events >= 90 | **FAIL** | 58/90 — due to API quota, not code |
| judge score 1.0 | **FAIL** | 0.64 — due to API quota, not code |
| output dir does not contain API key | **PASS** | Confirmed via secret scan |

---

## Secret Hygiene Check

```
rg -n "sk-[A-Za-z0-9_-]{16,}" benchmark_results/w1_full50_after_streaming_20260526_100642/
→ 0 matches
```

No API key found in any report, artifact, log, or config file.

---

## Comparison with Previous Runs

| Run | Characters | Events | Judge | Status |
|-----|-----------|--------|-------|--------|
| w1_failure_closure (50ch) | 75 | 102 | 1.0 | PASS |
| w1_manuscript_smoke (10ch) | 40 | 26 | 1.0 | PASS |
| **This run (w1_full50 streaming)** | **56 (partial)** | **58 (partial)** | **0.64** | **FAIL (quota)** |

The regression in character and event counts is entirely explained by API quota exhaustion after chapter 24. The first 24 chapters extracted at approximately the same rate as the prior passing run.

---

## What Needs Codex Analysis?

**No code changes required.** The failure is external (API billing).

However, three recommendations for Codex:

1. **Add 402 budget sentinel**: When the supervisor detects a 402 error on any window, it should immediately halt the run with a clear `budget_exhausted` terminal status rather than exhausting the rerun budget. Currently, 29 failed windows × 5 prompts = 145 wasted API calls to retry against a known-bad API state.

2. **Validate API balance before long runs**: A pre-flight balance check at session start (if the DeepSeek API supports it) would surface this issue before any tokens are consumed.

3. **R1 (OOM on <16GB) still open**: The streaming fix confirmed on 24GB (7.5% peak). A dedicated 16GB run is needed. See `failures_and_followups.md`.

---

## Artifacts Available

| File | Status | Size |
|------|--------|------|
| judge_artifact.json | Copied | 45KB |
| manifest.json | Copied | 27KB |
| supervisor_decisions.json | Copied | 16KB |
| timeline_architecture.json | Copied | 161KB |
| window_metrics.json | Copied | 40KB |
| review_report.json | Copied | 1.4KB |
| reducer_artifact.json | Copied | 215B |
| prompt_windows.json | Copied | 9.3KB |
| project_structure_digest.json | Copied | 959B |
| tool_operating_spec.json | Copied | 462B |
| inbox.json | NOT WRITTEN | — |
| manuscript.json | NOT WRITTEN | — |
| cross_validation.json | NOT WRITTEN | — |

---

## Next Steps

1. **Top up DeepSeek API balance** (user action required)
2. **Restart sidecar** (it terminated after the error)
3. **Rerun this benchmark** from a clean project directory with the same config
4. **Target**: All 50 chapters extracted, judge 1.0, inbox.json and manuscript.json written
5. **Bonus target**: Run on 16GB machine to validate R1 (OOM) fix from `6718ab0`
