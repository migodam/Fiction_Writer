# Test Results - Iteration 2

## Commands Run
- `npm run build`
- `npm run test:e2e -- tests/e2e/p0/timeline_crud_drag.spec.ts tests/e2e/p1/graph_layout_persist.spec.ts tests/e2e/smoke.spec.ts --grep "create timeline event|agent dock can be collapsed and restored without losing workbench context|can interact with timeline events and drag reorder|can use writing studio with sidebar and context panel|toolbar save action updates status bar"`
- `npm run test:e2e -- tests/e2e/p0/navigation.spec.ts tests/e2e/p0/characters_crud.spec.ts tests/e2e/p0/timeline_crud_drag.spec.ts tests/e2e/p0/writing_editor.spec.ts tests/e2e/p1/characters_routes.spec.ts tests/e2e/p1/world_model_containers.spec.ts tests/e2e/p1/graph_layout_persist.spec.ts tests/e2e/p1/cross_page_links.spec.ts tests/e2e/smoke.spec.ts`

## Passed
- Production build
- `tests/e2e/p0/navigation.spec.ts`
- `tests/e2e/p0/characters_crud.spec.ts`
- `tests/e2e/p0/timeline_crud_drag.spec.ts`
- `tests/e2e/p0/writing_editor.spec.ts`
- `tests/e2e/p1/characters_routes.spec.ts`
- `tests/e2e/p1/world_model_containers.spec.ts`
- `tests/e2e/p1/graph_layout_persist.spec.ts`
- `tests/e2e/p1/cross_page_links.spec.ts`
- `tests/e2e/smoke.spec.ts`

## Result Summary
- Full targeted Playwright suite: `26/26` passed.
- Focused regression rerun for timeline, agent dock, writing smoke path, and status bar behavior: passed.
- World item editor blocker is resolved.
- Current shell and foundation changes are stable against the repo's active browser test suite.
