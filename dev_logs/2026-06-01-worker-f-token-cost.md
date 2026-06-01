# Dev Log — Worker F — Token / Cost UX — 2026-06-01

## Changes Made

### sidecar/workflows/w1_run_events.py
- Added _token_ledger dict, _DEFAULT_PRICE_TABLE, _SORTED_PRICE_TABLE
- Updated ensure_session, clear_session for ledger lifecycle
- Added add_token_usage, _cost_for_model, session_token_ledger

### sidecar/workflows/w1_import.py
- Added _extract_llm_usage helper
- Added session_id param to _invoke_json_prompt, _repair_json_response, _run_cross_validation_for_window
- Threaded session_id through: node_process_chunks (7 sites), node_synthesize_relationships, node_classify_character_tags, node_infer_world_settings
- Instrumented _legacy_node_process_chunks (3 bare ainvoke calls)
- Moved add_token_usage import to module level

### sidecar/routers/workflows.py
- Added token_ledger: dict = {} to W1StatusResponse
- Populated token_ledger in w1_status() from session_token_ledger()

### src/ui-react/services/electronApi.ts
- Added W1TokenLedger interface
- Added token_ledger field to W1StatusResult

### src/ui-react/store.ts
- Added w1TokenLedger state field + 3 reset locations + polling mapping

### src/ui-react/components/ImportWorkflow.tsx
- Added formatTokens helper
- Added Token/Cost card (w1-token-cost-card)
- Added budget-exhausted banner (w1-budget-exhausted-banner)

## Tests Executed

| Test | Result |
|---|---|
| sidecar/.venv/bin/python -m pytest tests/test_w1_token_ledger.py -v | 9/9 PASS |
| sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q | 52/52 PASS |
| sidecar/.venv/bin/python -m pytest tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py -q | PASS |
| npm run ui:build | PASS (0 errors) |
| npm run ui:lint | PASS (0 errors) |
| npx playwright test import_token_cost.spec.ts | 5/5 PASS |

## Commits

- feat: add token/cost ledger to w1_run_events
- fix: use longest-match for model price lookup in _cost_for_model
- refactor: pre-sort price table at module load; log cost-unavailable to event feed
- feat: extract LLM usage after each ainvoke and accumulate in session token ledger
- feat: thread session_id through _run_cross_validation_for_window for full token metering
- fix: meter legacy ainvoke paths (_repair_json_response and _legacy_node_process_chunks)
- feat: include token_ledger in W1StatusResponse (w1_status endpoint)
- feat: add W1TokenLedger type, w1TokenLedger store state, and Token/Cost card UI
- fix: show token/cost card after import done; fix premature cost-unavailable display
- test: add Playwright spec for token/cost card (5 scenarios)
