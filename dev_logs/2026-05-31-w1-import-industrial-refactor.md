# W1 Import Industrial Refactor — 2026-05-31

## Scope

This iteration advanced W1 Import from patch-level fixes toward product-grade, explainable import behavior:

- Prompt density is now an Orchestrator policy decision (`sparse_turning_points`, `arc_level`, `chapter_level`, `scene_level`) instead of a static prompt-only rule.
- `PromptPolicyPatch` gained bounded knobs for event density, topology fidelity, world-model scope, and timeline label granularity. Raw prompt text remains forbidden.
- Timeline labels now use deterministic candidate placement and hiding/tooltip fallback for dense views.
- Timeline sync warnings now classify derived/runtime fields separately from real schema problems.
- World Model import filters module-owned concepts such as relationship graphs and event timelines, adds localized Chinese taxonomy, and writes hierarchy-compatible `categoryPath` / `parentId`.
- Workbench Inbox supports package-level W1 import acceptance with transaction-style same-package dependency resolution and readable blocking edges.

## Files Changed

- Backend/import: `sidecar/models/state.py`, `sidecar/prompts/w1_prompts.py`, `sidecar/supervisor/planner.py`, `sidecar/supervisor/policy.py`, `sidecar/supervisor/prompt_policy.py`, `sidecar/supervisor/tools.py`, `sidecar/workflows/w1_import.py`
- Frontend/data: `src/ui-react/services/projectService.ts`, `src/ui-react/components/WorkbenchWorkspace.tsx`
- Timeline UI: `src/ui-react/components/TimelineWorkspace.tsx`, `src/ui-react/components/timeline/*`
- Tests: `tests/test_w1_planner_proposal.py`, `tests/test_w1_supervisor_policy.py`, `tests/test_w1_import_compiler.py`, `tests/e2e/p1/timeline_topology_import.spec.ts`, `tests/e2e/p1/workbench_import_package_accept.spec.ts`, `tests/timeline_layout_engine_check.ts`
- Docs/reporting: `dev_docs/W1_IMPORT_COMPILER.md`, `dev_docs/DATA_MODEL.md`, `communication/2026-05-31-w1-import-industrial-report.md`

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/planner.py sidecar/supervisor/prompt_policy.py sidecar/supervisor/tools.py sidecar/supervisor/policy.py sidecar/workflows/w1_import.py` — PASS
- `sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_import_compiler.py tests/test_w1_supervisor_policy.py -q` — 134 passed
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_tools.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py tests/test_w1_run_events.py -q` — 95 passed
- `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` — 5/5 passed, secret scan clean
- `npm run ui:build` — PASS with existing Vite chunk-size warning
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts tests/e2e/p1/timeline_topology_import.spec.ts --reporter=list` — 20 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts --reporter=list` — 8 passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_workflow.spec.ts --reporter=list` — 24 passed

## Cost / Safety Ledger

- Live API/model calls: no
- full50 run: no
- Provider keys read: no
- Zero-cost dry-run harness: yes
- Playwright used mocked/dev data only

## Research Notes

Timeline label placement followed a deterministic candidate-placement approach. D3 `forceCollide` and standard automatic label placement references support collision avoidance, but W1 uses a deterministic greedy scorer instead of random force simulation to keep Playwright tests stable.

## Remaining Risks

- Real deep import smoke has not been rerun after this refactor; user manual smoke is still required.
- The deterministic World organizer is LLM-ready but not a standalone live organizer agent.
- `import_test11`-style package grouping depends on proposals carrying `importRunId`; this is now written by W1 proposal data, but older already-created proposals may still rely on fallback grouping.
- Timeline label metrics use approximate SVG text bounds plus Playwright dense fixture validation; unusual fonts may still need tuning.
