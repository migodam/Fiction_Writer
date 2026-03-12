# Iteration Protocol

## Purpose
This protocol governs all post-reset implementation work for the Narrative IDE architecture. It replaces the older module-last Workbench sequence with a foundation-first delivery model.

## Delivery Phases
1. Specification reset
2. Foundation and persistence
3. Workbench and Agent Dock shell
4. Core authoring loop
5. World and Graph sync loop
6. Deliverable modules
7. QA hardening

## Phase Goals
### 1. Specification Reset
- Keep source-of-truth docs current.
- Resolve conflicts by updating the new doc set first.

### 2. Foundation and Persistence
- Implement project-folder initialization, open, save, and repository boundaries.
- Normalize shell layout, route handling, unread state, and archive behavior.
- Keep dev and test runtime standardized on port `3000`.

### 3. Workbench and Agent Dock Shell
- Build Inbox, History, Issues, and Bulk Actions.
- Reserve the right-side dock for future agent status and tasks.
- Route proposal outputs through Workbench.

### 4. Core Authoring Loop
- Complete Characters, Timeline, and Writing as one shared workflow.
- Keep references many-to-many where required.

### 5. World and Graph Sync Loop
- Complete world containers and world item persistence.
- Complete graph boards, image cards, mixed nodes, and graph-to-workbench sync.

### 6. Deliverable Modules
- Finish Publish export.
- Add first-pass Consistency.
- Upgrade Simulation, Beta Reader, and Insights to polished interactive modules.

### 7. QA Hardening
- Expand selector coverage, deep-link tests, recovery flows, and persistence regression coverage.

## Per-Iteration Order
Every implementation iteration follows this order:
1. Triage
2. Plan
3. Implement
4. Test
5. Debug
6. QA acceptance
7. Log
8. Continue

## Triage Rules
Prioritize in this order:
- P0: app shell, routing, persistence, or test harness broken
- P1: core authoring workflow broken
- P2: module behavior partial or inconsistent
- P3: polish or deferred agent integration

## Planning Rules
Each iteration plan must define:
- bounded target
- concrete files or subsystems
- required tests
- success criteria

## Implementation Rules
- Keep changes reversible and repository-driven.
- React components must not become ad hoc file readers.
- Use stable `data-testid` selectors on interactive controls.
- Do not bypass Workbench for AI-originated changes.
- Do not break project-folder portability.

## Test Rules
After each implementation step, run the smallest meaningful set of tests:
- production build
- module-specific Playwright coverage
- smoke subset for touched navigation or shell paths

## Logging Rules
Each iteration must update:
- `dev_logs/iterations/YYYY-MM-DD/iter_<NN>/devlog.md`
- `dev_logs/iterations/YYYY-MM-DD/iter_<NN>/test_results.md`
- `dev_logs/matrix.json`

Logs must include:
- module or phase target
- changed files
- tests run
- bugs found and fixed
- QA result
- next priorities

## Continue Rule
Continue automatically unless:
- the user stops the session
- all major modules meet the quality gates
- a blocker requires an explicit product decision

## Legacy Note
`dev_agent_logs/iteration.md` remains as a historical reference. This file is the active protocol for future work.
