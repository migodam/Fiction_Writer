# Acceptance Report

## Scope
This iteration promotes the project from a shell-heavy demo to a Windows-focused, offline-first `v1 beta` candidate for large novel development. The acceptance target is no longer "every page can open", but "core authoring, cross-page navigation, layout behavior, and review flow are credible, stateful, and testable."

## Accepted In This Iteration
### Foundation / data / migration
- Project schema upgraded with `schemaVersion`
- Legacy project loading now migrates into the current model before use
- Project persistence now includes:
  - `system/schema/schema.json`
  - `system/ui-state.json`
  - `system/tasks/requests.json`
  - `system/runs/runs.json`
  - `system/runs/artifacts.json`
  - `system/beta-personas.json`
  - `system/beta-runs.json`
  - `entities/character-tags.json`
- Project-level UI state is now persisted and restored with the project

### Shell / UX system
- Top-level pane system remains `Sidebar / Workspace / Inspector / Agent Dock`
- Top-level pane widths are resizable and persisted
- Writing Studio now has its own internal pane system:
  - `Outline / Selection`
  - `Manuscript`
  - `Narrative Context`
- Internal writing panes support collapse, resize, and persisted layout state
- Scroll containers were normalized to remove the previous double-scroll behavior
- Global scrollbar styling is now unified into a narrow dark theme
- Settings now include:
  - language
  - layout reset
  - density
  - editor width
  - motion level
  - shortcut guidance
- A shared context-menu system is now available across major workspaces

### Core authoring loop
- `Characters` now uses real route-backed sections:
  - `/characters/list`
  - `/characters/candidates`
  - `/characters/relationships`
  - `/characters/tags`
  - `/characters/profile/:characterId`
- `Characters / Relationships` is no longer empty and supports relationship creation plus timeline presence links
- `Characters / Tags` is now data-backed with tag creation, deletion, and character membership toggling
- `Writing Studio` now behaves like a real authoring tool instead of a fixed-width page
- `World Model` now supports custom container creation, inline rename, collapse state, and item editing with reverse references

### Timeline / Graph / Beta Reader
- Timeline branch data now supports true branch metadata:
  - `parentBranchId`
  - `forkEventId`
  - `mergeEventId`
  - `sharedBranchIds`
- Timeline now supports zoom, pan, branch creation, branch filtering, location filtering, character filtering, hover cards, and drag reassignment
- Graph now supports:
  - multiple boards
  - board creation and switching
  - node creation
  - edge drafting
  - node dragging
  - canvas pan
  - `Ctrl + wheel` zoom
  - graph sync proposal routing into Workbench
- Beta Reader is now data-driven with persona list, persona creation, persona runs, aggregate metrics, and feedback cards

### AI-ready interfaces
- Added data contracts for:
  - `TaskRequest`
  - `TaskRun`
  - `TaskArtifact`
  - `BetaPersona`
  - `BetaRun`
  - richer `GraphBoard`
  - richer `TimelineBranch`
- Agent Dock now surfaces task queue, run state, and artifacts as future integration anchors
- External agents still do not mutate canonical data directly; Workbench remains the review gate

## Cross-Page Flows Accepted
- `Characters -> Timeline`
- `Characters -> Graph`
- `World Model -> Timeline`
- `Timeline -> Writing`
- `Graph -> Workbench`
- `Workbench -> History`
- `Publish <- Project data`

## Test Results
### Build
- `npm run build`
- Result: passed on March 12, 2026

### Playwright
- `npx playwright test --config tests/playwright.config.ts`
- Result: `30/30 passed` on March 12, 2026

### Coverage focus
- layout resizing and language switching
- route-backed character sections
- graph to workbench proposal flow
- world container and item creation
- cross-page deep links
- writing autosave
- publish export flow
- full smoke path

## Remaining Limitations
- Electron-backed directory lifecycle still needs a dedicated desktop-only end-to-end pass beyond browser-mode Playwright
- Graph does not yet support marquee selection or full multi-node editing workflows
- Timeline branch UI now carries real branch semantics, but fork/merge editing UX is still lighter than the final target
- Agent Dock and task contracts are ready for future CLI / LangGraph integration, but no real task execution is wired in this release
- Portrait generation remains placeholder-only
- Undo/history and richer release-grade export controls are still future work

## Acceptance Verdict
This iteration is accepted as a `v1 beta` baseline for continued productization. The project now has a stable enough data boundary, a credible authoring loop, UI behavior that matches the walkthrough more closely, and automated coverage strong enough to support the next round of release hardening.
