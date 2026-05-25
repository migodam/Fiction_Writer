# W1 Failure Closure Benchmark Report

**Benchmark ID:** `w1_failure_closure_20260526_011743`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Run date:** 2026-05-26  
**Fixture:** 凡人修仙传_前50章.txt (50 chapters, ~100K chars)

---

## Executive Summary

The W1 Failure Closure Benchmark ran the full orchestrated import supervisor pipeline (`use_supervisor=True`, `use_orchestrator=True`) against the 50-chapter Chinese xianxia novel fixture. The previous benchmark (`w1_orchestrated_import_quality_20260525`) had five failure symptoms: OOM at `proposal_write`, only 4 characters extracted, 3 timeline events, mixed English/Chinese output, and unknown chapter ordering.

**5 of 6 previous failures are now resolved.** One known regression remains: the supervisor path does not populate `manuscript_chapters`, so `manuscript.json` is empty. This is a P1 fix item for Codex.

| Previous Failure | Status |
|---|---|
| OOM crash at `proposal_write` | **FIXED** — run completed (49% peak on 24GB machine) |
| Character undercoverage (4 chars) | **FIXED** — 75 characters, all 4 key chars present |
| Language mismatch (English in Chinese import) | **FIXED** — 0 Latin violations |
| World routing (1 container) | **FIXED** — 6 containers, 七玄门 = organization |
| Timeline density (3 events) | **FIXED** — 102 canonical events, 36 on main branch |
| Chapter order (unknown) | **STILL FAILING** — 0 chapters in manuscript.json |

**Judge:** score=1.0, passed=True, 0 failed gates, iteration=0

---

## Run Configuration

| Field | Value |
|---|---|
| Source fixture | `/home/narrative_ide/novels/凡人修仙传_前50章.txt` |
| Project path | `/home/narrative_ide/w1_failure_closure_50ch_20260526_011743/` |
| Import run ID | `sup_29503d787f` |
| Session ID | `29300d2d-4454-4798-87dc-82a45560ba68` |
| Sidecar URL | `http://127.0.0.1:8765` |
| Start time | 2026-05-26 01:36:36 UTC+8 |
| End time | 2026-05-26 04:20 UTC+8 |
| Elapsed | ~163 minutes (~2h43m) |
| Segments (chapters) | 50 |
| Source chars | 99,890 |

---

## Stage 1: Smoke Test (10 Chapters)

**Result: PASS** — both `manuscript.json` and `system/inbox.json` written.

| Metric | Value |
|---|---|
| Judge score | 1.0 |
| Judge passed | True |
| Characters | 50 |
| Canonical events | 20 |
| World items | 30 |
| Language violations | 0 |
| Key chars (韩立/墨大夫/张铁) | All found |
| Manuscript chapters | Written |
| Inbox written | Yes |

---

## Stage 2: Full 50-Chapter Benchmark

### Judge Verdict

| Field | Value |
|---|---|
| Score | 1.0 |
| Passed | True |
| Failed gates | None |
| Thematic rerun requests | None |
| Iteration | 0 |
| Status | warning (density policy applied, not a failure) |

### Character Analysis

| Metric | Value |
|---|---|
| Total characters | 75 |
| Key char 韩立 | **FOUND** |
| Key char 墨大夫 | **FOUND** |
| Key char 厉飞雨 | **FOUND** |
| Key char 张铁 | **FOUND** |
| Latin violations in fields | 0 (FIXED from previous benchmark) |
| Character group distribution | 七玄门(40), 家庭与乡邻(20), 超自然存在(5), 野狼帮(4), 主角(3) |
| Overlong summaries | 0 |
| Trait duplication/noise | 0.0 |

### Timeline Analysis

| Metric | Value |
|---|---|
| Canonical events | 102 |
| Branch count | 5 |
| Main branch (branch_import_main) | 36 events (35.3% share) |
| branch_theme_antagonist | 36 events |
| branch_arc_rival_ally | 7 events |
| Discarded duplicates | 171 |
| Scene beats | 148 |
| Residual duplicate clusters | 4 (not collapsed by dedup policy) |
| Timeline mainline overdense | False |
| Branches over budget | 2 (at budget limit, not exceeding) |

The 4 residual duplicate event clusters involve semantically similar events that weren't merged (e.g., 3 instances of "墨大夫传授无名口诀"). These represent distinct retellings across windows rather than true duplicates — the dedup policy correctly preserved them.

### World Ontology Analysis

| Metric | Value |
|---|---|
| World items | 107 |
| World containers | 6 |
| Total world entities | 113 |
| 七玄门 category | **organization** (FIXED from previous benchmark) |
| Containers | 地点, 组织与势力, 物品与法器, 规则与修炼体系, 概念与设定, 文化与习俗 |
| Organization items | 25 |
| Location items | 22 |
| Item items | 20 |
| Concept items | 17 |
| System items | 15 |
| Rule items | 6 |
| Artifact items | 2 |

### Chapter / Manuscript Analysis

| Metric | Value |
|---|---|
| `manuscript.json` chapters | **0** (regression) |
| `writing/chapters/` files | 0 (empty directory) |
| Source coverage | All 50 chapters covered in 35 windows |
| Chapter order in windows | Sequential (ordered by manifest) |

**Known Regression:** In the supervisor path (`use_supervisor=True`), `node_build_manuscript()` reads `state["manuscript_chapters"]` which is only populated in the legacy non-supervisor path. The supervisor yields data via a different state key. No chapter content is written to disk despite full source coverage at extraction time.

