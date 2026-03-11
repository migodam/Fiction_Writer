# Narrative IDE — Iteration Protocol

This document defines the execution protocol for every development iteration.

It is the mandatory workflow for all AI agents and coordinators after bootstrap is complete.

---

# 0. Purpose

The system must be developed through disciplined, test-driven, multi-agent iterations.

Each iteration must:

- choose a bounded scope
- assign work to specialized agents
- implement only the necessary changes
- verify with tests
- perform QA acceptance
- log artifacts
- either continue or escalate

This document prevents:
- context waste
- aimless coding
- repeated architecture drift
- infinite self-check loops
- incomplete UI page generation

---

# 1. Iteration Structure

Each iteration must follow this exact order:

1. TRIAGE
2. PLAN
3. DELEGATE
4. IMPLEMENT
5. TEST
6. DEBUG
7. QA ACCEPTANCE
8. LOG
9. NEXT

Do not skip steps.

---

# 2. TRIAGE

The Coordinator must first determine:

- current module being worked on
- current failing tests
- current user-visible bugs
- current blockers
- whether previous iteration succeeded

Prioritization order:

- P0: app broken / route broken / test harness broken
- P1: core workflow broken
- P2: feature partial or inconsistent
- P3: polish only

Each iteration must address only the top 1–3 issues.

---

# 3. PLAN

The Coordinator must write a concise iteration plan including:

- target module
- concrete tasks
- expected files to modify
- tests to run
- success criteria

This plan must be recorded in:

- dev_logs/iterations/YYYY-MM-DD/iter_<NN>/devlog.md

The plan must be small enough to complete in one iteration.

---

# 4. DELEGATE

The Coordinator must assign sub-agent tasks.

Recommended role split:

## Architecture Agent
Checks:
- route correctness
- component boundaries
- store structure
- design system compliance

## UI Implementation Agent
Responsible for:
- page content
- components
- inspector integration
- mock data rendering

## Testing Agent
Responsible for:
- Playwright tests
- selector coverage
- regression protection

## Debugging Agent
Responsible for:
- root cause analysis
- minimal safe fixes
- failure explanations

## QA Acceptance Agent
Responsible for:
- checking UX against specs
- rejecting partial or empty pages
- behaving like a strict user

## Documentation Agent
Responsible for:
- devlog updates
- matrix updates
- known issues updates

The Coordinator should not personally do all work if delegation is possible.

---

# 5. IMPLEMENT

Implementation rules:

- Make minimal reversible changes
- Follow DESIGN_SYSTEM.md strictly
- Use only semantic tokens
- Do not introduce ad-hoc patterns
- Do not leave pages empty
- Always wire mock data if backend is incomplete
- All interactive controls must have `data-testid`

Never implement more than the planned scope.

---

# 6. TEST

The Testing Agent must run the required tests after implementation.

Use Playwright as the primary gate.

Minimum required test categories:

- route and navigation
- sidebar switching
- page rendering
- key CRUD path for current module
- inspector updates
- selector coverage for new interactions

Tests to run should be selected based on module scope.

Do not weaken tests unless the spec itself is wrong.

---

# 7. DEBUG

If tests or UI behavior fail:

The Debugging Agent must produce:

- symptom
- root cause hypothesis
- evidence
- minimal fix
- regression test

For any single failing assertion:
- maximum 3 fix attempts in one iteration

If still failing after 3 attempts:
- record as known issue
- propose next-best path
- move on only if not P0/P1 blocking

---

# 8. QA ACCEPTANCE

The QA Acceptance Agent acts as the strictest user.

Every module/feature must be accepted by QA before it counts as complete.

QA checks:

- page is not empty
- interactions are meaningful
- design system is respected
- inspector updates correctly
- route is stable
- no obvious regression introduced
- required buttons exist and are placed correctly
- workflow matches UI_logic and UX_rules

If QA rejects:
- feature is not complete
- schedule another iteration

---

# 9. LOGGING

Each iteration must update:

## Required
- dev_logs/iterations/YYYY-MM-DD/iter_<NN>/devlog.md
- dev_logs/iterations/YYYY-MM-DD/iter_<NN>/test_results.md
- dev_logs/matrix.json

## Optional
- dev_logs/known_issues.md
- dev_logs/progress_summary.md

Iteration logs must include:

- date/time
- iteration number
- module worked on
- assigned sub-agents
- files changed
- tests run
- bugs found
- bugs fixed
- QA result
- next priorities

---

# 10. Matrix Tracking

`dev_logs/matrix.json` must track project status.

Recommended fields:

- current_module
- completed_modules
- current_iteration
- open_bugs
- known_issues
- selector_coverage
- playwight_status
- qa_status
- backlog

This file is the high-level progress dashboard.

---

# 11. Iteration Success Criteria

An iteration is successful if:

- planned scope is implemented
- relevant Playwright tests pass
- QA accepts the result
- logs are updated

If any of these fail, the iteration is incomplete.

---

# 12. Continue / Stop Rules

Continue automatically unless one of these is true:

- user explicitly says stop
- three consecutive iterations find no new bugs and no remaining major gaps
- all major modules are complete and accepted

Otherwise continue to the next iteration.

Never stop just because one iteration finished.

---

# 13. Command Discipline

Do not enter loops like:

- "Should I run tests?"
- "Should I stop?"
- "Should I lint?"

Instead:

- decide once
- execute
- log result
- continue

If uncertain whether to run a command:
- prefer running the relevant test for the changed module
- skip unrelated commands

---

# 14. Module Completion Rule

A page/module is considered complete only when:

- route works
- sidebar integration works
- workspace content is meaningful
- inspector works
- mock/real data renders
- key actions exist
- tests pass
- QA accepts

---

# 15. Recommended Module-by-Module Execution Order

The project should continue in this order:

1. Characters
2. Timeline
3. Writing Studio
4. Graph
5. World Model
6. Simulation
7. Consistency
8. Beta Reader
9. Publish
10. Insights
11. Workbench

Do not skip ahead unless blocked.

---

# 16. Empty-State Rule

Every page must have a meaningful empty state with:

- title
- explanatory text
- at least one Create button
- at least one AI-assisted action button

No blank panels.

---

# 17. Final Principle

The purpose of this protocol is not speed at any cost.

The purpose is:

- stable iterative delivery
- deterministic development
- strong QA
- architecture consistency
- long-session survivability

All future development must follow this protocol.