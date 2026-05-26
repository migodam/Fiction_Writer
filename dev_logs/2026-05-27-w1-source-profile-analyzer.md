# W1 SourceProfileAnalyzer — Deterministic Foundation

**Date**: 2026-05-27
**Branch**: codex/w1-orchestrated-import-quality
**Files changed**: `sidecar/models/state.py`, `tests/test_w1_source_profile.py`, `dev_docs/W1_IMPORT_COMPILER.md`

---

## What Was Added

### `SourceProfile` TypedDict (`state.py`, after `ImportGranularityProfile`)

A new TypedDict capturing deterministic manuscript metadata:

| Field | Type | Notes |
|-------|------|-------|
| `chapter_count` | int | `len(chunks)` |
| `source_language` | str | Passed through from caller |
| `avg_chars_per_chapter` | float | Rounded to 1 decimal |
| `total_chars` | int | Sum of all chunk text lengths |
| `estimated_source_type` | Literal | Classification result |
| `dialogue_density_hint` | Literal | Heuristic; advisory only |
| `named_entity_density_hint` | Literal | Based on `entity_mentions` field |
| `recommended_granularity_profile` | Literal | Same value as estimated_source_type |
| `confidence` | float | 0.5–0.95 depending on case strength |
| `evidence` | List[str] | 2–3 strings explaining decisions |

### `analyze_source_profile()` function (`state.py`, after `plan_orchestrator_targets`)

Deterministic profiler. No LLM, no network calls.

**Classification rules** (mirrors `select_granularity_profile()` thresholds):

| Condition | Result | Confidence |
|-----------|--------|------------|
| `chapter_count == 0` | fine_short_story | 0.5 (empty input) |
| `chapter_count ≤ 15` | fine_short_story | 0.90 |
| `chapter_count > 30` AND CJK lang | coarse_webnovel | 0.95 |
| `chapter_count > 30` AND non-CJK | balanced_novel | 0.85 |
| `16 ≤ chapter_count ≤ 30` | balanced_novel | 0.80 |

CJK languages: `zh`, `ko`, `ja` (same `_WEBNOVEL_LANGUAGES` frozenset).

**Intentional deviation from `select_granularity_profile()`**: the `fast` profile override
is omitted. That override is an execution policy decision, not a source characteristic. The
profiler describes the source as-is.

**Chunk text fallback chain**: `content` → `manuscript_content` → `raw_content` → `""`

**Dialogue density heuristic** — conservative advisory:
- Counts: `「`, `」`, `"`, `"`, `"`
- Ratio > 0.05 → high; > 0.02 → medium; else → low
- Not a precise structural claim; callers must treat as advisory.

**Named entity density**:
- Missing `entity_mentions` key → treated as empty list (no error)
- avg > 8 → dense; ≥ 3 → moderate; else → sparse

### `source_profile: SourceProfile` field on `ImportSupervisorState`

Type surface only. Not wired into policy.py or tools.py. Allows future callers to
write `state["source_profile"] = analyze_source_profile(...)` without a type error.

---

## Test Results

```
tests/test_w1_source_profile.py: 23 passed in 0.02s
tests/test_w1_granularity.py + tests/test_w1_extraction_variants.py: 69 passed in 0.27s
```

---

## Deferred

Integration into `policy.py` (calling `analyze_source_profile` before the supervisor loop
starts) is explicitly deferred. Codex will wire it after review.
