# Execution Plan

## Goal
Close the current architecture into a stable, parallel-deliverable product baseline without adding new speculative capabilities.

## Current Execution Priorities
1. Close verified backend workflows that still lack canonical UI surfaces.
2. Strengthen proposal/canonical-data safety in the main product loop.
3. Make publish/export a real deliverable path.
4. Harden sidecar runtime behavior.
5. Keep docs, tests, and agent entry points aligned with the actual repo.

## Ordered Workstreams
| Order | Workstream | Owner role | Primary write scope | Blocked by | Exit criteria |
|---|---|---|---|---|---|
| 1 | WS-06 Test harness and doc consistency hardening | QA/docs owner | `tests/`, `dev_docs/`, repo agent docs | none | canonical docs and test harness are stable enough for parallel work |
| 2 | WS-01 W2 Manuscript Sync UI closure | Writing/workflow owner | writing/manuscript UI + W2 workflow | WS-06 only for doc/test baseline | W2 has a production trigger and regression coverage |
| 3 | WS-02 W0 Orchestrator UI and control surface | Agent/workflow owner | agent UI + W0 workflow | WS-06 only for doc/test baseline | W0 has a production UI and reliable step reporting |
| 4 | WS-03 Proposal acceptance and canonical data safety closure | Workbench/data owner | Workbench + project service | WS-01 and WS-02 can proceed in parallel; no hard blocker | proposal loop is predictable and reference-safe |
| 5 | WS-04 Publish and export closure | Publish/desktop owner | publish UI + export bridge | WS-06 only for doc/test baseline | Markdown/HTML export path is explicit and testable |
| 6 | WS-05 Sidecar runtime hardening | Sidecar/runtime owner | sidecar runtime surfaces | informed by WS-01 and WS-02 runtime findings | restart/lock/status/cancel behavior is production-safe |

## Workstream Exit Criteria
Every workstream is complete only when:
- primary deliverable behavior is implemented
- required regression tests pass
- canonical docs are updated
- shared-surface changes are called out in handoff
- no hidden scope expansion was introduced

## Non-Goals for This Wave
- no new W8+ workflow design
- no speculative multimodal/video expansion
- no full undo/redo history project
- no version control UI work
- no large schema redesigns without a dedicated decision-log entry
