# Narrative IDE Communication Index

Last updated: 2026-07-25
Owner: Codex / W4 QA + Communication Merge

This folder is the evidence and handoff layer for Narrative IDE work. It is not the canonical product source of truth. When docs conflict, use `dev_docs/README.md` to identify the winning canonical document, then use the files here as reports, prompt packages, QA evidence, and historical context.

## Start Here

| Status | File | Why it matters |
|---|---|---|
| Current World/Harness closeout | `2026-07-25-world-model-harness-reviewer-redesign-report.md` | Notebook/folder UI, concrete narrative links, semantic reviewer/mover, benchmark reconciliation, Agent Dock, tests, and residual gates. |
| Current Harness research | `2026-07-25-agent-harness-open-source-architecture-research.md` | Public Claude Code/Codex and OneNote architecture references, limits, and the adopted runtime design. |
| W1 package compiler repair | `2026-07-25-claude-code-harness-and-package-compiler-report.md` | Official Claude Code public-Harness research, package graph v2 root cause/fix, and Import Text 18 acceptance evidence. |
| Current implementation truth | `2026-07-15-agent-runtime-resilience-and-recovery-report.md` | Durable runtime, recovery, Time Travel, real-fixture acceptance, paid recovery outcome, human gate, and final test matrix. |
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

## Current Verdict

- The 2026-07-25 World Model/Harness wave adds stable Notebook/Folder/Item ownership, semantic
  relocation review, accepted-project reconciliation, and a normalized Agent execution surface.
  PM closeout: `2026-07-25-world-model-harness-reviewer-redesign-report.md`.
- The 2026-07-14 accepted-project audit improved from 1 error/19 warnings to 0/0 after offline
  reconciliation: 9 event-scene links, 13 event-world links, 7 scene-world inverse links, 10
  high-confidence reclassifications, and 2 quarantined candidates.
- Concrete World-to-event timeline deep links are committed and verified in Playwright and an
  actual 1280px browser pass: the event title/time/branch banner and centered focus ring are visible.
- Previous 2026-07-21 active W1/runtime regression: 817 passed. Full-repo pytest additionally reported 842
  passes plus 11 failures and 7 errors isolated to reference-only V2/V3 `src/core` tests and
  their missing `tests/api_key.txt`; those are recorded as legacy debt, not hidden.

- The 2026-07-25 package-compiler gate passes 805 targeted W1/runtime tests, 279 browser P0/P1/smoke tests, 34 focused package tests, UI lint/build, and Electron runtime smoke.
- Import Text 18 completed the authorized DeepSeek V4 Flash 10/10 resume for `$0.014351`. On 2026-07-25 its 108 proposals were recompiled, repaired, accepted, and verified after Electron restart with no additional provider calls or cost. A full pre-acceptance project backup remains available.
- Provider response recovery uses a stable sequence-independent operation key excluding `attemptId`, project-local `0700`/`0600` content-addressed artifacts, verified cross-attempt reuse, per-process singleflight, human-gated unknown outcomes on cache and network paths, and unique-operation usage-ledger rebuilds without session double counting.
- The previous 2026-07-21 baseline included Electron runtime smoke and the broader P0/P1 suite.
  That wave verified UI lint/build, 817 active W1/runtime tests, the complete 276-test P0/P1
  Playwright suite, timeline drag stability, and a headed Electron actual-fixture run covering
  package acceptance, restart persistence, and interrupted-run recovery. The deterministic
  Electron runtime smoke also passed after rerunning outside the network-restricted sandbox.
- Final Flash artifact `/tmp/.../20260713_033431` passes every extraction and semantic gate except the now-fixed 张铁 serializer boundary. Exact production-code replay passes diagnostics with every symptom flag false.
- Six ledger-backed Flash runs cost `$0.439420`. One Pro attempt was stopped after 12 minutes with zero settled calls/tokens/cost because provider latency made completion inside the 30-minute gate impossible.
- The previous reviewer-ready W1 baseline was merged through PR #2. The 2026-07-25 World/Harness
  wave remains on `codex/agent-runtime-resilience` until its final Git/push gate.
- Existing reports are retained as provenance. Older worker reports and prompt packages are `merged-retained`, not deleted. Do not move or archive old communication files without Lead approval.

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
| W4 undo / world taxonomy | `2026-06-05-w4-world-taxonomy-dragdrop-report.md` | `2026-06-04-w4-global-undo-report.md`, `2026-06-05-w5-timeline-undo-transaction-report.md` |
| W5 hierarchy / tags | `2026-06-04-w5-hierarchical-tags-report.md` | `2026-06-06-w1-import-p0-bug-checklist.md` |
| W7 QA | `2026-06-06-w7-post-smoke-final-qa-report.md` | `2026-06-05-w7-qa-followup-codex-addendum.md` |
| Multi-Claude prompts | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | Single file to copy from; older prompt packages listed below as superseded |
| Communication merge | `2026-06-06-communication-merged-evidence-rollup.md` | `2026-06-06-task-completion-audit.md`, this README |
| Orchestrator design | `2026-06-06-orchestrator-design-and-prompt-hardening-addendum.md` | `sidecar/supervisor/policy.py`, `planner.py`, `planner_llm.py`, `tool_registry.py` |
| Execution guide | `2026-06-06-next-wave-execution-guide-and-solution-architecture.md` | Current answer to how to execute Claude windows and what the solution design is |

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
