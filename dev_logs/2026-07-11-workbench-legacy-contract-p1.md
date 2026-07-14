# Workbench Legacy-Contract P1 Repair

## Scope

- Restored Playwright coverage for the reachable Workbench Backlog story-gap view.
- Aligned graph coverage with the active `graph-board-flow` selector and graph node IDs.
- Replaced stale default-seed dependencies in chapter preview and proposal safety coverage with explicit browser fixtures.
- Updated locale verification to use the active Advanced Settings language controls.

## Product vs. Legacy Contract

- Product behavior: Backlog remains available at `/workbench/tasks`; tests must navigate through that route instead of expecting its controls in Inbox.
- Product behavior: the graph surface exposes `graph-board-flow`, and starter board node IDs use the `graph_` prefix.
- Product behavior: settings are rendered by `AdvancedSettingsModal`; its language rows are role-addressable controls rather than the removed legacy locale test IDs.
- Legacy contract: the retired inspector resizer is no longer asserted. Sidebar and Agent Dock resize coverage remains.
- Safety behavior: the tests now create their own accepted and unsupported proposals, their canonical world item, and their linked issue. They no longer depend on mutable seed proposal IDs.

## Files Changed

- `tests/e2e/p1/backlog_story_gaps.spec.ts`
- `tests/e2e/p1/chapter_preview.spec.ts`
- `tests/e2e/p1/graph_layout_persist.spec.ts`
- `tests/e2e/p1/layout_i18n.spec.ts`
- `tests/e2e/p1/workbench_proposal_safety.spec.ts`

## Verification

- `npx playwright test --config tests/playwright.config.ts --workers=1 tests/e2e/p1/workbench_proposal_safety.spec.ts` - passed (5 tests).
- `npx playwright test --config tests/playwright.config.ts --workers=1 tests/e2e/p1/backlog_story_gaps.spec.ts tests/e2e/p1/chapter_preview.spec.ts tests/e2e/p1/graph_layout_persist.spec.ts tests/e2e/p1/layout_i18n.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts` - passed (11 tests).
- `npm run ui:lint` - passed.
- `npm run ui:build` - passed. Vite reported only its existing chunk-size advisory.
