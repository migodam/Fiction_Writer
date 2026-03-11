# Developer Agent Logs

## Step A: Repo Scan & Entry Points
*   **Entry Points:** `src/ui-react/main.tsx`, `src/ui-react/App.tsx`.
*   **Router:** React Router v6 used in `App.tsx`. Navigation works by passing state around.
*   **Tailwind:** Used natively. Config is at `tailwind.config.js` and entry CSS at `src/ui-react/style.css`.
*   **Tests:** Playwright under `tests/e2e/`. Run via `npx playwright test`. Playwright config at `tests/playwright.config.ts`.
*   **Action taken:** Scanned repo to understand current architecture.

## Step B: Implement AppShell + Routes + Wire Pages
*   Created `src/ui-react/config/routes.tsx` to act as the single source of truth for the app's routing configuration (Activity Bar items, Sidebar sections, actions, etc.).
*   Refactored `Sidebar.tsx` to use this new route config instead of hardcoded maps.
*   Refactored `App.tsx` layout and `TopToolbar` to pull dynamically from `APP_ROUTES` and handle sidebar/workspace state changes.
*   State management (Zustand) in `store.ts` verified to be sufficient for initial panels/selection (already supported `currentActivity`, `sidebarSection`, etc.).

## Step C: Integrate Tokens + Styles
*   Mapped CSS variables (`--bg`, `--text`, `--brand`, etc.) from `src/ui-react/style.css` into `tailwind.config.js` theme block.
*   Wrote `dev_docs/DEV_UI_TOKENS.md` to document usage.
*   Updated components like `Sidebar.tsx` and parts of `App.tsx` to use the semantic Tailwind classes (`bg-bg-elev-1`, `text-text-2`, `hover:bg-hover`, `border-border`, etc.) instead of hardcoded hex colors `[#...]`.

## Step D: Add Mock Data + Contracts
*   Created mock JSON files under `src/ui-react/mock/`: `characters.json`, `timeline.json`, `relationships.json`, `world_items.json`, `graph.json`.
*   Created `dev_docs/UI_CONTRACT.md` detailing the layout, buttons, and routing expectations for each activity.

## Step E: Playwright Smoke Tests & Fixes
*   Run the initial tests with `npm run test:e2e` to verify existing tests.
*   Fixed a bug in `WritingWorkspace.tsx` causing a TypeScript build error.
*   Fixed failing E2E tests for 'Saved' toast visibility by switching to exact text match to disambiguate from 'Unsaved changes'.
*   All 13 E2E tests pass.

## Metrics
*   **Iteration time:** ~5 min
*   **Tests:** 13 passed / 0 failed.

## Known Issues
*   The `Inspector` and other workspace sub-panels still have many hardcoded `[#hex]` tailwind classes that could be migrated to the new semantic tokens in a future pass.