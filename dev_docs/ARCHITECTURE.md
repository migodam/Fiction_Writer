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

## Durable Agent Runtime and Harness (2026-07-25)

W1 uses a constrained durable harness rather than an in-memory free-form agent
loop.

```text
React Import Workspace / Agent Dock
  -> Electron IPC -> sidecar workflow/runtime API
  -> RuntimeStore SQLite WAL (run, attempt, lease, event, decision, receipt)
  -> bounded planner + registered tools + W1 supervisor
  -> intent before provider/cache I/O
  -> artifact receipt + checkpoint
  -> semantic coverage + compiled package graph
  -> explicit human proposal gate -> single-writer canonical transaction
```

- `system/runtime/agent_runtime.db` is the authoritative control ledger for
  lineage/run/attempt identity, leases/fencing, durable event sequence, tool
  intents/results, receipts, human decisions, and checkpoint metadata. W1 graph
  checkpoints are persisted separately.
- Electron remains the only native bridge. React reaches runtime state through
  services, IPC, and API endpoints; it never opens the runtime DB.
- Planner/Self-Ask/ReAct behavior is bounded by registered typed tools,
  budget/time/step limits, deterministic validators, and a single-writer
  proposal/canonical boundary. Agents exchange durable artifacts, not shared
  memory objects.
- Recovery validates source/config/artifacts/snapshot/parent-chain and creates
  a child attempt. A running parent cannot be forked. Accepted canonical data is
  never silently changed by Time Travel.
- Provider calls are intent-first and receipt-backed. Ambiguous interruption is
  `unknown_outcome`, requiring an exact human decision before one retry or
  cancellation. API keys, prompts, source bodies, and hidden reasoning are not
  persisted in the runtime ledger or resumable snapshot.

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
- Renderer Node access is disabled (`nodeIntegration: false`) and the renderer runs with context isolation enabled.
- `src/electron/preload.cjs` exposes only named bridge capabilities used by `src/ui-react/services/electronApi.ts`; it never exposes `ipcRenderer`, generic `invoke`, or generic `send` access.
- Main-process IPC validates local project roots before filesystem/sidecar operations and keeps DB table/entity checks within the existing allowlist contract.

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
- Complete P0/P1 browser regression must be rerun after the final UI changes;
  focused tests and Electron runtime smoke are not a replacement.
- A fresh-project Flash 10-chapter canary must complete and stop at proposal
  gate before any larger/Pro run. A legacy unknown provider outcome remains an
  explicit human cancel/retry decision.
- Headed Electron user-project package acceptance with reviewer quarantine is
  still a manual/production validation boundary.
- Publish/export is present as a workspace but not yet a fully closed delivery subsystem.
- The web bundle is already large enough to justify later code-splitting and scale-minded UI work.

## Legacy and Reference Paths
- `src/ui` and other prototype-era UI layers are reference-only.
- `langgraph.md` is workflow architecture reference material, not the top-level governance document.
- Older roadmap/planning docs are historical context only and must not define new implementation work.
