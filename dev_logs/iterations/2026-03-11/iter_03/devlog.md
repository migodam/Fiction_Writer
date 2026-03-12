# Iteration 3 - 2026-03-11

## Goal
- Deliver a user-acceptable Narrative IDE demo for Windows-style desktop usage.
- Add real project initialization flow with `starter-demo` and `blank` templates.
- Add single-language switching between English and Chinese.
- Add collapsible/resizable shell layout comparable to an IDE.
- Expand walkthrough, export, world map, and cross-page acceptance coverage.

## Assigned Sub-Agents
- Architecture Agent: finalize the shell contract for project lifecycle, layout persistence, locale state, and proposal flow.
- UI Implementation Agent: implement project dialogs, starter project content, publish workspace, insights workspace, world map, and shell resizing.
- Testing Agent: align old tests to the new starter data and add acceptance coverage for project init, layout, locale, world map, and publish.
- Debugging Agent: investigate failing route contracts, stale selector expectations, and the sidebar toggle defect.
- QA Acceptance Agent: validate all top-level modules, cross-page deep links, export flows, and walkthrough readiness.
- Documentation Agent: author the Chinese walkthrough, acceptance report, and iteration artifacts.

## Files Changed
- `src/electron/main.js`
- `src/ui-react/App.tsx`
- `src/ui-react/components/AgentDock.tsx`
- `src/ui-react/components/BetaReaderWorkspace.tsx`
- `src/ui-react/components/CharactersWorkspace.tsx`
- `src/ui-react/components/ConsistencyWorkspace.tsx`
- `src/ui-react/components/EventInspector.tsx`
- `src/ui-react/components/GraphWorkspace.tsx`
- `src/ui-react/components/InsightsWorkspace.tsx`
- `src/ui-react/components/PublishWorkspace.tsx`
- `src/ui-react/components/Sidebar.tsx`
- `src/ui-react/components/SimulationWorkspace.tsx`
- `src/ui-react/components/TimelineWorkspace.tsx`
- `src/ui-react/components/WorkbenchWorkspace.tsx`
- `src/ui-react/components/WorldWorkspace.tsx`
- `src/ui-react/components/WritingWorkspace.tsx`
- `src/ui-react/i18n.ts`
- `src/ui-react/mock/seedProject.ts`
- `src/ui-react/models/project.ts`
- `src/ui-react/services/electronApi.ts`
- `src/ui-react/services/projectService.ts`
- `src/ui-react/store.ts`
- `tests/e2e/p0/characters_crud.spec.ts`
- `tests/e2e/p1/characters_routes.spec.ts`
- `tests/e2e/p1/cross_page_links.spec.ts`
- `tests/e2e/p1/graph_layout_persist.spec.ts`
- `tests/e2e/p1/layout_i18n.spec.ts`
- `tests/e2e/p1/project_init_and_persistence.spec.ts`
- `tests/e2e/p1/world_map_publish.spec.ts`
- `tests/e2e/smoke.spec.ts`
- `docs/DEMO_WALKTHROUGH.md`
- `docs/ACCEPTANCE_REPORT.md`

## Summary of Changes
- Implemented project creation/open/save flows around starter and blank templates.
- Added a richer starter demo project with characters, candidates, branches, scenes, world items, graph boards, proposals, issues, exports, and world map markers.
- Added locale-aware UI state and translation dictionaries for English and Simplified Chinese.
- Added a settings modal, project dialog, and persisted layout state.
- Added resizable `Sidebar`, `Inspector`, and `Agent Dock`, plus functional sidebar collapse.
- Promoted `Publish` and `Insights` from placeholders into data-backed workspaces.
- Expanded `Timeline`, `World`, `Writing`, and `Graph` to support the acceptance walkthrough paths.
- Added acceptance-grade Playwright coverage for project init/reopen, layout, language switching, world map, publish exports, and updated cross-page flows.
- Authored a detailed Chinese walkthrough and acceptance report.

## Bugs Found
- The top toolbar sidebar toggle passed the current collapse state back into the store instead of flipping it, so the sidebar did not actually collapse.
- Several Playwright tests still depended on obsolete starter IDs such as `char_1`, `cand_1`, and `scene_1`.
- The command palette smoke test matched both the command palette option and the activity bar button under strict mode.
- The old layout acceptance approach measured the wrong DOM node and could not detect panel resizing correctly.

## Bugs Fixed
- Fixed the toolbar sidebar toggle to invert collapse state correctly.
- Updated tests and cross-page expectations to the new starter dataset (`char_aria`, `cand_mina`, `scene_arrival`, `event_bridge`, etc.).
- Scoped command palette navigation to the palette container to avoid strict-mode ambiguity.
- Reworked layout acceptance checks to validate resizer movement and sidebar collapse/restore behavior.

## QA Result
- Accepted for this iteration: acceptance demo shell, starter project flow, locale switching, resizable layout, cross-page authoring workflow, world map path, publish export path, and walkthrough/report deliverables.

## Known Issues
- Electron folder operations are implemented, but the automated acceptance suite still runs in browser mode and validates the localStorage fallback path instead of a true Electron E2E run.
- Agent Dock remains a shell without live agent execution.
- Portrait generation is still a placeholder action.

## Next Priorities
- Add Electron-level end-to-end validation for real folder-backed create/open/save.
- Deepen structured references and conflict visualization across Characters, Timeline, Writing, World, and Graph.
- Expand Graph editing beyond selection and proposal queuing.
- Continue toward true agent task execution while keeping Workbench as the review gate.
