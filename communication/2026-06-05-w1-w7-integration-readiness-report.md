# W1-W7 Integration Readiness Report — 2026-06-05

## Executive Summary

Codex completed the W1-W7 integration gap closure that blocked the W7 ten-chapter experiment.

The two missing integration pieces are now fixed:

| Gap | Previous State | Current State | Evidence |
|---|---|---|---|
| W2 reviewer/organizer fixes | Dirty, uncommitted on integration branch | Committed as `4e65643` | W2 reviewer/organizer pytest `107 passed` |
| W1 orchestrator density work | Only existed on `codex/w1-ai-import-orchestrator` | Cherry-picked as `b8d3b1c` | W1 policy/manifest pytest `22 passed` |

The W7 small import experiment is now unblocked from an integration-gate perspective. It should still be run as a controlled 10-chapter smoke only, not full50.

## Work Completed

### W1 — AI Import Prompt + Orchestrator Quality

Integrated commit: `b8d3b1c`

Changes now present on the integration branch:

| Area | Result |
|---|---|
| Sparse event density | `sparse_turning_points` now dispatches to its own sparse event prompt, not the arc prompt |
| Timeline-worthiness gate | Canonical events require `state_change` and `why_timeline_worthy` |
| Logistics filtering | Travel, supply-gathering, routine training, and atmospheric dialogue are explicitly scene beats unless they cause irreversible state change |
| Policy artifact | `prompt_policy_decision.json` includes chosen density, source signals, topology signals, and reviewer feedback |
| Manifest revision validation | `validate_manifest_revision()` rejects unknown fields, invalid revision types/actions, and empty `dedupeKey` |

### W2 — Reviewer + Organizer + Manifest Repair

Committed as: `4e65643`

Changes now committed:

| Area | Result |
|---|---|
| Quality Reviewer | Detects repeated age phrases such as `23岁` / `十岁` and emits deterministic repair operations |
| Quality Reviewer | Detects duplicate manuscript chapters by title and fallback chapter number |
| Fact Reviewer | Confirmed snippet-only behavior; does not read whole novel chunks |
| Consistency Reviewer | Emits `manifest_revision_diffs` for protected existing character facts |
| Organizer | Adds acceptance-matrix coverage for identity/rank exclusion, person-name exclusion, and ambiguous `堂` routing |

### W3-W6 Regression Status

| Workstream | Verification |
|---|---|
| W3 timeline sync + label layout | `timeline_sync_roundtrip.spec.ts` passed 11/11 |
| W4 global undo | `global_undo.spec.ts` passed 4/4 |
| W5 hierarchical tags | `tag_hierarchy_drag_drop.spec.ts` passed 5/5 |
| W6 sidebar/relationship graph linkage | `graph_sidebar_linkage.spec.ts` passed 3/3 |

## Test Results

### Python

| Command | Result |
|---|---|
| `py_compile` touched W1/W2 Python files | PASS |
| `pytest tests/test_w1_prompt_policy_selection.py tests/test_w1_manifest_revision_schema.py -q` | 22 passed |
| `pytest tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_import_compiler.py -q` | 107 passed |

### Frontend

| Command | Result |
|---|---|
| `npm run ui:build` | PASS |
| `timeline_sync_roundtrip.spec.ts` | 11 passed |
| `global_undo.spec.ts` | 4 passed |
| `tag_hierarchy_drag_drop.spec.ts` | 5 passed |
| `graph_sidebar_linkage.spec.ts` | 3 passed |

## W7 Ten-Chapter Experiment Readiness

W7 can start after confirming the final git status has no unexpected staged files. Recommended W7 constraints:

| Constraint | Required Behavior |
|---|---|
| Scope | First 10 chapters only |
| Profile | `deep` is acceptable for quality validation |
| Cost control | Stop immediately on HTTP 402 / insufficient balance |
| No full50 | Do not run full50 in this gate |
| Manual validation focus | Manuscript non-empty, chapter order, duplicate chapters, timeline branch/fork/merge preservation, reviewer repair proposals, world taxonomy placement |

## Remaining Notes

| Item | Status |
|---|---|
| `docs/superpowers/` | Left untracked intentionally; not part of this integration gate |
| `communication/2026-06-04-w1-ai-import-orchestrator-delivery-report.md` | Added as supporting W1 delivery evidence |
| Live import quality | Not certified by this gate; W7 smoke is still required |

## Final Recommendation

Proceed to W7 ten-chapter smoke once the final commit containing this report is created and `git status --short --branch` shows only intentionally untracked non-workstream files, preferably none.
