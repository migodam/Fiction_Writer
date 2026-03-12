# Iteration 2 - 2026-03-11

## Goal
- Execute the long-run architecture reset for the Narrative IDE.
- Move the app onto a project-folder aware shared data model and service layer.
- Bring Workbench and Agent Dock forward as first-class shell features.
- Stabilize world, graph, timeline, and smoke coverage against the new foundation.

## Assigned Sub-Agents
- Architecture Agent: define the shared project model, route-backed shell contract, and future agent placement.
- UI Implementation Agent: wire Workbench, Agent Dock, and the repository-backed shell into the React app.
- Testing Agent: align smoke and P1 coverage with Workbench, Graph sync, and World item creation.
- Debugging Agent: fix timeline event normalization, world item editor activation, and duplicate selector instability.
- QA Acceptance Agent: validate the shell, Workbench flow, Graph sync, World item create flow, and route stability.
- Documentation Agent: write new source-of-truth docs and iteration artifacts.

## Files Changed
- `dev_docs/PRODUCT_SPEC.md`
- `dev_docs/DATA_MODEL.md`
- `dev_docs/ROUTES_AND_UI.md`
- `dev_docs/TEST_PLAN.md`
- `dev_docs/ITERATION_PROTOCOL.md`
- `src/ui-react/App.tsx`
- `src/ui-react/components/AgentDock.tsx`
- `src/ui-react/components/WorkbenchWorkspace.tsx`
- `src/ui-react/components/CharactersWorkspace.tsx`
- `src/ui-react/components/EventInspector.tsx`
- `src/ui-react/components/GraphWorkspace.tsx`
- `src/ui-react/components/TimelineWorkspace.tsx`
- `src/ui-react/components/WorldWorkspace.tsx`
- `src/ui-react/config/routes.tsx`
- `src/ui-react/mock/seedProject.ts`
- `src/ui-react/models/project.ts`
- `src/ui-react/services/projectService.ts`
- `src/ui-react/store.ts`
- `tests/e2e/p1/cross_page_links.spec.ts`
- `tests/e2e/p1/graph_layout_persist.spec.ts`
- `tests/e2e/p1/world_model_containers.spec.ts`
- `tests/e2e/smoke.spec.ts`
- `vite.config.ts`

## Summary of Changes
- Added a shared Narrative Project model, seed project, and project service for create/open/save flows with split-file persistence support.
- Rebuilt the app shell around route-backed Workbench sections, a global Agent Dock, and project-aware status reporting.
- Promoted Workbench to an Inbox/History/Issues/Bulk Actions surface and added Graph-to-Workbench proposal queuing.
- Added strict port handling on Vite so the dev server stays on `3000` instead of drifting to `3001`.
- Fixed World item creation by recognizing generated `new_*` item IDs and initializing the editor with the new world schema.
- Normalized timeline event editing to the shared event model so saved events no longer crash the timeline view.
- Replaced placeholder P1 specs with real coverage for graph sync, world item creation, and cross-page deep-link flows.
- Wrote new source-of-truth docs for product scope, data model, routes/UI, test plan, and iteration protocol.

## Bugs Found
- Timeline events created from the inspector still used legacy `participants` and `location` fields, which destabilized the timeline after save.
- The collapsed Agent Dock reused the top-toolbar `ai-assistant` selector, causing strict-mode Playwright failures.
- The previous smoke test still expected obsolete Workbench sidebar sections.
- Vite could still drift to port `3001` when `3000` was occupied.

## Bugs Fixed
- Timeline inspector now normalizes edited events into `participantCharacterIds` and `locationIds` before save.
- Collapsed Agent Dock now uses a dedicated `agent-dock-expand` selector.
- Smoke and P1 tests now match the current Workbench route contract and shell behavior.
- The stray Vite process on `3001` was terminated and `strictPort: true` now prevents recurrence.

## QA Result
- Accepted for this iteration: foundation shell, shared project service, Workbench route contract, Agent Dock shell, Graph sync proposal flow, World item creation, and updated smoke coverage.

## Known Issues
- Project persistence currently defaults to memory mode in browser-based Playwright runs and `nodefs` mode in Electron-capable contexts.
- Publish, Consistency auto-fix suggestions, and advanced modules remain phase backlog items rather than complete deliverables.

## Next Priorities
- Expand the project-folder lifecycle with explicit folder picker integration through Electron.
- Deepen Writing, Timeline, and World references against the shared repository layer.
- Implement Workbench-backed Consistency suggestions and Publish export against the new project schema.
