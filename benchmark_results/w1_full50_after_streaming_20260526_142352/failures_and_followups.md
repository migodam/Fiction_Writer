# W1 Full 50-Chapter Run 3 — Failures and Follow-ups

Benchmark: `w1_full50_after_streaming_20260526_142352`  
Date: 2026-05-26  
Result: **FAIL — character_undercoverage (68/75)**

---

## Primary Failure: Character Convergence (R3 — P2)

The judge's `character_undercoverage` gate requires ≥75 characters. This run extracted 68 after 44 windows and 47 supervisor decisions including multiple thematic reruns for character recovery.

**Root cause:** Extraction prompts do not receive the expected major character list per chapter range. The LLM must discover characters independently. Minor/peripheral characters appearing in only 1–2 chapters are frequently missed, and the supervisor's rerun budget is consumed before the gap closes.

**Three consecutive full runs have now failed on this gate:**
- Run 2 (111158): 65 characters
- Run 3 (142352): 68 characters
- Previous PASS (failure_closure): 75 characters — one favorable draw, now an outlier

**Impact:** Run terminated before `proposal_write`. No inbox.json or manuscript.json.

**Fix (Codex P2):** Inject the expected major character list per chapter range (from the manifest `chapter_range_characters` field) as a "must-find" hint in extraction prompts. This reduces non-determinism in character coverage.

---

## Confirmed Working

### Streaming Write Fix (R1 — RESOLVED)
No OOM in any of the three 50-chapter runs. Memory percentage unavailable in run 3 monitor (psutil env issue), but no crash occurred. Confirmed across runs 1 and 2: peak ≤7.5% vs 49% pre-fix.

### API Balance
No 402 errors in runs 2 or 3. Balance sufficient for full 50-chapter runs.

---

## Remaining Open Items

### R2 (P2): Residual Duplicate Event Clusters
0 duplicates discarded in this run (vs 13 in run 2). Run-to-run variance; cross-window fuzzy dedup would make this deterministic.

### R3 (P2): Missing Major Characters — PRIMARY BLOCKER
Character coverage range across three full runs: 65–68 characters. The 75 threshold is not reachable via thematic reruns alone. Structural fix required.

**Codex action:** Inject `expected_characters` hint list (from manifest) into the W1 extraction window prompt. Expected to raise character coverage to 80–90 consistently.

### R4 (P3): Timeline Variance
80 canonical events in this run (vs 108 in run 2, 102 in previous PASS). All three results are from the same code. Timeline extraction is also non-deterministic; the ≥90 benchmark target was only met in run 2. The R3 fix may indirectly stabilize event extraction by providing richer context (character list) to extraction prompts.

### R5 (P2): Graceful API Budget Exhaustion
No 402 errors in runs 2 or 3, but the mechanism (detect 402 → terminate immediately) would still improve robustness.

---

## Cross-Run Comparison Table

| Benchmark | Characters | Events | Judge | Supervisor Decisions | Result |
|-----------|-----------|--------|-------|---------------------|--------|
| failure_closure 50ch | 75 | 102 | 1.0 | — | PASS |
| full50 run 1 (100642) | 56 (partial) | 58 (partial) | 0.64 | — | FAIL/INVALID (402) |
| full50 run 2 (111158) | 65 | 108 | 0.82 | 44 | FAIL |
| full50 run 3 (142352) | 68 | 80 | 0.82 | 47 | FAIL |

---

## Next Benchmark Trigger

After R3 (character injection) is implemented:
1. Run 50-chapter benchmark
2. Verify characters ≥75 on first judge pass (no thematic reruns needed)
3. Verify inbox.json and manuscript.json written
4. Verify judge score 1.0
5. Verify timeline events ≥90
