# Iteration 1 - 2026-03-05

## Goal
- Scaffold the new Electron + React UI project.
- Implement the primary layout (TopToolbar, ActivityBar, Sidebar, Workspace, Inspector, StatusBar) with required `data-testid` selectors.
- Setup React Router with routes from `UI_ROUTES.txt`.
- Pass P0-1 (Application Launch) and P0-2 (Activity Navigation) tests.

## Strategy
1. Scaffold a React + TypeScript project using Vite in `src/ui-react`.
2. Update root `package.json` with devDependencies and scripts to run Vite and Electron.
3. Setup the basic UI shell in React.
4. Implement Routing and Activity Bar navigation.
5. Create skeleton Workspace pages for all activities.
6. Verify with Playwright.

## Files to be created/modified
- `package.json` (modified)
- `src/ui-react/` (created)
- `src/electron/` (created)
- `dev_logs/matrix.json` (created)

## Initial Assumptions
- Electron will eventually serve the React app.
- For testing purposes, we will target `http://localhost:3000`.
- Streamlit in `src/ui` remains untouched.
