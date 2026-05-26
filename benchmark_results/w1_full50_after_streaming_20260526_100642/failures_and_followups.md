# W1 Full 50-Chapter After Streaming — Failures and Follow-ups

Benchmark: `w1_full50_after_streaming_20260526_100642`  
Date: 2026-05-26  
Result: **FAIL (INVALID — API quota exhausted)**

---

## Primary Failure: DeepSeek API 402 Insufficient Balance

All extraction calls for chapters 25–50 returned HTTP 402 `Insufficient Balance`. The DeepSeek account balance was consumed by prior benchmark runs on the same day:
- `w1_failure_closure` 50-chapter run (01:17–09:04 UTC+8)
- `w1_manuscript_smoke` 10-chapter smoke (09:27–09:57 UTC+8)

**Impact**: 29/41 windows failed. Judge received partial data (56 chars / 58 events) and could not converge. Run terminated in `error` state. No inbox.json or manuscript.json written.

**Fix**: Top up DeepSeek API balance and rerun from a fresh project directory.  
**Status**: User refunded balance. Rerun started at 11:11 UTC+8 (session `f920e767`).

---

## Confirmed: Streaming Write Fix Working (R1 Resolved)

**R1 (P1): OOM on <24GB machines** — previously marked open in `w1_failure_closure/failures_and_followups.md`.

Peak memory in this run: **7.5%** (~1.8GB / 24GB), vs **49%** (~11.7GB) in the pre-fix run.

The streaming write refactor in `6718ab0` demonstrably works:
- `_WRITE_KEYS` whitelist slims the write_input before entity loops
- `del merged + gc.collect()` frees intermediate state immediately
- Progressive entity pop prevents proposals accumulating in memory
- Manuscript failsafe writes immediately

**R1 closure**: Confirmed resolved on 24GB. To verify 16GB threshold, run a dedicated benchmark on a ≤16GB machine. Not blocking current work.

---

## Remaining Open Items (Inherited from w1_failure_closure)

### R2 (P2): Residual Duplicate Event Clusters

4 event clusters were not collapsed in the 50-chapter run (from the PASS run). Cross-window fuzzy dedup pass would address this.

### R3 (P2): Missing Major Characters in Some Windows

Supervisor's rerun policy compensates but inflates the rerun rate. Fix: inject expected major character list per chapter range into extraction prompts.

### R4 (P3): Branch Density at Limit

Two timeline branches hit the 36-event cap. Events beyond the cap are demoted to scene beats. Consider raising to 50 for main and antagonist branches.

---

## New Item: Graceful API Budget Exhaustion (R5 — P2)

When a window fails with HTTP 402 (billing exhaustion), the supervisor currently retries the window as if it were a transient LLM failure. This wastes 29 × 5 = 145 API calls before giving up.

**Fix**: Detect 402 status in the extraction layer and immediately raise a `BudgetExhaustedError` that terminates the run with a clear `budget_exhausted` terminal status rather than exhausting the rerun budget.

**Suggested Codex action**: In the window extraction error handler, check for HTTP 402 and propagate a sentinel error that bypasses the supervisor retry loop.

---

## Next Re-benchmark Trigger

After the 11:11 rerun (session `f920e767`) completes, verify:
1. All 50 chapters extracted
2. Characters ≥ 75, key characters present
3. Timeline events ≥ 90 (previous PASS: 102)
4. Judge score 1.0
5. Inbox + manuscript written
6. Peak memory stays below 10% on 24GB

If passing, promote `6718ab0` and `5db686f` as validated on 50-chapter full run.
