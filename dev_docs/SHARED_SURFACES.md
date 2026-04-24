# Shared Surfaces

This document defines the high-conflict files and subsystems that require coordination during parallel development.

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
