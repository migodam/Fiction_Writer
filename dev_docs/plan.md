# NARRATIVE IDE — AI EXECUTION PLAN

This is the primary execution protocol for any AI agent working on this repository.
Goal: produce a stable, commercial-grade Desktop Narrative IDE UI with deterministic behavior and strong automated tests.

This plan is designed for long-running CLI sessions (~1 hour) without dead loops.

---

## 0. Non-Negotiables

- Do NOT modify existing Streamlit app logic. You may reuse interfaces/contracts but must build a new Electron + React UI.
- Windows-only demo target.
- Offline-first: all core features must work without network.
- UI chrome in English; content fields may be CN/EN mixed.
- Tech stack fixed: Electron + React + Zustand + Playwright.
- ALL interactions must use `data-testid` from `dev_docs/TEST_SELECTORS.txt`.
- Follow: `dev_docs/UI_logic.txt`, `dev_docs/UX_rules.txt`, `dev_docs/UI_ROUTES.txt`, `dev_docs/DEV_RULES.md`, `dev_docs/ARCHITECTURE.md`.

---

## 1. Required Working Set (read every session start)

Read these files in order (must be referenced during work):

1. dev_docs/DEV_RULES.md
2. dev_docs/ARCHITECTURE.md
3. dev_docs/UI_logic.txt
4. dev_docs/UX_rules.txt
5. dev_docs/UI_ROUTES.txt
6. dev_docs/TEST_SELECTORS.txt
7. tests/TEST_PLAN.md

If any file is missing, create it with placeholders and stop feature work until present.

---

## 2. Deliverables & Output Artifacts (every iteration)

All iterations must produce:

1) Development log entry  
2) Test run result  
3) Matrix update (progress vs plan)

Store in:

- `dev_logs/iterations/YYYY-MM-DD/iter_<NN>/devlog.md`
- `dev_logs/iterations/YYYY-MM-DD/iter_<NN>/test_results.md`
- `dev_logs/matrix.json` (updated every iteration)

No logs scattered elsewhere.

---

## 3. Iteration Cadence (1 hour session)

Run exactly this loop until time budget ends or P0/P1 are green:

### Iteration Loop (strict)

A) Triage (max 5 min)
- Run tests (or targeted suite) and collect failures.
- Pick top 1–3 highest priority issues (P0 first, then P1).
- Write a short plan with expected files to change.

B) Implement (max 20 min)
- Make minimal code changes.
- Never refactor unrelated areas.

C) Verify (max 10 min)
- Re-run relevant Playwright tests.
- If failing:
  - perform root-cause analysis
  - apply smallest fix
  - re-run
  - stop after 3 attempts for the same failure (see Escalation).

D) Log (max 5 min)
- Update devlog, test_results, matrix.json.

E) Escalation / Next (max 2 min)
- If stuck, open a "Known Issue" ticket entry in the devlog and move on to next priority task.

Hard cap: do not spend > 3 fix attempts on the same failing assertion in a single iteration.

---

## 4. Priority System

Always follow this order:

P0 Blockers (must pass)
- App boot/layout
- Activity navigation (all)
- Sidebar switching
- Characters create/save
- Candidate confirm flow
- Timeline add branch/event
- Timeline drag reorder
- Writing autosave
- Timeline → Writing link
- Global search to entity

P1 Core (next)
- Graph layout persist/reset
- World container + item + dynamic fields
- Workbench run + failure panel
- Consistency run + issue list navigation
- Publish preview + export stub
- Insights metrics visible

P2 Advanced
- Branch drag across tracks
- Context inserts as chips
- Modals/confirm flows
- Keyboard shortcuts

Never implement P2 if any P0 fails.

---

## 5. Architecture Tasks (minimum baseline)

Before implementing features, ensure these exist:

### App shell
- Electron main process (creates window, loads React)
- React layout with fixed regions:
  - TopToolbar
  - ActivityBar
  - Sidebar
  - Workspace
  - Inspector
  - StatusBar

### Routing
- React Router uses `dev_docs/UI_ROUTES.txt`
- All routes render non-empty content.

### Zustand stores (minimum)
- uiStore: currentActivity, currentRoute, sidebarSection, selectedEntity
- projectStore: loaded project metadata, dirty flags, loading/errors
- editorStore: writing buffers, save status

### Persistence (phase 1: JSON)
- Implement repository interface:
  - loadProject()
  - saveProject()
  - CRUD per entity type
- Store files locally (offline), never rely on network.

---

## 6. Playwright Execution Requirements

Every iteration must run Playwright.

### If UI not ready to run tests
- Implement missing `data-testid` first.
- Implement stable seed project/test mode.

### Test mode requirements
- A fixed seed project is loaded for tests.
- Disable animations in test mode.
- Stable deterministic layout.

### Failure policy
When tests fail:
1) Identify if selector mismatch vs behavior bug vs timing flake.
2) Fix the root cause:
   - selector mismatch: align to TEST_SELECTORS
   - behavior bug: fix state/routing/persistence
   - timing: add deterministic waits (avoid arbitrary timeouts)
3) Re-run.

Never change tests to "make it green" unless tests are incorrect relative to dev_docs specs.

---

## 7. Debugging Protocol (no dead loops)

Use this structured debugging flow:

1) Reproduce with the smallest test.
2) Collect signals:
   - console logs
   - app errors
   - React error boundaries output
   - persistence read/write traces
3) Hypothesis:
   - state bug
   - routing bug
   - persistence bug
   - selector mismatch
4) Apply minimal fix.
5) Verify with tests.
6) If 3 attempts fail:
   - write Known Issue + suspected root cause + next experiment
   - deprioritize and continue other tasks

Never stay stuck on one issue for > 30 minutes.

---

## 8. Logging Spec

### devlog.md template
Include:
- Iteration number and timestamp
- Goal (1–3 items)
- Files changed
- Summary of changes
- Why this was the minimal fix
- Known Issues discovered
- Next steps

### test_results.md template
Include:
- Commands run
- Passed/failed tests list
- Links/paths to traces/screenshots

### matrix.json schema (append/update)
Track:
- P0/P1/P2 completion state
- Current failures
- Routes implemented
- data-testid coverage status (rough percentage)
- Last test run timestamp

---

## 9. Feature Growth Policy (prevent scope creep)

Only add new features when:
- It is required to pass P0/P1 tests
- Or it is explicitly listed in dev_docs specs

If a feature idea arises (e.g., "characters should include gender"):
- Create a backlog item in devlog
- Do not implement until P0/P1 stable
- Add it to matrix.json "backlog" list

---

## 10. AI Interaction Constraints (offline-first)

- If any AI/LLM assistance feature is not available offline:
  - implement as stub with clear UX, and a mock provider for tests
- The UI must remain functional without AI.

---

## 11. Completion Criteria (session)

A session is considered successful if:
- All P0 tests pass
- At least 2 P1 tests are implemented and passing
- dev_logs contain complete iteration history
- matrix.json updated and consistent

---

## 12. Questions Policy

If a decision blocks implementation, ask at most 3 questions.
If unanswered, proceed with conservative defaults and document assumptions in devlog.

---

END