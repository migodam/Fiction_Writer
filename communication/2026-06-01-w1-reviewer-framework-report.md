# W1 Reviewer Framework — Delivery Report

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Owner:** Reviewer Framework  

---

## Summary

Designed and implemented the W1 Reviewer Framework: a modular, zero-cost, deterministic quality-review layer for the W1 Import pipeline. Three reviewers (Quality, Fact, Consistency) share a unified `ReviewReport` schema and are callable by the Orchestrator post-import. No LLM calls, no live API, no full source text reads.

---

## Changed Files

### New: `sidecar/supervisor/reviewers/`

| File | Description |
|---|---|
| `__init__.py` | Package entry point; exports `QualityReviewer`, `FactReviewer`, `ConsistencyReviewer`, `BaseReviewer`, all 5 schema types |
| `schemas.py` | TypedDicts: `ReviewFinding`, `RepairAction`, `OrchestratorRequest`, `ZeroCostLedger`, `ReviewReport` |
| `base.py` | `BaseReviewer` ABC with `_finding`, `_repair`, `_orch_req`, `_build_report`, `_zero_ledger` helpers |
| `quality_reviewer.py` | 11 deterministic checks on proposals/registry/manuscript |
| `fact_reviewer.py` | 3 evidence-card-only checks with Jaccard similarity mismatch detection |
| `consistency_reviewer.py` | 4 cross-import continuity checks against `project_structure_digest` |

### New: `tests/`

| File | Tests | Result |
|---|---|---|
| `test_w1_reviewers_quality.py` | 7 | 7/7 PASS |
| `test_w1_reviewers_fact.py` | 5 | 5/5 PASS |
| `test_w1_reviewers_consistency.py` | 5 | 5/5 PASS |

### Modified: `sidecar/models/state.py`

Added `reviewer_reports: List[dict]` field to `ImportSupervisorState` (after `judge_artifact`, line 1159). Uses `List[dict]` to avoid circular import with the reviewers package.

---

## Schema

```
ReviewReport {
  reviewer:              "quality" | "fact" | "consistency"
  verdict:               "pass" | "warn" | "needs_repair" | "needs_orchestrator_rerun"
  severity:              "low" | "medium" | "high"   # max across all findings
  findings:              ReviewFinding[]
  local_repair_actions:  RepairAction[]
  orchestrator_requests: OrchestratorRequest[]
  token_cost_ledger:     ZeroCostLedger
}

ReviewFinding {
  finding_id:   str   # f"{check_name}_{entity_id}"
  check_name:   str
  description:  str
  severity:     "low" | "medium" | "high"
  entity_refs:  str[]
  evidence_refs: str[]
}

RepairAction {
  action_type:        "merge_duplicate" | "reclassify" | "add_evidence_ref"
  target_entity_ids:  str[]
  description:        str
  deterministic:      bool
}

OrchestratorRequest {
  request_type:    "rerun_window" | "reclassify_entity" | "merge_entity"
  theme:           str   # matches ThematicRerunRequest.theme vocab
  target_windows:  str[]
  expected_repair: str
  priority:        "low" | "medium" | "high"
}
```

**Verdict escalation:** no findings → `pass`; only low/medium → `warn`; any high + orch_req → `needs_orchestrator_rerun`; any high without orch_req → `needs_repair`.

---

## Checks Implemented

### QualityReviewer (11 checks)

| check_name | Severity | Trigger |
|---|---|---|
| `timeline_stream_of_consciousness` | high | >50% event proposals are scene_beat |
| `mainline_share_too_high` | medium | >80% canonical events on main branch |
| `branch_over_budget` | medium | Any non-main branch >10 canonical events |
| `world_empty_container` | medium | World proposal with empty description |
| `world_wrong_classification` | high | World proposal with category=character |
| `world_module_pollution` | medium | Name collision between char and world proposals |
| `character_duplicate_name` | high | Two char proposals share same normalized name |
| `character_missing_major` | high | protagonist_list member not in entity_registry |
| `character_thin_card` | low | summary < 20 chars |
| `relationship_no_evidence` | medium | Relationship proposal with no evidence field |
| `manuscript_empty` | medium | manuscript_chapters absent or empty |

### FactReviewer (3 checks)

| check_name | Severity | Trigger |
|---|---|---|
| `evidence_entity_mismatch` | high | Jaccard similarity < threshold (default 0.05) between entity desc and evidence snippet |
| `evidence_missing` | medium | Character/event proposal with no evidence reference |
| `low_confidence_entity` | low | confidence < 0.65 |

Config: `max_snippets=5`, `max_total_tokens=1000`, `mismatch_threshold=0.05`. LLM adapter stub (`_llm_mismatch_check`) returns `None` by default.

### ConsistencyReviewer (4 checks)

| check_name | Severity | Trigger |
|---|---|---|
| `character_duplicate_across_imports` | high | New character name matches existing project character |
| `timeline_branch_continuity` | medium | All new branch IDs are orphaned (no overlap with existing branches) |
| `world_item_conflict` | high | Same world item name with different category in existing vs new |
| `relationship_redundant` | high | Same source→target pair already exists in project |

Gracefully passes if `project_structure_digest` is None or empty.

---

## Tests Run

```
tests/test_w1_reviewers_quality.py    7/7 PASS
tests/test_w1_reviewers_fact.py       5/5 PASS
tests/test_w1_reviewers_consistency.py 5/5 PASS
tests/test_w1_quality_rubric.py       19/19 PASS (regression — no breakage)

Total: 36/36 PASS | Runtime: <0.1s | Live API calls: 0
```

---

## Risks

| Risk | Status |
|---|---|
| `quality.py` circular import | Not triggered; reviewers do not import from `quality.py`. New checks are independent implementations. |
| `project_structure_digest` schema variability | Handled: ConsistencyReviewer reads both dict and flat formats; gracefully passes on None/empty. |
| CJK tokenization for FactReviewer | Handled: character-level bigrams for CJK text, no external deps. |
| Branch continuity ambiguity | Handled: only flags when ALL new branches are fully orphaned from existing branches. |

---

## Deferred Items

- **Wiring into supervisor orchestrator**: reviewers are not yet called from `supervisor/tools.py:qa_review()` or `supervisor/policy.py`. This is the next integration task.
- **LLM adapter for FactReviewer**: `_llm_mismatch_check()` is a stub returning `None`. Activate by subclassing `FactReviewer` and overriding.
- **RAG snippet fetch**: evidence cards must be pre-populated; reviewer does not fetch snippets from source.
- **Reviewer composition pipeline**: running all three in sequence and merging reports.
- **Repair action auto-apply**: `RepairAction.deterministic=True` actions are flagged but not yet executed automatically.
