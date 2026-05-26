# W1 Full 50-Chapter Run 4 — Benchmark Report

**Benchmark ID:** `w1_full50_after_streaming_20260526_190513`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Head commit:** `f366144` (R3 fix applied)  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Date:** 2026-05-26  
**Run number:** 4

---

## Executive Summary

**RESULT: FAIL/INVALID — API 402 Insufficient Balance**

Run completed in 2 minutes because all 70 LLM extraction calls failed with `402 Insufficient Balance`. The R3 fix (`f366144`) was deployed but could not be validated — no extraction occurred. The manuscripts and inbox files were written but contain 0 characters and 0 events.

This is the same failure mode as run 1 (`w1_full50_100642`). The DeepSeek API balance was depleted by runs 2 and 3 (each ~100 minutes of deep extraction).

**Action required: Top up DeepSeek API balance before running again.**

---

## Run Details

| Field | Value |
|-------|-------|
| Session ID | `72805962-a64e-414a-9651-49fe1b9c9fae` |
| Import run ID | `sup_a483ce0ac3` |
| Start time | 19:05 UTC+8 |
| End time | 19:07 UTC+8 |
| Elapsed | ~2 min |
| Windows total | 14 (all failed 402) |
| Failed prompts | ~70 (5 per window × 14 windows) |
| Terminal status | `done` (all empty) |

---

## R3 Fix Status

The R3 fix (`f366144`) was implemented and committed before this run:
- `sidecar/supervisor/tools.py`: `supervisor_hint` field wired through chunk reassembly
- `sidecar/supervisor/policy.py`: character recovery hints built for `character_undercoverage` reruns
- 97 tests pass

The fix is deployed but cannot be validated until the API balance is restored and a new run completes.

---

## Required Next Step

Top up DeepSeek API balance, then run benchmark again (run 5). The R3 fix is in place — no code changes needed before run 5.

Estimated cost for one full 50-chapter deep run: based on prior runs (~100 minutes of continuous DeepSeek V4 Pro usage). Ensure sufficient balance for at least 2 hours of inference.
