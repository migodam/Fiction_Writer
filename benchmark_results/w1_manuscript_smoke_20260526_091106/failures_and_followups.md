# W1 Manuscript Smoke — Failures and Follow-ups

Benchmark: `w1_manuscript_smoke_20260526_091106`  
Date: 2026-05-26  
Result: **PASS**

---

## Validated Fix

**Manuscript chapters now written in supervisor path.**

The previous regression (manuscript.json always empty in supervisor path) is resolved by commit `5db686f`. The fix uses `state["chunks"]` as a deterministic fallback when `chunk_extractions` is empty (which is always the case in the supervisor path). 10 chapters written in order with full content.

---

## Remaining Open Items (from w1_failure_closure benchmark)

These were not addressed by the manuscript fix and remain open:

### R1 (P1): OOM on <24GB Machines

`node_write_to_project()` loads the full entity registry into RAM simultaneously before writing proposals. The 50-chapter run survived on 24GB but will OOM on smaller machines. Fix: stream-write proposals one entity at a time.

**Suggested Codex action:** Refactor `node_write_to_project()` to write proposals incrementally using the agent-plus-tools pattern.

### R2 (P2): Residual Duplicate Event Clusters

4 event clusters were not collapsed in the 50-chapter run. These share semantic meaning but have different `dedupeKey` values due to window-level NLP variation. A cross-window fuzzy dedup pass would address this.

### R3 (P2): Missing Major Characters in Some Windows

Some windows show `missing_majors_count > 0` for key characters. The supervisor's rerun policy compensates, but it inflates the rerun rate (86% reruns in the 50-chapter run). Fix: inject expected major character list per chapter range into extraction prompts.

### R4 (P3): Branch Density at Limit

Two timeline branches hit the 36-event cap. Events beyond the cap are demoted to scene beats. Consider raising the cap to 50 for main and antagonist branches.

---

## Next Re-benchmark Trigger

After R1 (OOM fix) is merged, run the full 50-chapter benchmark on a 16GB machine to verify no OOM.

Acceptance criteria for next run:
1. All 50-chapter manuscript criteria met (already passing on 24GB)
2. Run completes without OOM on ≤16GB
3. All other metrics remain at current levels
