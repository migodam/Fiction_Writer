# W1 Manuscript Supervisor Fix — Smoke Validation Report

**Benchmark ID:** `w1_manuscript_smoke_20260526_091106`  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Required commit:** `5db686f fix: build manuscript from chunks in W1 supervisor path`  
**Model:** `deepseek-v4-pro` via DeepSeek API  
**Prompt profile:** `deep`  
**Date:** 2026-05-26  
**Fixture:** 凡人修仙传_前10章.txt (10 chapters, ~20,951 chars)

---

## Executive Summary

This benchmark validates the Codex fix for the W1 supervisor manuscript regression. The previous benchmark (`w1_failure_closure_20260526_011743`) confirmed that `manuscript.json` was empty (`chapters: []`) in the supervisor path. Codex added a deterministic raw-chunk fallback in `node_build_manuscript()`.

**RESULT: PASS** — All acceptance criteria met.

| Criterion | Result |
|---|---|
| `manuscript.json` exists | **YES** |
| Chapter count = 10 | **10** |
| All titles non-empty | **YES** |
| All `manuscript_content` non-empty | **YES** |
| `orderIndex` = 0–9 sequential | **YES** |
| `system/inbox.json` exists | **YES** |
| Judge score ≥ previous smoke (1.0) | **1.0** |
| Language violations = 0 | **0** |

---

## Run Details

Two runs were executed:

### Run 1 (Failed — old sidecar)

The first run used sidecar PID 97078, which started at 1:19 AM — before the fix commit was made at 9:04 AM. The old code was loaded, and `manuscript.json` was empty.

### Run 2 (Valid — with fix)

After restarting the sidecar (PID 55934, started 9:27 AM with commit `5db686f` loaded), a fresh project directory was created and a new run was executed.

| Field | Value |
|---|---|
| Session ID | `374ab212-323b-46cf-85dc-44d1c6fef8ab` |
| Import run ID | `sup_27488a4242` |
| Project path | `/home/narrative_ide/w1_ms_smoke_20260526_092758/` |
| Source | `凡人修仙传_前10章.txt` (20,951 chars, 10 chapters) |
| Start time | 09:27 UTC+8 |
| End time | 09:57 UTC+8 |
| Elapsed | ~30 minutes |
| Windows | 6 (3 original + 2 reruns + 1 cross-validate) |
| Supervisor decisions | 9 total |

---

## Acceptance Criteria Results

### manuscript.json

```
chapter count:  10
titles:         第一章 ... 第十章 (all non-empty)
content:        2499 / 2026 / 1700 / 2421 / 2262 / 2044 / 1943 / 2034 / 2034 / 1988 chars
orderIndex:     0 1 2 3 4 5 6 7 8 9 (sequential)
```

All 10 chapters written with complete source text preserved. No truncation.

### Judge

| Field | Value |
|---|---|
| Score | **1.0** |
| Passed | True |
| Failed gates | None |
| Thematic reruns | None |
| Character count | 40 |
| Canonical events | 26 |
| World count | 74 |
| Mixed language | False |

### Language

- 40 characters analyzed
- 0 Latin violations in name, aliases, summary, or personality_traits

### Inbox

- Written: Yes
- Entity types: character(40), timeline_event(22), world_item(37), world_container(7), relationship(24), character_tag(3), timeline_branch(5), chapter(10), world_settings(1)

---

## Fix Verification

The fix adds a deterministic fallback in `node_build_manuscript()` for the supervisor path:

```python
extractions = state.get("chunk_extractions", [])
if not extractions:
    return {"manuscript_chapters": _build_from_chunks(chunks), "progress": 0.88}
```

When `chunk_extractions` is empty (supervisor path), it falls back to `state["chunks"]` — the raw parsed chapter list — and builds ordered manuscript entries from that. The `_build_from_chunks()` helper sorts by `chapter_hint` to preserve source order.

The output confirms this works: chapters are written in order (第一章 → 第十章) with full source text preserved.

---

## Test Coverage

The following tests pass on `5db686f`:

```
tests/test_w1_import_compiler.py::test_build_manuscript_orders_chapters_by_source_chunk_id
tests/test_w1_import_compiler.py::test_build_manuscript_supervisor_falls_back_to_chunks_without_extractions
tests/test_w1_import_compiler.py::test_node_write_to_project_manuscript_still_written
tests/test_w1_import_compiler.py  (33 total)
tests/test_w1_import_diagnostics.py
tests/test_w1_supervisor_policy.py  (72 total)
tests/test_w1_supervisor_tools.py
tests/test_w1_prompt_windows.py
```

Total: 105 tests pass, 0 failures.

---

## Residual Items

The previous `failures_and_followups.md` listed 4 remaining risks (R1-R4). The manuscript fix (R0, now resolved) was the only blocking item. The other items remain:

| Risk | Status |
|---|---|
| OOM on <24GB machines (R1) | Still open — P1 for Codex |
| Residual duplicate events (R2) | Still open — P2 |
| Missing major characters in some windows (R3) | Still open — P2 |
| Branch density at hard limit (R4) | Still open — P3 |

For the 50-chapter production run, R1 (OOM) is the next P1 to address.
