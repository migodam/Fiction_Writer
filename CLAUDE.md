# CLAUDE.md

This file provides operational guidance to Claude Code when working in this repository.

## Start Here
Read these before making changes:
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. task-relevant canonical docs from the Source-of-Truth Registry

## Active Stack
- UI: `src/ui-react`
- Desktop/runtime: `src/electron`
- Workflow runtime: `sidecar`

Treat `src/ui` and other prototype-era paths as reference-only unless a task explicitly requires them.

## Commands

```bash
npm install
npm run electron:dev
npm run ui:dev
npm run ui:build
npm run ui:lint
npm run ui:format
npm run test:e2e
```

## Architecture Snapshot
- Electron owns native integration, file dialogs, settings persistence, and sidecar lifecycle.
- React owns shell layout and route-backed workspaces.
- Zustand owns shared UI/project state; `setSelectedEntity(type, id)` is the global selection contract.
- Services own persistence and bridge calls; UI must not touch canonical storage directly.
- Sidecar owns W0-W7 workflow execution and status surfaces.

## Mandatory Rules
- Follow `dev_docs/DEV_RULES.md` exactly.
- Use `dev_docs/WORKFLOW_STATUS.md` for workflow state and `dev_docs/FRONTEND_BACKEND_CHECKLIST.md` for bridge mapping.
- If working in parallel, obey:
  - `dev_docs/PARALLEL_WORKTREE_PROTOCOL.md`
  - `dev_docs/SHARED_SURFACES.md`
  - `dev_docs/TASK_PACK_TEMPLATE.md`
  - `dev_docs/WORKSTREAM_BOARD.md`
- Update canonical docs whenever code changes invalidate them.
- Record changes and test results in `dev_logs/`.

## Git Commit Style
Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
