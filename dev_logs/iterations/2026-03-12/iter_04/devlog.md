# Iteration 04 Devlog

## Theme
Narrative IDE v1 beta foundation reset with real authoring workflows, richer UI behavior, and AI-ready local contracts.

## Major Changes
- upgraded the project model with `schemaVersion`, UI-state persistence, task/run/artifact contracts, character tags, beta personas/runs, richer graph boards, and richer timeline branch metadata
- added migration logic in `projectService` so older projects load into the new structure and reserialize forward
- persisted new project-side files under `system/` and `entities/` for schema metadata, UI state, tasks, runs, beta data, and character tags
- rebuilt `CharactersWorkspace` as route-backed list/candidates/relationships/tags/profile flows
- rebuilt `WritingWorkspace` into a real three-pane authoring layout with resize, collapse, autosave, and broader narrative context
- rebuilt `WorldWorkspace` with custom container creation, inline rename, collapse state, richer detail editing, and reverse references
- rebuilt `TimelineWorkspace` with zoom, pan, branch creation, branch filtering, shared-event rendering, and scene deep-linking
- rebuilt `GraphWorkspace` with multi-board navigation, board creation, pan/zoom, node drag, edge drafting, and sync-to-Workbench flow
- rebuilt `BetaReaderWorkspace` as a data-driven persona lab with aggregate analysis
- added shared `PaneResizeHandle` and global `ContextMenu` primitives
- normalized scrollbar styling and reduced the previous double-scroll behavior
- expanded settings to include layout/density/editor-width/motion controls
- updated Agent Dock to surface task queue and artifacts as future CLI/LangGraph anchors

## QA / Debug Notes
- first build break was caused by a type extraction expression in `PaneResizeHandle.tsx`
- later failures were mostly integration-level: missing imports, stale tests, duplicate test IDs for shared timeline events, and stricter selectors after richer UI
- world container creation required keeping rename-on-create while preserving a stable visible anchor for tests
- writing context was broadened from "only hard-linked scene data" to "linked + recent" so the authoring surface remains useful during active drafting

## Outcome
- production build passes
- browser-mode Playwright suite passes `30/30`
- walkthrough, acceptance report, and progress matrix were updated to match the current product state

## Follow-up Direction
- release hardening for Electron-only project-folder lifecycle
- deeper graph editing polish
- stronger timeline fork/merge authoring controls
- real local task execution behind Agent Dock / Workbench
