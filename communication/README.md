# Narrative IDE Communication Index

Last updated: 2026-07-25
Owner: Codex / W4 QA + Communication Merge

This folder is the evidence and handoff layer for Narrative IDE work. It is not the canonical product source of truth. When docs conflict, use `dev_docs/README.md` to identify the winning canonical document, then use the files here as reports, prompt packages, QA evidence, and historical context.

## Start Here

| Status | File | Why it matters |
|---|---|---|
| **Canonical current Harness gate** | `2026-07-25-agent-runtime-harness-reviewer-ready-report.md` | Durable Runtime, recovery/Time Travel, hard budgets, body-free snapshots, package safety, first-canary stall repair, exact remaining user decision, and reviewer gate. |
| Current World/Harness closeout | `2026-07-25-world-model-harness-reviewer-redesign-report.md` | Notebook/folder UI, concrete narrative links, semantic reviewer/mover, benchmark reconciliation, Agent Dock, tests, and residual gates. |
| Current Harness research | `2026-07-25-agent-harness-open-source-architecture-research.md` | Public Claude Code/Codex and OneNote architecture references, limits, and the adopted runtime design. |
| W1 package compiler repair | `2026-07-25-claude-code-harness-and-package-compiler-report.md` | Official Claude Code public-Harness research, package graph v2 root cause/fix, and Import Text 18 acceptance evidence. |
| Historical runtime baseline | `2026-07-15-agent-runtime-resilience-and-recovery-report.md` | Retained 2026-07-21 evidence. Superseded for current canary/reviewer status by the 2026-07-25 canonical Harness gate. |
| Previous reviewer-ready baseline | `2026-07-11-w1-reviewer-ready-orchestrator-report.md` | Pre-resilience W1 outcome, earlier paid-run ledger, residual P2 risks, and Git merge sequence. |
| Current plan | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | Single-file Claude workflow for the next investigation/repair wave; includes execution steps and hardening addendum. |
| Current rollup | `2026-06-06-current-state-rollup.md` | Short index of current verdict, evidence, risks, and next actions. |
| Merged evidence | `2026-06-06-communication-merged-evidence-rollup.md` | Actual compression of older 2026-05-31 to 2026-06-05 reports into durable evidence buckets. |
| Task audit | `2026-06-06-task-completion-audit.md` | One-by-one status check against the user's requested defects and documentation merge requirement. |
| Orchestrator addendum | `2026-06-06-orchestrator-design-and-prompt-hardening-addendum.md` | Historical/supporting addendum. Its required prompt content is now merged into the current plan file. |
| Execution guide | `2026-06-06-next-wave-execution-guide-and-solution-architecture.md` | Human execution steps, Mermaid flow, review gates, and algorithm/frontend/backend/right-click solution map. |
| Current QA truth | `2026-06-06-w7-post-smoke-final-qa-report.md` | Latest automated QA status; zero-cost gates green, live provider smoke still gated. |
| W4 QA + Communication Merge | `2026-06-08-w4-qa-comms-merge-report.md` | W4 investigation report: selector fixes, acceptance matrix, Electron gap analysis, 13-step manual smoke plan, W2 deferred items. |
| Current P0 checklist | `2026-06-06-w1-import-p0-bug-checklist.md` | User-facing defect status and manual smoke checklist. |
| Live smoke / hard fail | `2026-06-06-w1-live-smoke-runner-and-hardfail-report.md` | Direct 10-chapter runner, hard-fail guard, and timeout/token-ledger evidence. |
| Deep diagnostic flow | `2026-06-06-w1-deep-diagnostic-multiagent-flow.md` | Investigation-first multi-agent workflow that led to the next-wave plan. |

## Current Verdict (2026-07-25)

- The canonical current report is `2026-07-25-agent-runtime-harness-reviewer-ready-report.md`.
- Runtime, W1 resume, budget, proposal-gate, package graph, World hierarchy, command/Undo, and Electron recovery hardening have current targeted evidence. The branch is not yet a paid-canary success story.
- The first fresh Flash canary stalled because the old runner bypassed durable RuntimeStore/Harness activity. The repaired runner now persists leases, intents, heartbeats, cleanup, and human-gated unknown outcomes. No successful fresh paid artifact is claimed here.
- A separate legacy Import Text 18 paid-recovery attempt has an unknown provider boundary. It remains a user decision: cancel or authorize one exact retry. It must not be retried automatically.
- Focused post-fix Playwright passed; the complete P0/P1 browser suite must be rerun by the main integration flow. Electron runtime recovery/fork/SSE smoke passed.
- Existing reports remain provenance. Items marked `merged-retained` are not deleted; use their rollup/current report rather than treating every historical conclusion as live truth.

## Status Labels

