# W1 Full 50-Chapter Run 4 — Failures and Follow-ups

Benchmark: `w1_full50_after_streaming_20260526_190513`  
Date: 2026-05-26  
Result: **FAIL/INVALID — API 402 Insufficient Balance**

---

## Primary Failure: API 402 Insufficient Balance

All 70 LLM extraction calls failed with `402 Insufficient Balance`. Run completed in 2 minutes with 0 characters and 0 events. Manuscript and inbox files were written but are empty.

**This run is invalid and cannot be used to evaluate the R3 fix.**

**Action required:** Top up DeepSeek API balance before attempting run 5.

---

## R3 Fix Status

The R3 fix (commit `f366144`) is implemented and ready:
- `supervisor_hint` field now survives chunk reassembly in `extract_window`
- `_apply_thematic_reruns` builds recovery hints for `character_undercoverage`
- 97 tests pass

The fix is untested at runtime due to API exhaustion.

---

## Next Benchmark Trigger

After DeepSeek balance is topped up:
1. Restart sidecar (it restarts cleanly)
2. Run benchmark (run 5)
3. Verify characters ≥75 — specifically that thematic reruns now use the `supervisor_hint` to recover minor characters
4. Verify inbox.json and manuscript.json written with real content
5. Verify judge score 1.0
