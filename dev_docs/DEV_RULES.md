# NARRATIVE IDE — DEVELOPMENT RULES

This document defines the mandatory operating rules for all agents and humans working in this repository.

These rules are strict. Follow them before, during, and after implementation.

---

# 1. GOVERNANCE ENTRYPOINT

Every session must start with:

1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. task-relevant canonical docs from the Source-of-Truth Registry

Do not guess which doc is canonical. `dev_docs/README.md` decides that.

---

# 2. SOURCE-OF-TRUTH RULE

For UI behavior only, the precedence remains:

1. `UI_logic.txt`
2. `UX_rules.txt`
3. `UI_ROUTES.txt`
4. `TEST_SELECTORS.txt`
5. `TEST_PLAN.md`

For architecture, workflow status, planning, and worktree coordination, use the canonical docs defined in `dev_docs/README.md`.

Reference-only and legacy docs must not define new work.

---

# 3. ACTIVE STACK RULE

The active implementation baseline is:

- `src/ui-react`
- `src/electron`
- `sidecar`

Older paths such as `src/ui` and other prototype-era layers are legacy/reference-only unless the task explicitly says otherwise.

---

# 4. TEST-FIRST DEVELOPMENT

All development must follow this loop:

1. Read `TEST_PLAN.md`
2. Identify the smallest meaningful failing or missing test coverage
3. Implement minimal code changes
4. Run the required checks
5. Fix failures
6. Repeat

P0 and P1 tests must pass before merge or handoff.

---

# 5. UI CONSISTENCY RULES

The shell layout must remain consistent across all pages:

Top Toolbar  
Activity Bar  
Sidebar  
Workspace  
Global Inspector  
Status Bar

Pages may only change workspace content.

---

# 6. SELECTOR RULE

All interactive UI elements must use stable `data-testid` selectors.

Never rely on:

CSS class  
DOM hierarchy  
random attributes

Selectors must follow `dev_docs/TEST_SELECTORS.txt`.

---

# 7. ROUTING RULE

Routes must follow the active route inventory defined by:

- `src/ui-react/config/routes.tsx` for implementation
- `dev_docs/PRODUCT_SPEC.md` for product/module inventory
- `dev_docs/UI_ROUTES.txt` for UI route behavior rules

Every route must render a valid workspace. Invalid entity IDs must show `Entity not found` with a recovery path.

---

# 8. STATE MANAGEMENT

Global UI state must be handled by Zustand.

High-value shared state must not be duplicated in local component state:

selected entity  
current activity/route  
sidebar section  
workspace state  
editor state  
agent/status surfaces

Treat `src/ui-react/store.ts` as a shared surface. Coordinate before editing it in parallel work.

---

# 9. PERSISTENCE AND WORKFLOW BOUNDARIES

UI must not directly read/write canonical storage.

Use:

- `src/ui-react/services/*`
- Electron IPC bridges
- sidecar workflow endpoints

Proposal gatekeeping remains mandatory: AI-originated changes do not silently mutate canonical data.

---

# 10. SAFE REFACTORING

Do not refactor a working module unless:

tests exist  
tests pass before refactor  
tests pass after refactor

If no tests exist, add coverage or keep the refactor out of scope.

---

# 11. DOCUMENTATION UPDATE RULE

Update the canonical docs in the same change whenever you modify:

routes  
selectors  
workflow status  
workflow/UI integration  
core architecture  
worktree operating rules

If a change affects parallel execution, update the relevant docs in:

- `WORKFLOW_STATUS.md`
- `FRONTEND_BACKEND_CHECKLIST.md`
- `PARALLEL_WORKTREE_PROTOCOL.md`
- `WORKSTREAM_BOARD.md`
- `DECISION_LOG.md`

---

# 12. PARALLEL WORKTREE RULE

Parallel work must follow:

- `PARALLEL_WORKTREE_PROTOCOL.md`
- `SHARED_SURFACES.md`
- `TASK_PACK_TEMPLATE.md`
- `WORKSTREAM_BOARD.md`

Every parallel task needs:

goal  
owned paths  
forbidden paths  
required tests  
handoff artifacts

---

# 13. DEVELOPMENT LOG

Every iteration must record:

changes made  
files modified  
tests executed  
test results

Log under `dev_logs/`.

---

# END
