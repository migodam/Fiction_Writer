# W1 Failure Closure — Remaining Issues and Follow-ups

Benchmark: `w1_failure_closure_20260526_011743`  
Date: 2026-05-26  
Branch: `codex/w1-orchestrated-import-quality`

---

## Status: 5/6 Failures Closed

| Failure | Status |
|---|---|
| OOM at proposal_write | FIXED |
| Character undercoverage | FIXED |
| Language mismatch | FIXED |
| World routing | FIXED |
| Timeline density | FIXED |
| Chapter order / manuscript content | **STILL FAILING** |

---

## Remaining Failure: Chapter Content Not Written

### Symptom
`manuscript.json` contains `{"chapters": [], "source_file": "...", "imported_at": "..."}` — an empty chapter list.

### Root Cause
`node_build_manuscript()` in `sidecar/workflows/w1_import.py` reads `state["manuscript_chapters"]`. In the non-supervisor (legacy) path, `state["manuscript_chapters"]` is populated by `node_split_and_process_chunks()`. In the supervisor path (`use_supervisor=True`), this state key is never populated — chapters are represented as `state["chunks"]` dicts, not as `manuscript_chapters` entries.

### Fix Location
- `sidecar/supervisor/policy.py`: `_policy_with_progress()` at line ~700+ (after extract phase)
- `sidecar/workflows/w1_import.py`: `node_build_manuscript()` at line ~3000+

### Fix Description
After the window extraction phase completes in `_policy_with_progress()`, reconstruct `state["manuscript_chapters"]` from `state["chunks"]` by mapping each chunk's `text` and `chapter_number`/`chapter_title` fields into the format expected by `node_build_manuscript()`.

### Acceptance Criterion
`manuscript.json` must contain exactly 50 entries (one per source chapter), each with non-empty `title` and `content` fields. Chapter order must be 1→50 monotonically.

---

## Residual Risks (Not Blocking, Need Monitoring)

### R1: OOM Risk on <24GB Machines

**What:** `node_write_to_project()` loads the full entity registry (75 chars + 87 events + 107 world items = 269 entities + all state blobs) into RAM simultaneously before writing any proposals.

**Risk:** A machine with 16GB RAM would have hit OOM in this run. The current run peaked at 49% of 24GB = 12.3GB.

**Recommended fix:** Stream-write proposals: iterate entity registry one entity at a time, write one `inbox.json` bundle per entity, release reference. Alternatively use the agent-plus-tools pattern: define a `write_proposal_bundle(entity_id, fields)` tool that appends to inbox.json and returns a receipt. Agent calls it per entity — RAM never accumulates.

**Priority:** P1 — required before any production use or smaller-machine testing.

---

### R2: Residual Duplicate Event Clusters (4 clusters)

**What:** 4 event clusters exist in `timeline_architecture.json` where multiple events have the same semantic meaning (e.g., 3 instances of "墨大夫传授无名口诀"). The current dedup policy merged 171 duplicates but didn't collapse these 4.

**Root cause:** Cross-window dedup uses `dedupeKey` matching. These 4 clusters have slightly different keys due to different window-level NLP outputs (different participant sets or chapter assignments across windows).

**Recommended fix:** Post-reduce pass using fuzzy title matching + participant overlap + chapter proximity to merge residual duplicates that share ≥2 of 3 match dimensions.

**Priority:** P2 — affects timeline readability but not correctness.

---

### R3: Missing Major Character in 5 Windows

**What:** 5 distinct windows reported `missing_majors_count > 0` (mainly 马副门主, 墨大夫, 张铁, 厉飞雨, 瘦长师兄 in various windows). The supervisor's rerun policy rescued these via window reruns, but it required 12 reruns for 14 original windows — 86% rerun rate.

**Root cause:** The extraction prompt does not explicitly enumerate expected major characters for a given chapter range. The model may miss a character if they appear only briefly in that chapter.

**Recommended fix:** Inject the chapter-specific cast of expected characters from the `expected_characters` field in the manifest into each window extraction prompt. This gives the model an explicit checklist.

**Priority:** P2 — reduces reruns and improves first-pass quality.

---

### R4: Branch Density at Hard Limit

**What:** `branch_import_main` and `branch_theme_antagonist` each have exactly 36 canonical events — the density policy limit. Events beyond 36 were demoted to scene beats. This means important late-story events may be missing from the canonical timeline.

**Impact:** The QA review raised 2 warnings about this. The judge still passed (score=1.0) because the overall event count (102) is within expected range, but narrative completeness for the 50 chapters may be affected.

**Recommended fix:** Evaluate raising the per-branch cap from 36 to 50 for main-character and antagonist branches. Alternatively, add a secondary timeline tier for "important scene beats" that is distinct from simple scene beats.

**Priority:** P3 — low risk but may affect user experience of the imported timeline.

---

## Action Items for Codex

| ID | Action | Priority | Owner |
|---|---|---|---|
| ACT-01 | Fix manuscript chapter writing in supervisor path | P1 | Codex |
| ACT-02 | Fix OOM in `node_write_to_project()` via streaming writes | P1 | Codex |
| ACT-03 | Add cross-window semantic dedup for residual clusters | P2 | Codex |
| ACT-04 | Inject expected major character lists into extraction prompts | P2 | Codex |
| ACT-05 | Raise branch density limit for main/antagonist branches | P3 | Codex |

---

## Re-benchmark Trigger

Re-run this benchmark after ACT-01 and ACT-02 are merged. The acceptance criteria for the next run:

1. `manuscript.json` must have 50 chapters (non-empty)
2. Run must complete without OOM on a 16GB machine (or simulator)
3. All other metrics must remain at current levels (75+ chars, 100+ events, 6+ containers, 0 language violations)
4. Judge score must remain 1.0