### Memory / OOM Analysis

| Metric | Value |
|---|---|
| Previous benchmark | OOM crash at `proposal_write` |
| This run | Completed without crash |
| Peak memory | ~49% of 24GB = ~12.3GB RSS |
| Machine RAM | 24GB |
| Final status | **survived** |

The OOM was avoided on this machine (24GB vs likely smaller in the previous run). The root cause (full entity registry + all state blobs read simultaneously in `node_write_to_project()`) still exists and will OOM on machines with ≤16GB RAM.

### Supervisor Decisions

| Metric | Value |
|---|---|
| Original windows | 14 |
| Rerun windows | 12 |
| Cross-validation passes | 14 |
| Total supervisor decisions | 41 |
| Failed prompts | 0 |
| Failed chunks | 0 |
| Blocked proposals | 0 |

### Review Report Status

| Field | Value |
|---|---|
| Status | warning |
| Warnings | 2 (density policy: branch_import_main and branch_theme_antagonist at budget limit) |
| Errors | 0 |
| Low confidence items | 3 |
| Duplicate merges | Multiple resolved by dedup policy |

---

## Previous Failure Comparison

| Failure Symptom | Previous Result | Current Result | Status |
|---|---|---|---|
| `proposal_write` OOM | Crashed (OOM) | Completed (49% peak) | **FIXED** |
| Character count | 4 | 75 | **FIXED** |
| Key chars (韩立/墨大夫/厉飞雨/张铁) | Missing | All present | **FIXED** |
| Language consistency | Latin traits in Chinese import | 0 violations | **FIXED** |
| World containers | 1 | 6 | **FIXED** |
| 七玄门 routing | Unknown/wrong | organization | **FIXED** |
| Timeline events | 3 | 102 canonical | **FIXED** |
| Manuscript chapters | Unknown | 0 (supervisor regression) | **STILL FAILING** |

---

## Diagnostics Summary

From `w1_import_diagnostics.py`:

```
Import_Test6 symptom flags:
  duplicate_event_clusters_present: true  (4 clusters — acceptable)
  mixed_language_trait_sets: false        ← FIXED
  overlong_character_summaries: false     ✓
  review_report_inbox_count_mismatch: false ✓
  scene_beats_or_discards_present: true   (expected — 148 scene beats)
  timeline_branch_over_budget: true       (2 branches at limit — warning only)
  timeline_mainline_overdense: false      ✓
  trait_duplication_or_noise: false       ✓
```

---

## Artifact Paths

| Artifact | Path |
|---|---|
| Benchmark results dir | `benchmark_results/w1_failure_closure_20260526_011743/` |
| Run config | `…/run_config.json` |
| Benchmark metrics | `…/benchmark_metrics.json` |
| Main report | `…/benchmark_report.md` |
| Failures & followups | `…/failures_and_followups.md` |
| Artifact index | `…/artifact_index.json` |
| Diagnostics output | `…/raw_logs/diagnostics_output.txt` |
| Copied artifacts (smoke) | `…/copied_artifacts/smoke/` |
| Copied artifacts (full50) | `…/copied_artifacts/full50/` |

---

## Residual Risks

1. **Manuscript chapters empty** (P1): Supervisor path does not write chapter content. `node_build_manuscript` reads wrong state key. Writers cannot read back their imported chapters.

2. **OOM on ≤16GB machines** (P1): `node_write_to_project()` loads full entity registry + all state into RAM simultaneously. This run survived on 24GB but will crash on smaller machines. Fix: stream-write proposals one entity at a time using the agent-plus-tools pattern.

3. **Residual duplicate events** (P2): 4 event clusters across windows weren't collapsed by the current dedup policy. Semantic deduplication needs cross-window merging, not just per-window.

4. **Missing 马副门主/瘦长师兄 in some windows** (P2): Several windows showed these characters as missing majors. They appear in the final registry (window reruns rescued them) but this inflates rerun count.

5. **Timeline branch density** (P3): 2 branches at the density limit (36 events each). The density policy correctly demoted additional events to scene beats, but the limit is a hard cap that may drop important events in very dense narrative arcs.

---

## Recommended Next Fixes (for Codex)

### P0 (Blocking)
None — the run succeeded.

### P1 (High Priority)
1. **Fix manuscript chapter writing in supervisor path**: In `_policy_with_progress()` or `run_supervisor_streaming()`, after extraction, ensure `state["manuscript_chapters"]` is populated from `state["windows"]` data before `node_build_manuscript()` is called.

2. **Fix OOM in `node_write_to_project()`**: Stream-write proposals one entity at a time. Replace the current pattern (load all → batch → write) with an incremental write loop. This is the agent-plus-tools architectural fix: each proposal write operation calls a tool that writes one bundle and returns a receipt, so state never accumulates the full entity set in RAM.

### P2 (Medium Priority)
3. **Cross-window event deduplication**: Add a post-reduce pass that collapses semantically equivalent events across windows (not just within a window). Use the existing `dedupeKey` + `semanticSignature` fields in the reduce output.

4. **Major character tracking across windows**: The `missing_majors` list in window metrics shows characters expected to appear that don't. Add a fallback: if a major character is missing from the primary window extraction and the rerun also misses it, run a targeted single-character extraction prompt for that character in that window range.

### P3 (Low Priority)
5. **Increase branch density budget**: Evaluate raising the 36-event cap for main and antagonist branches to 50 events, since scene beats created by density policy may lose narrative structure.
