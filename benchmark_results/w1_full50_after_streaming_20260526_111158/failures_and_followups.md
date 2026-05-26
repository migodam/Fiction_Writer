# W1 Full 50-Chapter Rerun — Failures and Follow-ups

Benchmark: `w1_full50_after_streaming_20260526_111158`  
Date: 2026-05-26  
Result: **FAIL — character_undercoverage (65/75)**

---

## Primary Failure: Character Convergence (R3 — P2)

The judge's `character_undercoverage` gate requires ≥75 characters. This run extracted 65 after 39 windows and 44 supervisor decisions including multiple thematic reruns for character recovery.

**Root cause:** Extraction prompts do not receive the expected major character list per chapter range. The LLM must discover characters independently. Minor/peripheral characters appearing in only 1–2 chapters are frequently missed, and the supervisor's rerun budget is consumed before the gap closes.

**Impact:** Run terminated before `proposal_write`. No inbox.json or manuscript.json.

**Fix (Codex P2):** Inject the expected major character list per chapter range (from the manifest `chapter_range_characters` field) as a "must-find" hint in extraction prompts. This reduces non-determinism in character coverage.

---

## Confirmed Working

### Streaming Write Fix (R1 — RESOLVED)
Peak memory: ≤7.5% throughout the 2h37m run. No OOM. Confirmed across two full 50-chapter runs.

### API Balance
No 402 errors. Balance sufficient for the full 50-chapter run.

### Timeline Quality
108 canonical events (target ≥90, previous PASS: 102). 8 branches (previous PASS: 5). Timeline architecture is improving run-over-run.

---

## Remaining Open Items

### R2 (P2): Residual Duplicate Event Clusters
13 duplicate events discarded in this run. Cross-window fuzzy dedup pass would reduce this.

### R3 (P2): Missing Major Characters — PRIMARY BLOCKER
Character coverage is non-deterministic: 75 in previous PASS, 65 in this run. The supervisor's thematic rerun strategy cannot reliably recover 10 missing characters within its budget.

**Codex action:** Inject `expected_characters` hint list (from manifest) into the W1 extraction window prompt. Expected to raise character coverage to 80–90 consistently.

### R4 (P3): Branch Density at Limit
8 branches now (up from 5). None hit the 36-event cap in this run, but worth monitoring as event counts grow.

### R5 (P2): Graceful API Budget Exhaustion
No 402 errors in this run, but the mechanism (detect 402 → terminate immediately) would still improve robustness. See previous benchmark.

---

## Threshold Discussion

The character acceptance threshold (75) was set based on the first 50-chapter PASS run. Two subsequent 50-chapter runs have gotten 65 characters. Options:

1. **Fix R3** (preferred): Character injection makes 75+ consistently achievable.
2. **Lower threshold to 65**: More achievable given current extraction, but reduces quality bar.
3. **Rerun**: Each run has different LLM draws; another attempt might hit 75+ naturally.

---

## Next Benchmark Trigger

After R3 (character injection) is implemented:
1. Run 50-chapter benchmark
2. Verify characters ≥75 on first judge pass (no thematic reruns needed)
3. Verify inbox.json and manuscript.json written
4. Verify judge score 1.0
