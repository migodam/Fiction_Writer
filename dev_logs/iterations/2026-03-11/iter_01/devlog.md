# Iteration 1 - 2026-03-11

## Goal
- Stabilize the Characters module against the route and selector contract.
- Fix the failing P0 candidate confirmation flow.
- Make Playwright start the Vite dev server deterministically from project scripts.

## Assigned Sub-Agents
- Architecture Agent: define Characters route and sidebar contract.
- UI Implementation Agent: patch Characters routing, selection, and invalid-profile behavior.
- Testing Agent: repair Characters coverage and wire Playwright to the repo config.
- Debugging Agent: verify root cause of the candidate-flow failure and capture deferred World evidence.
- QA Acceptance Agent: validate Characters against UI logic and UX rules.
- Documentation Agent: update iteration artifacts and matrix state.

## Files Changed
- `package.json`
- `src/ui-react/App.tsx`
- `src/ui-react/components/CharactersWorkspace.tsx`
- `src/ui-react/components/Sidebar.tsx`
- `src/ui-react/config/routes.tsx`
- `src/ui-react/store.ts`
- `src/ui-react/components/WritingWorkspace.tsx`
- `tests/e2e/p0/characters_crud.spec.ts`
- `tests/e2e/p1/characters_routes.spec.ts`
- `tests/playwright.config.ts`

## Summary of Changes
- Added URL-backed Characters routes for `list`, `candidates`, `relationships`, `tags`, and `profile/:characterId`.
- Synced sidebar state from the current route instead of relying on implicit in-memory defaults.
- Made candidate confirmation deterministic by routing to the confirmed character profile after confirmation.
- Added invalid character profile handling with an `Entity not found` recovery path.
- Added Characters route coverage in Playwright and fixed the project script to load the repository Playwright config.
- Removed an invalid Lucide `title` prop in Writing Studio so the TypeScript/Vite production build succeeds.

## Bugs Found
- P0 candidate confirmation failed because the app landed on `/characters` without entering the candidate queue view.
- Playwright config in `tests/playwright.config.ts` was not used by `npm run test:e2e`, so `baseURL` and `webServer` were ignored.
- Deferred blocker outside current scope: World item editor still does not appear after `add-world-item-btn`.

## Bugs Fixed
- Candidate confirmation now passes through route-backed sidebar navigation and profile selection.
- Playwright now uses `--config tests/playwright.config.ts`, with a repo-root `webServer` and `baseURL`.
- Characters profile routes now render a not-found state instead of silently falling back.

## QA Result
- Accepted for this iteration: Characters route contract, candidate flow, save validation, inspector sync, and navigation behavior passed targeted QA coverage.

## Known Issues
- `tests/e2e/smoke.spec.ts` world-model item creation still fails waiting for `world-item-name-input`.
- Governing document path drift remains: `dev_docs/TEST_PLAN.md` exists, but `tests/TEST_PLAN.md` does not; iteration protocol still lives at `dev_agent_logs/iteration.md`.

## Next Priorities
- Fix the deferred World item editor bug.
- Expand route-backed contracts and deep-link coverage for Timeline and Writing Studio.
- Fill remaining empty `tests/e2e/p1/*.spec.ts` files with behavior-level coverage instead of placeholders.
