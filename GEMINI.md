# GEMINI.md

This file provides operational guidance to Gemini-style coding agents working in this repository.

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

## Operating Principles
1. Privacy-first and local-first still apply, but the active product is an Electron/React desktop app with a Python sidecar.
2. Canonical product/workflow behavior comes from `dev_docs`, not from historical prototype assumptions.
3. Workflow status lives in `dev_docs/WORKFLOW_STATUS.md`.
4. UI/store/IPC/sidecar mappings live in `dev_docs/FRONTEND_BACKEND_CHECKLIST.md`.
5. Parallel work must follow the worktree docs in `dev_docs/`.

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

## Git Commit Style
Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
