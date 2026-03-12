# Test Plan

## Quality Gates
A module counts complete only when:
- route and sidebar wiring work
- project data persists through the shared service layer
- selectors exist for all core interactions
- Playwright covers the main user path
- QA acceptance confirms the workflow is meaningful and not brittle

## Infrastructure Tests
- App shell renders toolbar, activity bar, sidebar, workspace, inspector, agent dock, and status bar.
- The dev server runs on port `3000` with strict port handling.
- Playwright reuses an existing `3000` server when available and only starts one when needed.
- Project creation, open, and save can run against real or simulated storage.

## Core Workflow Tests
### Workbench
- Inbox renders proposals.
- Accept and reject move proposals to history.
- Resolved proposals no longer show unread state.
- Issues render consistency findings.

### Characters
- Create and edit a character.
- Confirm and reject candidates.
- Invalid profile routes show `Entity not found`.
- Character actions can deep-link into Timeline and Graph.

### Timeline
- Create an event.
- Reorder or move an event between branches.
- Event detail selection updates inspector.
- Timeline links into Writing and shared references.

### Writing
- Scene selection and autosave work.
- Writing context shows linked entities.
- Scene data remains consistent with chapters and events.

### World
- Create containers and items.
- World item editor opens deterministically.
- Custom fields persist.
- World map accepts an image base and markers in later iterations.

### Graph
- Mixed node boards render.
- Graph auto-layout and reset actions respond.
- Queue sync routes proposals into Workbench.

### Publish
- Markdown export renders manuscript and optional appendices.
- HTML export renders the same content with export metadata.

## Safety and Consistency Tests
- Referenced entities cannot be hard-deleted without an impact list.
- Archive preserves discoverability and references.
- Broken references and duplicate entities surface in Consistency or Workbench.
- Proposal resolution clears unread status without extra manual cleanup.

## Regression Scope
At minimum, each implementation iteration should rerun:
- one infrastructure test
- module-specific Playwright tests
- the relevant smoke subset
- production build

## Current Test Strategy
- Use Playwright as the primary behavioral gate.
- Prefer deterministic selectors via `data-testid`.
- Avoid assertions that depend on CSS classes or fragile text layout.
