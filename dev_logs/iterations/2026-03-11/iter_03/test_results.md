# Test Results - Iteration 3

## Commands Run
- `npm run build`
- `npm run test:e2e -- tests/e2e/p0/characters_crud.spec.ts tests/e2e/p1/characters_routes.spec.ts tests/e2e/p1/cross_page_links.spec.ts tests/e2e/p1/graph_layout_persist.spec.ts tests/e2e/p1/project_init_and_persistence.spec.ts tests/e2e/p1/layout_i18n.spec.ts tests/e2e/p1/world_map_publish.spec.ts tests/e2e/smoke.spec.ts`
- `npm run test:e2e -- tests/e2e/p1/layout_i18n.spec.ts`
- `npm run test:e2e`

## Passed
- Production build
- Full Playwright suite (`30/30`)
- Project initialization and reopen flow
- Locale switching (`en <-> zh-CN`)
- Sidebar collapse and multi-panel resizing
- Characters route contract and candidate confirmation
- Timeline character/location filtering and scene jump
- World model containers and world map markers
- Graph -> Workbench proposal flow
- Workbench inbox/history resolution flow
- Publish Markdown/HTML export flow
- Smoke coverage across all top-level modules

## Result Summary
- Final browser acceptance suite: `30/30` passed.
- The iteration now has executable coverage for the new acceptance plan instead of the older partial foundation checks.
- The demo walkthrough path is supported by the current UI and test suite.

## Residual Risk
- Electron-specific folder picking and true filesystem writes are implemented but not covered by Playwright browser mode; they still require desktop/Electron validation.
