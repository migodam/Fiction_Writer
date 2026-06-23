# W1 Import Manual Smoke Bug Todo — 2026-05-29

## Review Rule

Only investigate unchecked items during each follow-up pass. Mark an item checked only after code/tests or a manual smoke artifact proves the symptom is gone.

## Checklist

- [x] Chapters import in source order, including Chinese chapter numerals and Arabic numerals.
- [x] Blank starter `Chapter 1` / `Scene 1` are removed during first W1 import acceptance.
- [x] Chapter detail fields are populated and visible: summary, goal, notes, and scene list.
- [x] Manuscript text is written into canonical `Scene.content` and attached to the matching chapter.
- [x] `Accept All` handles same-batch dependencies across characters, events, relationships, chapters, scenes, branches, containers, and world items.
- [x] Main characters and relationships can be accepted; minor-only imports are no longer a dependency artifact.
- [x] Starter `Main Branch` does not overlap imported branches after W1 import acceptance.
- [x] Starter English world containers are cleaned from W1 import projects.
- [x] World Model taxonomy routes Chinese cultivation methods to their own category and avoids putting people/roles into the wrong world container.
- [x] Final acceptance report compares every unchecked item above and records evidence before checking it off.

## Initial Investigation Notes

- The Workbench safety applier validates one proposal at a time against the current project only. It cannot see IDs that will be created by other proposals in the same import batch, so characters, events, relationships, scenes, and world items can block each other.
- W1 scene proposals were derived from chunk scene summaries with `chapterId: None` and no manuscript content. Chapter proposals carried manuscript text on chapter-only fields, while the canonical writing UI reads scene content.
- W1 chapter proposals used empty summary/goal fields, so the chapter detail side card had little useful imported information to display.
- Starter blank projects include `Main Branch`, `Chapter 1`, `Scene 1`, and English world containers. These defaults need to be cleaned when accepting real W1 import proposals into a still-blank project.

## Zero-Cost Verification Evidence

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py` — pass.
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_prompt_windows.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py tests/test_w1_run_events.py tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py -q` — 210 passed.
- `sidecar/.venv/bin/python benchmark_results/v2_planner_dry_run/run_harness.py --no-write` — 5/5 passed, secret scan clean, live smoke skipped.
- `npm run ui:build` — pass.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_activity_status.spec.ts tests/e2e/p1/import_workflow.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts tests/e2e/p1/import_smoke_acceptance.spec.ts --reporter=list` — 34 passed.

## Manual Smoke Boundary

The actual `impirt_test9`/`import_test9` project directory was not present under this repository's `data/projects` during this pass, so the fixes are verified with deterministic fixtures that reproduce the same dependency, manuscript, default-template, and taxonomy failure modes. A small manual `deep` smoke is still the next user-facing validation step.
