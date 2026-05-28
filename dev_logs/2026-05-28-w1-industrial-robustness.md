# W1 Industrial Robustness — Dev Log
**Date:** 2026-05-28
**Branch:** codex/w1-orchestrated-import-quality

## Summary

Four targeted improvements across backend and frontend, zero new API calls, all existing tests pass.

---

## Phase A: Backend token/context safety

### Digest over-reservation fix (`w1_import.py:_build_supervised_prompt_windows`)

**Root cause:** `_build_supervised_prompt_windows` estimated `digest_tokens` using a 24000-token clip (`_DIGEST_RESERVE_TOKENS`). But `extract_window` never uses `window["text"]` directly — it reassembles from raw chunks and prepends `_rolling_window_context`, which clips the digest to **8000 chars** (≈4000 tokens). The window split decision was reserving ~20000 tokens of budget that never reached the actual prompt.

**Fix:** Changed `digest_tokens = _estimate_tokens(digest[:8000_chars])` to match what `_rolling_window_context` actually sends. `digest_content` (the full token-clipped version) is still built for the window header fallback path (when `window_chunks` is empty).

**Impact:** `source_budget = max(input_window_budget - schema_reserve - digest_tokens - validation_tokens, 1000)` is now ~20k tokens larger for a medium-length novel digest. This allows fewer, larger windows per batch without changing actual prompt content or increasing API calls.

### Profile-aware `max_tokens` (`state.py`, `w1_import.py:_get_llm`)

Added `max_tokens_per_call` to `ImportProfileConfig` and all four `PROFILE_CONFIGS`:
- fast/balanced: 4096 (unchanged behavior)
- deep/custom: 5120 (allows richer per-window extraction output)

`_get_llm` now reads `profile_config.get("max_tokens_per_call", 4096)` instead of the hardcoded 4096.

**Not done:** max_tokens=8192 — requires provider-specific validation. Not set in this round.

### `token_budget_exhausted` in status (`routers/workflows.py`, `electronApi.ts`)

Added `token_budget_exhausted: bool` to `W1StatusResponse`. Derived from session errors matching `budget_exhausted|402|insufficient.?balance` or `converge_status == "budget_exhausted"`. Frontend (`W1StatusResult`) adds matching optional field.

---

## Phase B: Import observability summary

### `import_observability` in `node_review_import` (`w1_import.py`)

Added `import_observability` dict to `review_report` with 10 fields sourced entirely from existing state — no new LLM calls:

| Field | Source |
|-------|--------|
| `characters_extracted` | `entity_registry["characters"]` (skip_create excluded) |
| `events_extracted` | `entity_registry["events"]` |
| `world_items_extracted` | `entity_registry["world_detailed"]` |
| `relationships_extracted` | `state["relationships"]` |
| `manuscript_chapters_count` | `state["manuscript_chapters"]` |
| `manuscript_written` | bool of manuscript_chapters_count > 0 |
| `canonical_events_count` | `timeline_architecture["canonical_events"]` |
| `branch_count` | `state["timeline_branches"]` |
| `duplicate_count` | `timeline_architecture["discarded_duplicates"]` |
| `topology_warning_count` | `timeline_architecture["warnings"]` |

`proposal_write` updates `proposal_counts`, `safe_accept_ids`, `blocked_ids` on the same dict — it does NOT overwrite `import_observability` (separate key).

### Frontend (`electronApi.ts`, `ImportWorkflow.tsx`)

- Added `ImportObservabilitySummary` interface and `import_observability` field on `W1ImportReviewReport`
- `ImportWorkflow.tsx` done state: renders an observability grid (`data-testid="w1-import-observability"`) when `import_observability` is present

---

## Phase C: Frontend blocked-proposal UX fix

### Root cause (`projectService.ts:resolveProposal`)

When `applyProposalOperations` returns `blockedReason` (e.g., "Cannot create duplicate character X"), the code path at line 924-929 returned `project` with `proposals` unchanged. The proposal stayed in the inbox with no visual feedback. The user could click Accept indefinitely — same silent result each time.

### Fix

`resolveProposal` now annotates the blocked proposal with `lastBlockReason` and `lastBlockedAt` display fields, then replaces it in `proposals` via `.map(...)`. Proposal stays in inbox (existing `workbench_proposal_safety.spec.ts` test verifies this is correct behavior) but now shows a reason.

### `WorkbenchWorkspace.tsx` — both proposal card renderers

Both the inbox (`proposal-card-*`) and agent-proposals (`proposal-item-*`) card renderers now:
1. Show an amber reason banner (`data-testid="proposal-blocked-reason-{id}"`) when `proposal.lastBlockReason` is set
2. Disable the Accept button (`disabled={Boolean(proposal.lastBlockReason)}`) to prevent silent re-click

### `ImportWorkflow.tsx` — accept-safe-all feedback

`acceptSafeAll` now sets `acceptResult` state after the loop. An inline message (`data-testid="w1-accept-result"`) shows "N accepted. M proposals require manual review."

---

## Test results

**Python (168 → 176 passed):**
- `tests/test_w1_prompt_windows.py` — 4 new tests for digest budget fix and max_tokens_per_call
- `tests/test_w1_import_compiler.py` — 5 new tests for import_observability

**Playwright mocked (new tests in p1/):**
- `workbench_proposal_safety.spec.ts` — 2 new tests: blocked reason banner visible, accept button disabled
- `import_workflow.spec.ts` — 2 new tests: accept-safe-all result message, observability panel in done state

**Compile:** All 5 touched Python files compile clean. TypeScript build produces same 40 pre-existing missing-module errors (lucide-react/react-router-dom packages incomplete in environment) — zero new errors from our changes.

---

## Commits

```
feat(A): profile-aware max_tokens, fix digest over-reservation in supervisor windowing
feat(B): add import_observability to review_report and surface in import done UI
fix(C): show block reason on proposal card, disable accept after conflict, accept-safe-all summary
docs(D): dev_log and regression tests for W1 robustness phases A-C
```
