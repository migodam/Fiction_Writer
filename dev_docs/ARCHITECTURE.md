# Narrative IDE — Active Architecture

## Purpose
This document describes the active runtime architecture of the product. Use `WORKFLOW_STATUS.md` for workflow state and `FRONTEND_BACKEND_CHECKLIST.md` for detailed bridge mapping.

## Active Stack
- Desktop shell: Electron
- UI: React 18 + Vite
- Global state: Zustand
- Persistence/services: TypeScript service layer plus Electron IPC
- Workflow runtime: Python sidecar
- Behavioral testing: Playwright

## Runtime Topology
```text
Electron main process
  -> window lifecycle, dialogs, IPC handlers, sidecar spawn/control

React app (`src/ui-react`)
  -> shell layout, workspaces, agent surfaces, settings, route-backed modules

Zustand store (`src/ui-react/store.ts`)
  -> UI state + project state + selection + workflow status snapshots

Service layer (`src/ui-react/services/*`)
  -> project persistence, metadata loading, Electron bridge calls

Canonical storage
  -> split project files on disk
  -> `project.db` for selected structured data / search surfaces

Python sidecar (`sidecar`)
  -> W0-W7 workflow execution, lock handling, status endpoints, proposal-producing operations
```

## Active Module Inventory
The current route-backed modules are:
- Workbench
- Writing Studio
- Characters
- Timeline
- Graph
- World Model
- Simulation
- Beta Reader
- Consistency
- Agents
- Publish
- Insights
- Reference Library

The shell also includes a persistent Agent Dock and Status Bar.

## Data and Control Boundaries
### Electron boundary
- Owns native integration, app settings persistence, file system dialogs, IPC registration, and sidecar process control.
- Must not own product logic or canonical domain behavior.

### React/UI boundary
- Owns layout, rendering, local interaction flows, and route/module composition.
- Must not read/write canonical storage directly.

### Zustand boundary
- Owns shared selection, route state, panel state, task/run snapshots, and project entities loaded into the client.
- `setSelectedEntity(type, id)` remains the global selection contract for Inspector-focused behavior.

### Service boundary
- `projectService` and related services are the only allowed UI-facing persistence interfaces.
- `electronApi` is the UI bridge to Electron IPC and sidecar triggers.

### Sidecar boundary
- Owns workflow execution, runtime locks, status polling surfaces, and workflow-specific AI orchestration.
- Returns status and proposal-producing results; it does not directly own the React state tree.

## Persistence Model
- Canonical project state is folder-backed and split across project files.
- `project.json` remains the top-level project metadata and index surface.
- `project.db` exists in the active stack and should be treated as an active implementation detail, not a future-only migration note.
- The UI must remain storage-implementation-agnostic through services and IPC.

## Workflow Integration Model
- W0-W7 run through sidecar endpoints and status polling surfaces.
- Workflow status ownership:
  - status source -> `WORKFLOW_STATUS.md`
  - integration source -> `FRONTEND_BACKEND_CHECKLIST.md`
- Proposal gatekeeping is mandatory for AI-originated canonical changes.

## Known Architectural Gaps
- W0 Orchestrator has verified backend behavior but lacks a canonical production control surface.
- W2 Manuscript Sync has verified backend behavior but lacks a stable production trigger in the UI.
- Proposal acceptance and canonical-data safety need stronger end-to-end closure across Workbench and shared references.
- Publish/export is present as a workspace but not yet a fully closed delivery subsystem.
- Sidecar lifecycle, restart ergonomics, and shared runtime surfaces still need hardening.
- The web bundle is already large enough to justify later code-splitting and scale-minded UI work.

## Legacy and Reference Paths
- `src/ui` and other prototype-era UI layers are reference-only.
- `langgraph.md` is workflow architecture reference material, not the top-level governance document.
- Older roadmap/planning docs are historical context only and must not define new implementation work.
