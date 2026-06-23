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

## WS-W1 — AI Import Prompt + Orchestrator Quality
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH on `codex/w1-orchestrated-import-quality`
- Branch: `codex/w1-ai-import-orchestrator`
- Owner role: Sidecar/AI import prompt owner
- Codex review: REQUIRED before execute
- Allowed write scope:
  - `sidecar/prompts/w1_prompts.py`
  - `sidecar/supervisor/planner.py`
  - `sidecar/supervisor/prompt_policy.py`
  - `sidecar/supervisor/tools.py`
  - `tests/test_w1_supervisor_policy.py`, `tests/test_w1_import_compiler.py`
  - New: `tests/test_w1_prompt_policy_selection.py`, `tests/test_w1_manifest_revision_schema.py`
  - `communication/` W1 worker report
- Integration surface (Lead-owned): `sidecar/workflows/w1_import.py` — patch plan to Lead only
- Forbidden: `src/ui-react/**`, `src/electron/**`
- Definition of Done:
  - Zero-cost fixture shows orchestrator policy changes with source profile
  - `prompt_policy_decision.json` generated/simulated in tests
  - Manifest revision schema schema-validated
  - `w1_import.py` patch plan submitted to Lead

## WS-W2 — Reviewer + Organizer + Manifest Repair Loop
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH
- Branch: `codex/w2-reviewer-organizer-manifest`
- Owner role: Sidecar/reviewer owner
- Codex review: REQUIRED before execute
- Allowed write scope:
  - `sidecar/supervisor/reviewers/**`
  - `sidecar/supervisor/organizer.py`
  - `tests/test_w1_reviewers_*.py`, `tests/test_w1_organizer.py`
  - New: `tests/test_w1_reviewer_manifest_revision.py`
  - `communication/` W2 worker report
- Integration surface (Lead-owned): `sidecar/workflows/w1_import.py` — patch plan to Lead only
- Forbidden: `src/ui-react/**`
- Definition of Done:
  - Quality Reviewer local_repair for repeated age phrases in synthetic fixture
  - Quality Reviewer detects duplicate chapter numbers
  - Manifest revision schema-validated in test

## WS-W3 — Timeline Front/Back Consistency + Label Layout
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH
- Branch: `codex/w3-timeline-sync-layout`
- Owner role: Timeline UI owner
- Codex review: REQUIRED before execute
- Allowed write scope:
  - `src/ui-react/components/timeline/**`
  - `src/ui-react/components/TimelineWorkspace.tsx`
  - `tests/e2e/p1/timeline_*.spec.ts`
  - `communication/` W3 worker report
- Shared surfaces by reservation: `src/ui-react/services/projectService.ts` (W3 merges first)
- Integration surface (Lead-approved only): `sidecar/workflows/w1_import.py` timeline schema patch
- Forbidden: Character/World components, `store.ts` beyond timeline slice
- Definition of Done:
  - Playwright timeline drag-persist-reload roundtrip
  - Playwright label layout non-overlapping (30+ events)
  - Complex 4-branch topology preserved after import

## WS-W4 — Global Undo / Redo Transaction System
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH; merge after W3
- Branch: `codex/w4-global-undo`
- Owner role: State/persistence owner
- Codex review: optional before execute; REQUIRED before merge
- Allowed write scope:
  - `src/ui-react/store.ts` (undo stack slice)
  - `src/ui-react/services/projectService.ts` (after W3 merges)
  - `src/ui-react/hooks/**`, shell keyboard handling
  - `tests/e2e/p1/undo_transaction.spec.ts`
  - `communication/` W4 worker report
- Shared surfaces: `store.ts` coordinate with W6; `projectService.ts` rebase on W3
- Forbidden: sidecar import workflow
- Definition of Done:
  - Playwright Ctrl+Z edit→reload restores value
  - Selection changes excluded from undo stack

## WS-W5 — Hierarchical Tags + Windows-like Drag Drop
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH; merge after W4
- Branch: `codex/w5-hierarchical-tags`
- Owner role: Tag/data-model owner
- Codex review: optional before execute; REQUIRED before merge
- Allowed write scope:
  - `src/ui-react/models/project.ts` (tag hierarchy model)
  - `src/ui-react/services/projectService.ts` (after W4 merges)
  - `src/ui-react/components/WorldWorkspace.tsx`, `CharacterWorkspace.tsx` or related
  - `tests/e2e/p1/hierarchical_tags.spec.ts`
  - `communication/` W5 worker report
- Shared surfaces: `project.ts` coordinate with W3/W4; `projectService.ts` rebase on W4
- Forbidden: `sidecar/prompts/**`
- Definition of Done:
  - Playwright 4-level nested tags created and persisted
  - Playwright drag no-cycle enforcement
  - Migration unit test: flat tags → root level

## WS-W6 — Sidebar Collapse + Relationship Graph Linkage
- Status: dispatched 2026-06-04; fork from DISPATCH_HASH; merge after W5
- Branch: `codex/w6-sidebar-graph-linkage`
- Owner role: Graph/sidebar UI owner
- Codex review: optional before execute; REQUIRED before merge
- Allowed write scope:
  - Relationship graph UI components
  - Character sidebar/folder components
  - `src/ui-react/store.ts` graph filter slice (coordinate with W4)
  - `tests/e2e/p1/sidebar_graph_linkage.spec.ts`
  - `communication/` W6 worker report
- Shared surfaces: `store.ts` coordinate with W4; rebase after W4+W5 merge
- Forbidden: `sidecar/workflows/w1_import.py`
- Definition of Done:
  - Playwright core/main filter collapses sidebar and hides graph nodes
  - Relationship data unchanged after filter toggle

## WS-W7 — QA, First-10-Chapter Experiment, and PM Report
- Status: dispatched 2026-06-04; fork from integration branch after W1–W6 merged
- Branch: `codex/w7-qa-experiment-report`
- Owner role: QA/report owner
- Codex review: REQUIRED
- Allowed write scope:
  - `tests/e2e/p1/**` QA specs (read-only unless gap fix needed, Lead approves)
  - `communication/` final PM report
  - `dev_logs/` QA log
- Forbidden: core source files
- Definition of Done:
  - All P0 zero-cost tests pass on integration branch
  - First-10-chapter experiment complete (or documented gap with reason)
  - Final PM report written with per-worker contribution table and acceptance matrix

## Assignment Rule
- Pick one workstream.
- Copy the corresponding pack into a task-specific worktree note using `TASK_PACK_TEMPLATE.md`.
- Do not widen the scope inside implementation. Raise a blocker instead.
