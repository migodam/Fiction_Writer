# Workstream Board

This board contains ready-to-assign task packs for the next execution wave. Primary write scopes are intentionally non-overlapping. Shared surfaces require explicit reservation per `SHARED_SURFACES.md`.

## WS-01 — W2 Manuscript Sync UI Closure
- Integration status: merged into `codex/integration-wave1` on 2026-04-25.
- Owner role: Writing/workflow owner
- Allowed write scope:
  - `src/ui-react/components/ManuscriptWorkspace.tsx`
  - `src/ui-react/components/WritingWorkspace.tsx`
  - `tests/e2e/p1/` tests for W2 UI flow
  - `sidecar/workflows/w2_manuscript_sync.py`
- Shared surfaces by reservation only:
  - `src/ui-react/services/electronApi.ts`
  - `sidecar/routers/workflows.py`
  - `dev_docs/FRONTEND_BACKEND_CHECKLIST.md`
  - `dev_docs/WORKFLOW_STATUS.md`
- Blocked by: none
- Definition of Done:
  - stable user-facing W2 trigger exists
  - status/proposal flow is visible and documented
  - regression tests added for trigger + status + result path
- Required regression tests:
  - `npm run ui:build`
  - W2-specific Playwright coverage
  - `tests/e2e/p0/navigation.spec.ts`

## WS-02 — W0 Orchestrator UI and Control Surface
- Integration status: merged into `codex/integration-wave1` on 2026-04-25.
- Owner role: Agent/workflow owner
- Allowed write scope:
  - `src/ui-react/components/AgentWorkspace.tsx`
  - `src/ui-react/components/agent/*`
  - W0-specific tests under `tests/e2e/p1/`
  - `sidecar/workflows/w0_orchestrator.py`
- Shared surfaces by reservation only:
  - `src/ui-react/services/electronApi.ts`
  - `sidecar/routers/workflows.py`
  - `dev_docs/FRONTEND_BACKEND_CHECKLIST.md`
  - `dev_docs/WORKFLOW_STATUS.md`
- Blocked by: none
- Definition of Done:
  - canonical UI exists for goal entry, status polling, and permission/result display
  - bridge and workflow docs are updated
  - child-step status behavior is no longer misleading in normal flows
- Required regression tests:
  - `npm run ui:build`
  - orchestrator-specific Playwright coverage
  - `tests/e2e/p0/navigation.spec.ts`

## WS-03 — Proposal Acceptance and Canonical Data Safety Closure
- Integration status: merged into `codex/integration-wave1` on 2026-04-25.
- Owner role: Workbench/data owner
- Allowed write scope:
  - `src/ui-react/components/WorkbenchWorkspace.tsx`
  - `src/ui-react/services/projectService.ts`
  - Workbench safety tests under `tests/e2e/p1/`
- Shared surfaces by reservation only:
  - `src/ui-react/models/project.ts`
  - `src/ui-react/store.ts`
  - `dev_docs/DATA_MODEL.md`
- Blocked by: none
- Definition of Done:
  - proposal accept/reject flow is predictable and documented
  - canonical data updates preserve reference safety
  - unread/history/issue state cleanup is regression-tested
- Required regression tests:
  - `npm run ui:build`
  - proposal/workbench Playwright coverage
  - relevant smoke/navigation checks

## WS-04 — Publish and Export Closure
- Owner role: Publish/desktop owner
- Allowed write scope:
  - `src/ui-react/components/PublishWorkspace.tsx`
  - export-related tests under `tests/e2e/p1/`
- Shared surfaces by reservation only:
  - `src/electron/main.js`
  - `src/ui-react/services/electronApi.ts`
  - `src/ui-react/services/projectService.ts`
  - `dev_docs/PRODUCT_SPEC.md`
- Blocked by: none
- Definition of Done:
  - Markdown/HTML export path is explicit, testable, and documented
  - output expectations and failure states are defined
- Required regression tests:
  - `npm run ui:build`
  - publish/export Playwright coverage
  - shell/navigation smoke where touched

## WS-05 — Sidecar Runtime Hardening
- Owner role: Sidecar/runtime owner
- Allowed write scope:
  - `sidecar/main.py`
  - `sidecar/utils/lock.py`
  - `sidecar/routers/status.py`
  - runtime-focused Python tests
- Shared surfaces by reservation only:
  - `sidecar/routers/workflows.py`
  - `sidecar/models/state.py`
  - `dev_docs/ARCHITECTURE.md`
  - `dev_docs/WORKFLOW_STATUS.md`
- Blocked by: none
- Definition of Done:
  - lock, restart, status, and cancellation ergonomics are improved
  - runtime limitations are either fixed or clearly surfaced in docs/tests
- Required regression tests:
  - targeted Python/runtime tests
  - `npm run ui:build` if bridge/UI touched

## WS-06 — Test Harness and Doc Consistency Hardening
- Owner role: QA/docs owner
- Allowed write scope:
  - `tests/playwright.config.ts`
  - flaky or missing test coverage under `tests/e2e/`
  - `dev_docs/*`
  - repo agent entry docs
- Shared surfaces by reservation only:
  - `src/ui-react/config/routes.tsx`
  - `src/ui-react/i18n.ts`
- Blocked by: none
- Definition of Done:
  - test harness ownership of port/server reuse is reliable
  - canonical docs and entry docs all point to the same governance index
  - docs consistency audit passes
- Required regression tests:
  - `npm run ui:build`
  - `tests/e2e/p0/navigation.spec.ts`
  - `tests/e2e/p1/import_workflow.spec.ts`

## Assignment Rule
- Pick one workstream.
- Copy the corresponding pack into a task-specific worktree note using `TASK_PACK_TEMPLATE.md`.
- Do not widen the scope inside implementation. Raise a blocker instead.
