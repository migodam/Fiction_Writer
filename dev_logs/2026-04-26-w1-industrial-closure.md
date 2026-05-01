# W1 Industrial Closure

## Summary
- Added W1 JSON robustness for fenced JSON, trailing commas, malformed/truncated model output repair, and failed extraction artifacts.
- Prevented failed chunk prompt outputs from being cached as successful empty results.
- Slimmed imported character cards so W1 creates reviewable identity drafts instead of deep biography fields.
- Added semantic Timeline Architect branch assignment and density policy so dense imports do not collapse every event onto the root branch.
- Added Import Review status plumbing and UI surface with review counts, failed chunk signal, console access after completion, and safe batch-accept affordance.
- Added adaptive Timeline canvas width based on branch event density.

## Verification
- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/models/state.py sidecar/routers/workflows.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py`
- `npm run ui:lint`
- `npm run ui:build`
- `npx playwright test tests/e2e/p1/import_workflow.spec.ts --config tests/playwright.config.ts`
- `npx playwright test tests/e2e/p0/navigation.spec.ts --config tests/playwright.config.ts`

## Notes
- The first parallel Playwright attempt started two Vite web servers on port 3000; `navigation.spec.ts` was rerun alone and passed.
- DeepSeek-V4-Flash can still produce malformed JSON, so the fix keeps model-independent parser repair and failure artifact behavior.
