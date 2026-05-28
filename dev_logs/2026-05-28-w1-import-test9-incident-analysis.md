# W1 Import Test9 Incident Analysis and Fixes — 2026-05-28

## Scope

Investigated the user-reported run for project `import_test9`, run id `sup_451530498f`, created from `凡人修仙传_前50章.txt` with `prompt_profile=deep` and model `deepseek-v4-flash`.

No live model/API calls were made in this investigation. No full50 benchmark was run.

## Findings

- Backend extraction did run: artifacts show 16 original prompt windows, 47 window artifacts after split/rerun activity, 47 character proposals counted, 109 canonical timeline events, 76 world items, and `judge_artifact.score=0.82`.
- Product-visible project state was empty after the run: `system/inbox.json=[]`, `project.json` counts stayed zero, `manuscript.json` was absent, and `workflow.lock` remained.
- Quality was not product-grade despite a non-trivial judge score: relationships were `0`, character coverage failed softly (`47 < 50`), mainline topology was overdense, and timeline artifacts contained many exact/near-duplicate event titles.
- Cost pressure was caused by gate mismatch: `ImportGranularityProfile` selected `coarse_webnovel` with `min_characters_per_chapter=1.0` and `rerun_on_character_gap=false`, but `_process_window()` used flat ToolOperatingSpec defaults (`min_characters_per_chapter=1.5`, `event_density_target=1.25`) for rerun gates.
- Replaying `import_test9` window metrics: old rules flagged 14/16 original windows; profile-aware rules flag 5/16. Most prior reruns were chasing character density that the selected coarse profile explicitly should not chase.
- Supervisor window context was weaker than documented: `_build_supervised_prompt_windows()` wrote digest/validation headers into `window["text"]`, but `extract_window()` reassembled prompt text from chunks and dropped that header unless chunk text was absent.
- Relationship candidates lost evidence fields in the supervisor path before synthesis, making relationship finalization brittle and contributing to `relationships=0`.
- `node_write_to_project()` wrote `manuscript.json` after hundreds of proposal operations, so cancellation/OOM during proposal writes could leave no manuscript content even when extraction had succeeded.

## Fixes

- `_process_window()` now derives effective rerun gate thresholds from the validated `import_granularity_profile`, including `rerun_on_character_gap`.
- Thematic character recovery hints now use `converge_target.expected_min_characters` rather than recomputing from flat ToolOperatingSpec defaults.
- `extract_window()` now dynamically prepends current project digest, rolling registry summary, rolling validation summary, and import-plan context to each prompt call.
- Raw relationship candidates now preserve `evidence`, `aliasEvidence`, and `contradictionHint`.
- `node_synthesize_relationships()` now falls back to deterministic evidence-grounded relationships when the synthesis prompt returns none or errors.
- `node_architect_timeline()` now merges exact/high-confidence near-duplicate event titles while preserving numbered synthetic progression events.
- `node_write_to_project()` writes `manuscript.json` before proposal loops and writes `proposal_write_receipts.json` after proposal writes.

## Tests

- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/policy.py sidecar/supervisor/tools.py sidecar/workflows/w1_import.py` — pass.
- Targeted incident tests — 9 passed.
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_import_compiler.py -q` — 148 passed.
- Combined W1 regression set — 403 passed.
- `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` — 5/5 passed, secret scan clean, live smoke skipped.

## Cost Ledger

- Live model/API calls: false.
- Full50 benchmark: false.
- Zero-cost tests only.

## Deferred

- A real live smoke should not be attempted until the user explicitly approves cost.
- Proposal inbox clobbering by later frontend saves is still a suspected risk if `system/inbox.json` was overwritten after a successful write; `proposal_write_receipts.json` now makes that failure auditable, but a separate project-save merge guard may still be warranted.
