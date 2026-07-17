# Shared Surfaces

This document defines the high-conflict files and subsystems that require coordination during parallel development.

## Runtime and Transaction Surfaces (2026-07-15)

| Surface | Owners/consumers | Coordination rule |
|---|---|---|
| `sidecar/runtime/agent_runtime.py` and `system/runtime/agent_runtime.db` | Sidecar lifecycle, runtime router, W1 recovery, agentic scheduler | Coordinate schema/migration, lease/fence, event, redaction, and recovery changes. Per-project SQLite WAL metadata only: no graph state blobs or credentials. |
| `sidecar/runtime/checkpointer.py` and `system/runtime/langgraph_checkpoints.db` | W0-W7 workflow modules, sidecar lifecycle | Project-scoped savers must retain serializer safety and be closed through the established lifecycle. |
| `sidecar/routers/runtime.py`, `src/electron/main.js`, `src/electron/preload.cjs`, `src/ui-react/services/electronApi.ts` | Runtime API, IPC bridge, Recovery Center | Change endpoints, IPC, cursor, and payloads as one contract. `/workflow/stream` is the current SSE route; polling uses `/runtime/runs/{attempt_id}/events`. |
| `src/ui-react/services/projectTransaction.ts` | Project persistence and proposal-package acceptance | Coordinate WAL/journal manifest versions, recovery semantics, and crash-injection tests. Rename plus journal is not a power-loss guarantee without `fsync`. |
| `src/ui-react/models/project.ts` `ArtifactRef` and `src/ui-react/services/projectService.ts` | W1 artifact production/migration and Workbench acceptance | Keep ArtifactRef v2 root-contained, hash-checked, and lineage/attempt-bound; update migrations and acceptance validation together. |

## Shared Surface Contract
| Surface | Owner role | Why it is shared | Coordination policy |
|---|---|---|---|
| `src/ui-react/store.ts` | Integrator + state owner | Central UI/project state, action inventory, selection model | Do not edit without an explicit task-pack claim and coordination note. |
| `src/ui-react/config/routes.tsx` | Integrator + shell owner | Route inventory and sidebar section source | Route changes must update `PRODUCT_SPEC.md` and the relevant UI docs in the same change. |
| `src/ui-react/i18n.ts` | UI integrator | High churn translation surface used by many tasks | Batch changes after primary feature edits; avoid opportunistic cleanup. |
| `src/electron/main.js` | Desktop/runtime owner | IPC registration and process lifecycle choke point | One workstream at a time should own IPC additions or lifecycle changes. |
| `src/ui-react/services/electronApi.ts` | Desktop/runtime owner | Shared bridge for all Electron/UI contracts | Mirror any IPC change here in the same task; reserve before editing. |
| `src/ui-react/models/project.ts` | Data-model owner | Canonical TypeScript entity shapes used everywhere | Treat as a schema change. Update `DATA_MODEL.md` and call it out in handoff. |
| `src/ui-react/services/projectService.ts` | Persistence owner | Shared canonical storage behavior | Avoid mixing business logic and service changes from unrelated tasks. |
| `sidecar/routers/workflows.py` | Workflow integrator | Entry router for multiple workflows | Queue changes behind one owner or merge serially. |
| `sidecar/models/state.py` | Workflow integrator | Typed state shared across workflows | Reserve before changing; high regression risk. |
| `dev_docs/README.md` | PM/integrator | Global doc registry and precedence | Update only when governance changes, not for every feature detail. |
| `dev_docs/WORKFLOW_STATUS.md` | PM/integrator | Workflow status source of truth | Update only when a workflow status or product gap actually changes. |
| `dev_docs/FRONTEND_BACKEND_CHECKLIST.md` | PM/integrator | Bridge/integration source of truth | Update whenever UI/store/IPC/sidecar mapping changes. |

## Coordination Rules
- Touch shared surfaces only when the task pack explicitly names them.
- Shared-surface diffs should stay narrow and only support the task's owned subsystem.
- If a shared-surface change would unblock multiple workstreams, land it in the smallest possible preparatory task.
- Do not combine schema, routing, and workflow-router edits in one task unless the task pack is explicitly integration-focused.
