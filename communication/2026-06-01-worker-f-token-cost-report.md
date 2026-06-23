# Worker F — Token / Cost UX — Delivery Report

**Date:** 2026-06-01
**Branch:** codex/w1-orchestrated-import-quality
**Worker:** Worker F (Token and Cost UX)

## Summary

Implemented end-to-end token/cost ledger visibility for the W1 import workflow. Users can now see live input/output token counts and estimated USD cost during and after any import run.

## What Was Implemented

### Sidecar (Python)

**`sidecar/workflows/w1_run_events.py`**
- Added per-session `_token_ledger` in-memory storage
- Added `_DEFAULT_PRICE_TABLE` (8 model entries: deepseek-chat/v3/r1, gpt-4o/4o-mini/4.1, claude-3-5/3-7)
- Added `_SORTED_PRICE_TABLE` pre-computed at module load (longest-match-wins for model lookup)
- Added `add_token_usage(session_id, input_tokens, output_tokens)` — accumulates actual usage
- Added `session_token_ledger(session_id, model, estimated_input_tokens)` — returns ledger dict for UI; no secrets
- Updated `ensure_session()` + `clear_session()` to manage ledger lifecycle
- Logs to event feed when cost is unavailable for a model

**`sidecar/workflows/w1_import.py`**
- Added `_extract_llm_usage(response)` — dual-path extraction (LangChain usage_metadata + OpenAI response_metadata fallback)
- Added `session_id: str = ""` param to `_invoke_json_prompt` + wired `add_token_usage` after every successful `ainvoke`
- Added `session_id: str = ""` param to `_repair_json_response` + wired usage extraction
- Threaded `_session_id` through: `node_process_chunks` (5+2 call sites), `node_synthesize_relationships`, `node_classify_character_tags`, `node_infer_world_settings`
- Threaded `session_id` through `_run_cross_validation_for_window` (2 call sites in node_process_chunks)
- Instrumented 3 bare `ainvoke` calls in `_legacy_node_process_chunks`
- Moved `add_token_usage` import to module level

**`sidecar/routers/workflows.py`**
- Added `token_ledger: dict = {}` to `W1StatusResponse` Pydantic model
- Populated in `w1_status()`: aggregates `estimated_input_tokens` from window_metrics, extracts model from session config, returns full ledger via `session_token_ledger()`

### Frontend (TypeScript/React)

**`src/ui-react/services/electronApi.ts`**
- Added `W1TokenLedger` interface (5 required + 3 optional fields)
- Added `token_ledger?: W1TokenLedger` to `W1StatusResult`

**`src/ui-react/store.ts`**
- Added `w1TokenLedger: W1TokenLedger | null` state field
- Initialized/reset to `null` in 3 locations
- Mapped from `s.token_ledger ?? null` in status polling

**`src/ui-react/components/ImportWorkflow.tsx`**
- Added `formatTokens()` helper (M/k/raw formatting)
- Added `w1TokenLedger` selector
- Added Token/Cost card (`w1-token-cost-card`) rendered whenever `w1TokenLedger !== null` (persists through `done` state)
  - Input tokens: actual or estimated with "(est.)" label
  - Output tokens: actual only, hidden when 0
  - API calls count
  - Estimated cost or reason (hidden when neither available)
- Added 402 budget-exhausted banner (`w1-budget-exhausted-banner`, running/paused only)

## Tests

### Python unit tests (`tests/test_w1_token_ledger.py`)
- 9/9 pass (zero cost, no LLM calls)
- Covers: accumulation, cost calculation, unknown model, empty session noop, secret scan, clear/reset, gpt-4o-mini/gpt-4o disambiguation

### Playwright E2E (`tests/e2e/p1/import_token_cost.spec.ts`)
- 5/5 pass
- Covers: actual usage rendering, card persists on done, estimate fallback with "(est.)", 402 banner, absent when no ledger

### Existing tests
- `test_w1_import_compiler.py`: 52/52 pass (unchanged)
- `test_w1_quality_rubric.py` + `test_w1_v2_harness.py`: pass (unchanged)

## Remaining Risks

1. **Actual token counts depend on provider returning usage metadata.** DeepSeek must return `usage_metadata` or `response_metadata.token_usage` in its API responses. If the provider omits this (e.g., streaming mode), ledger shows 0 for actuals but estimates still surface.
2. **Price table not editable via UI** — this is a stretch goal requiring Lead coordination on `appSettingsService.ts` (already dirty on this branch).
3. **Legacy path (`_legacy_node_process_chunks`) instrumented but not well-tested** — no unit test exercises the legacy node directly. Coverage comes from integration.

## Manual Smoke Checklist

1. Open any project → click Workbench → click Import
2. Start an import with a .txt file
3. During running: Token/Cost card should appear showing estimated input tokens with "(est.)" label
4. After LLM calls: actual token counts should replace estimates
5. For deepseek-chat model: cost shows as `$X.XXXX`
6. For unknown model: cost field is hidden (not "cost unavailable")
7. On 402 error: red "Budget exhausted" banner appears above the console
8. On import completion: token/cost card remains visible showing final totals
9. Verify: no API key visible anywhere in the token/cost card
