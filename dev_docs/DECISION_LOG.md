# Decision Log

Use this file for durable project decisions that future agents must inherit.

## Entry Format
| Date | ID | Decision | Rationale | Impact | Supersedes | Status |
|---|---|---|---|---|---|---|

## Entries
| 2026-04-24 | D-001 | The active implementation baseline is `src/ui-react` + `src/electron` + `sidecar`. | These paths match the actual running product and current workflow integrations. | New work targets the active stack; older prototype paths are reference-only unless a task explicitly says otherwise. | — | active |
| 2026-04-24 | D-002 | DevDocs governance is strict-consolidation, English-first. | Multiple conflicting source-of-truth claims were slowing parallel work and causing drift. | Agents must read `dev_docs/README.md` first and follow the registry there. | older scattered source-of-truth claims | active |
| 2026-04-24 | D-003 | Workflow status and workflow integration are split into two docs. | Status and bridge wiring change at different rates and should not share one overloaded source. | `WORKFLOW_STATUS.md` owns status; `FRONTEND_BACKEND_CHECKLIST.md` owns UI/store/IPC/sidecar mapping. | implicit mixed ownership in older docs | active |
| 2026-04-25 | D-004 | Wave 1 integration landed WS-03, WS-01, then WS-02 in that order on `codex/integration-wave1`. | Proposal safety needed to anchor Workbench behavior before the W2 result path and W0 control surface were finalized. | W2 and W0 are now documented as active UI workflows; future work should start from the integrated branch and preserve the resolved shared-surface docs. | — | active |