| Label | Meaning |
|---|---|
| `canonical-current` | Current handoff/QA/plan entry inside `communication/`; this does not override `dev_docs/README.md`. |
| `rollup` | A PM synthesis that lists source docs and preserves unique evidence. |
| `supporting-evidence` | Tests, artifacts, screenshots, implementation reports, acceptance reports, or risk logs. |
| `superseded` | Older plans/prompts that should not be pasted as the current plan. |
| `merged-retained` | Evidence has been compressed into a rollup, but the original file remains for provenance. |
| `archive-candidate` | May be moved later only after Lead approval; no files are in this state yet. |

## Current Workstream Index

| Workstream | Current doc | Supporting evidence |
|---|---|---|
| W1 import quality | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | `2026-06-06-w1-import-p0-bug-checklist.md`, `2026-06-06-w1-live-smoke-runner-and-hardfail-report.md` |
| Durable Agent Runtime / Harness | `2026-07-25-agent-runtime-harness-reviewer-ready-report.md` | `2026-07-25-w1-live-canary-harness-stall-fix.md`, `2026-07-25-runtime-resume-budget-guard.md`, 2026-07-15 baseline report |
| W4 undo / world taxonomy | `2026-06-05-w4-world-taxonomy-dragdrop-report.md` | `2026-06-04-w4-global-undo-report.md`, `2026-06-05-w5-timeline-undo-transaction-report.md` |
| W5 hierarchy / tags | `2026-06-04-w5-hierarchical-tags-report.md` | `2026-06-06-w1-import-p0-bug-checklist.md` |
| W7 QA | `2026-06-06-w7-post-smoke-final-qa-report.md` | `2026-06-05-w7-qa-followup-codex-addendum.md` |
| Multi-Claude prompts | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | Single file to copy from; older prompt packages listed below as superseded |
| Communication merge | `2026-06-06-communication-merged-evidence-rollup.md` | `2026-06-06-task-completion-audit.md`, this README |
| Orchestrator design | `2026-06-06-orchestrator-design-and-prompt-hardening-addendum.md` | `sidecar/supervisor/policy.py`, `planner.py`, `planner_llm.py`, `tool_registry.py` |
| Execution guide | `2026-06-06-next-wave-execution-guide-and-solution-architecture.md` | Current answer to how to execute Claude windows and what the solution design is |
| Import Test 18 quality gate | `2026-07-25-import-test18-quality-regression-and-harness-repair-gate.md` | Durable failure evidence, Pro 50-chapter hold decision, two-compiler Harness repair sequence |

## Superseded Or Historical Prompt Packages

These are retained for provenance but should not be pasted as the current plan unless a Lead explicitly revives them:

- `2026-05-31-w1-reviewer-organizer-multiagent-plan-prompt.md`
- `2026-06-01-w1-reviewer-organizer-lead-plan.md`
- `2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md`
- `2026-06-04-w1-import-ai-frontend-lead-plan.md`
- `2026-06-04-w1-import-ai-frontend-parallel-claude-prompts.md`
- `2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md`
- `2026-06-05-w1-post-smoke-lead-baseline-dispatch.md`

## Historical Evidence Buckets

| Bucket | Files |
|---|---|
| June 1 worker repair reports | `2026-06-01-worker-a-project-loader-report.md` through `2026-06-01-worker-g-orchestrator-data-architecture-report.md`; merged in `2026-06-06-communication-merged-evidence-rollup.md` |
| June 1-2 smoke repair closure | `2026-06-01-w1-smoke-repair-lead-report.md`, `2026-06-02-w1-smoke-repair-closeout-report.md`, `2026-06-02-w1-smoke-repair-verification-report.md`; merged in `2026-06-06-communication-merged-evidence-rollup.md` |
| June 4 AI import/front-end wave | `2026-06-04-w1-ai-import-orchestrator-delivery-report.md`, `2026-06-04-w1-import-test13-defect-repair-report.md`, `2026-06-04-w1-worker3-timeline-sync-layout-report.md`, `2026-06-04-w1-worker6-sidebar-graph-linkage-report.md`, `2026-06-04-w2-reviewer-organizer-manifest-report.md`; merged in `2026-06-06-communication-merged-evidence-rollup.md` |
| June 5 follow-up reports | `2026-06-05-w1-manuscript-canonical-pipeline-report.md`, `2026-06-05-w1-manuscript-integration-fixback-report.md`, `2026-06-05-w1-w7-integration-readiness-report.md`, `2026-06-05-w2-import-granularity-token-billing-report.md`; merged in `2026-06-06-communication-merged-evidence-rollup.md` |

## Archive Policy

1. First pass: index, current-state rollup, merged evidence rollup, and task audit. Do not delete old reports.
2. Second pass, only after Lead approval: optionally move superseded reports into `communication/archive/2026-06/` with `git mv`.
3. Preserve unique test commands, screenshot paths, artifact paths, acceptance tables, and unresolved risks in rollups before any archive move.
4. If a report contains a prompt that was actually pasted to Claude, keep it linked even if superseded.

## Naming Convention

Use:

```text
YYYY-MM-DD-<workstream>-<topic>-<kind>.md
```

Recommended `kind` values:

- `plan`
- `prompt`
- `report`
- `checklist`
- `rollup`
- `addendum`
