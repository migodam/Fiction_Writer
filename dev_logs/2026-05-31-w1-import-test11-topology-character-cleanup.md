# W1 Import Test 11 Topology and Character Cleanup — 2026-05-31

## Scope

- Investigated follow-up smoke findings on `import_test11`.
- No live model/API calls were made.
- No full50 benchmark was run.
- Real project data was inspected but not manually edited.

## Findings

- The previous stale-branch fix allowed 36 timeline events to be accepted, but `system/inbox.json` still contained 17 pending character proposals.
- Remaining character proposals referenced event IDs that were discarded, merged, or demoted by Timeline Architect. Those stale `lastBlockReason` values still prevented acceptance.
- Several character proposals represented duplicate identities across prompt windows: repeated `韩立`, `韩母`, `韩父`, `三叔`, `岳堂主`, `王护法`, and similar entries.
- `timeline_architecture.json` contained fork/merge-ready branches, but `node_infer_world_settings()` returned a later `timeline_branches` value from broad world-settings inference. That later value could overwrite Timeline Architect topology before proposal write.
- The current project still had the blank starter `Chapter 1`/`Scene 1`, which collides with imported `第一章` because both sort at order index 0.
- Some chapters had duplicate content scenes: a W2-generated `第N章 — content` scene plus W1 `章节正文` scene with identical manuscript content.

## Fixes

- Workbench import acceptance now filters dangling references from imported character proposals before validation, so discarded scene-beat event IDs do not permanently block otherwise valid characters.
- Workbench import acceptance now merges same-name/alias character proposals into an existing canonical character instead of creating duplicate cards.
- W1 proposal write deduplicates same-identity registry characters before writing proposals and remaps event/relationship character IDs to the surviving primary ID.
- `node_infer_world_settings()` now preserves existing Timeline Architect branches instead of overwriting fork/merge-ready topology with broad world-settings suggestions.
- Project migration now removes blank starter writing artifacts once imported chapters exist and collapses duplicate same-content chapter scenes.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q` — 49 passed
- `npm run ui:build` — passed
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_smoke_acceptance.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts --reporter=list` — 8 passed

## Remaining Product-Quality Work

- Event extraction is still too granular for a novelist timeline. The next quality iteration should lower canonical event density, keep scene beats as manuscript notes, and require stronger causal/turning-point criteria before creating timeline events.
- Import UI still needs user-facing switches for Manuscript and Relationship extraction.
- Relationship quality remains limited by character dedupe and event granularity; rerun quality should be assessed after the current structural fixes are in place.
