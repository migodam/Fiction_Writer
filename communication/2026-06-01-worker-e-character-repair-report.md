# Worker E — Character Dedupe and Executable Reviewer Repair

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`

---

## Summary

Reviewer repair packages now produce **frontend-executable proposals**. Three root-cause bugs in `_collect_repair_proposals()` were fixed (wrong field names, wrong op key, hardcoded `world_item` entity type). `RepairAction` was extended with an optional `proposed_operations` field. `QualityReviewer` was updated to populate it for duplicate-name and repeated-phrase checks.

---

## Changed Files

| File | Change |
|------|--------|
| `sidecar/supervisor/reviewers/schemas.py` | Split `RepairAction` into `_RepairActionRequired` + `RepairAction(total=False)` to add optional `proposed_operations: List[dict]` |
| `sidecar/supervisor/reviewers/base.py` | Extended `_repair()` helper to accept `proposed_operations` kwarg |
| `sidecar/supervisor/reviewers/quality_reviewer.py` | Added `_check_character_repeated_phrases()` check; updated `_check_character_duplicate_name()` to emit `proposed_operations` with `op: 'delete'` for dup IDs |
| `sidecar/supervisor/tools.py` | Fixed `_collect_repair_proposals()`: correct field names, `proposedOperations` key, entity type inference, skip advisory-only actions |
| `tests/test_w1_reviewers_quality.py` | Added 2 new unit tests |
| `tests/e2e/p1/workbench_reviewer_repair_package.spec.ts` | Added tests 9 and 10 |

---

## Root Causes Fixed

| Bug | Before | After |
|-----|--------|-------|
| Wrong field key | `action.get("rationale")` | `action.get("description")` |
| Wrong op schema key | `"operations"` | `"proposedOperations"` |
| Wrong entity type | hardcoded `"world_item"` | inferred from `ops[0]["entityType"]` |
| Reads nonexistent field | `action.get("entity_id")` | `action.get("target_entity_ids", ["unk"])[0]` |
| Silent no-ops in inbox | actions without ops still produced proposals | skip if `proposed_operations` is absent |

---

## New Reviewer Check: `character_repeated_phrase`

Uses `re.search(r"(.{5,15}).*\1", text, re.DOTALL)` to detect any 5–15 char phrase that appears more than once in a character's `summary` or `background`. Generates an `op: 'update'` repair with deduplicated text. Zero-cost: pure regex, no model calls.

Example: `五言`'s summary repeating `十三岁锦衣少年` → finding fires, repair removes second occurrence.

## Updated Check: `character_duplicate_name`

Now emits `proposed_operations: [{"op": "delete", "entityType": "character", "entityId": dup_id}]` for each non-primary duplicate ID. Marked `deterministic: False` because delete may be blocked if the duplicate is referenced by a relationship proposal in the same batch.

---

## Tests

### Unit Tests (sidecar)

```
tests/test_w1_reviewers_quality.py — 9/9 PASS
```

| # | Test | Result |
|---|------|--------|
| 1 | `test_quality_catches_50_trivial_events` | PASS |
| 2 | `test_quality_catches_single_root_branch` | PASS |
| 3 | `test_quality_catches_empty_world_containers` | PASS |
| 4 | `test_quality_catches_relationship_missing_evidence` | PASS |
| 5 | `test_quality_catches_character_missing_major` | PASS |
| 6 | `test_quality_pass_on_clean_state` | PASS |
| 7 | `test_quality_token_ledger_is_zero_cost` | PASS |
| 8 | `test_quality_catches_character_repeated_phrase` *(new)* | PASS |
| 9 | `test_quality_duplicate_name_repair_has_executable_ops` *(new)* | PASS |

### Build Verification

```
npm run ui:build   — 0 TS errors, 1772 modules, clean
```

### New E2E Tests

```
tests/e2e/p1/workbench_reviewer_repair_package.spec.ts — tests 9 and 10 added
```

| # | Test | Coverage |
|---|------|----------|
| 9 | `accepting op:update repair package updates existing character field` | Inject character in state + `op: 'update'` repair proposal → accept → verify summary patched |
| 10 | `repair package with unsupported op is blocked with precise reason` | Inject `op: 'link'` repair → accept → verify blocked reason contains "not supported" |

*(Require dev server on :3000 to execute)*

---

## Interface Contract for Sidecar Owners

For reviewer repair proposals to be executable in the Workbench Inbox, each `RepairAction` emitted by a reviewer must include:

```python
RepairAction(
    action_type="...",
    target_entity_ids=["entity_id"],
    description="...",
    deterministic=True,                  # False if delete/merge might be blocked
    proposed_operations=[                # Required for inbox write
        {"op": "update"|"delete"|"create", "entityType": "character", "entityId": "...", "fields": {...}}
    ],
)
```

Actions without `proposed_operations` are advisory-only and not written to the inbox.

---

## Risks and Deferred Items

| Item | Risk | Status |
|------|------|--------|
| `op: 'delete'` for duplicate chars blocked if dup has relationships | Medium — relationship proposals in same W1 batch may reference the dup | Mitigated: `deterministic: False` marks package amber; user sees retry button |
| Repeated-phrase check uses greedy `{5,15}` — may over-match in dense Chinese prose | Low — false positives produce safe `op: 'update'` with only minor edits | Acceptable |
| E2E tests 9 & 10 require running dev server | Low | Documented; CI can run against `npm run ui:dev` |
