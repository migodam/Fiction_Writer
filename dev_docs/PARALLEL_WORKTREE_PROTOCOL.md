# Parallel Worktree Protocol

## Purpose
This protocol allows multiple agents and humans to work in parallel without colliding on shared files or redefining product behavior mid-flight.

## Branch and Worktree Naming
- Branch prefix: `codex/`
- Branch format: `codex/<workstream-id>-<slice>`
- Suggested worktree path: `.worktrees/<workstream-id>-<slice>`
- One active task pack per worktree

## Task Assignment Rules
- Every worktree task must map to one task pack from `WORKSTREAM_BOARD.md`.
- Every task pack has one owner role and one primary write scope.
- A task may read anywhere it needs, but it may only write inside:
  - owned paths
  - explicitly granted shared surfaces
- If a task requires a new shared-surface edit, record that claim in the handoff and notify the integrator before coding.

## Write-Scope Ownership
- Owned paths are exclusive for the duration of the task.
- Shared surfaces are not exclusive; they require explicit coordination.
- If two tasks need the same primary file, split the task pack again before implementation.
- Cross-cutting "small cleanup" changes are forbidden unless they are part of the task pack.

## Handoff Expectations
Every completed task must hand off:
- change summary
- exact files changed
- tests run and result
- docs updated
- unresolved risks
- integration notes for any shared surface touched

## Integration Cadence
- Rebase or merge from the latest trunk before final verification.
- Run the task-pack regression tests before handoff.
- Shared-surface edits merge one at a time after integrator review.
- The integrator updates `WORKSTREAM_BOARD.md` and `DECISION_LOG.md` when completion changes the plan for other tasks.

## Conflict Escalation
- If a task is blocked by another task pack, stop and record the blocker instead of improvising a scope expansion.
- If two tasks need the same shared surface, the integrator decides:
  - reservation order
  - whether to split the surface
  - whether to merge one task first and rebase the other
- Product decisions do not get made inside isolated worktrees; record them in `DECISION_LOG.md`.

## Minimum Task-Pack Compliance
Before implementation starts, each task pack must define:
- goal and non-goals
- owned paths
- forbidden paths
- shared surfaces, if any
- prerequisites/dependencies
- acceptance tests
- docs to update
- handoff artifacts
