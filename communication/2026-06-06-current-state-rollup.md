# Narrative IDE Current State Rollup

Date: 2026-06-06  
Author: Codex  
Scope: communication folder current-state rollup for the W1 post-smoke / next-wave repair line.

## Current Verdict

The current repo state should be read as follows:

1. Automated zero-cost QA is reported green in `2026-06-06-w7-post-smoke-final-qa-report.md`.
2. The latest P0 checklist is `2026-06-06-w1-import-p0-bug-checklist.md`.
3. The live-smoke/hard-fail boundary is `2026-06-06-w1-live-smoke-runner-and-hardfail-report.md`.
4. The next actionable multi-Claude workflow is `2026-06-06-w1-next-wave-multiagent-claude-plan.md`.
5. The remaining work is structural and should be investigated before coding.

## Canonical Current Communication Docs

| Role | File | Status |
|---|---|---|
| Next-wave execution plan | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | Current single-file prompt package |
| Communication merged evidence | `2026-06-06-communication-merged-evidence-rollup.md` | Current rollup |
| Task completion audit | `2026-06-06-task-completion-audit.md` | Current audit |
| Orchestrator/prompt hardening | `2026-06-06-w1-next-wave-multiagent-claude-plan.md` Section 11 | Merged into current single-file prompt package |
| Human execution guide | `2026-06-06-next-wave-execution-guide-and-solution-architecture.md` | Current execution and solution map |
| P0 checklist | `2026-06-06-w1-import-p0-bug-checklist.md` | Current |
| Live smoke / hard fail report | `2026-06-06-w1-live-smoke-runner-and-hardfail-report.md` | Current |
| Final automated QA report | `2026-06-06-w7-post-smoke-final-qa-report.md` | Current |
| Deep diagnostic flow | `2026-06-06-w1-deep-diagnostic-multiagent-flow.md` | Supporting current plan |

## Automated Evidence Summary

Latest reports claim:

- `npm run ui:build` passes.
- W1 targeted pytest suites pass in the latest automated report layer.
- P1 Playwright is reported green at `151/151`.
- W1 dry-run harness passes and live smoke remains gated.
- Direct 10-chapter runner exists and hard-fails safely under provider/API failure instead of pretending success.

This rollup does not re-run those commands. It records which report currently owns the evidence.

## Remaining Product Risks

| Area | Current state | Next-wave owner |
|---|---|---|
| Chapter / Manuscript | Projection tests exist, but user-reported truncation and Manuscript-vs-Chapter semantics require deeper source-span contract review | Claude W1 |
| W1 Orchestrator | Current W1 is fixed supervisor pipeline plus bounded proposal hooks; next design should be bounded `PlannerProposal`-driven orchestrated pipeline, not fully free agent | Claude W0 + W1 |
| Character model | Background/experience, duplicate text, custom attributes, and route/profile reachability need redesign | Claude W2 |
| Relationships | Free-text relationship labels and graph readability need ontology and layout work | Claude W1 + W2 + W3 |
| Chinese tags | zh user-facing label enforcement must be proven across prompt, reducer, reviewer, and UI | Claude W1 + W2 |
| Timeline undo | Covered regressions are not yet a full command/patch transaction architecture | Claude W3 |
| World Model | Taxonomy repairs exist, but OneNote-like folder tree and stable-ID drag nesting remain incomplete | Claude W3 |
| Right-click | Context menu exists but is not a desktop command registry | Claude W2 |
| Electron acceptance | Browser automation is not enough for final product proof | Claude W4 |
| Communication docs | README, current-state rollup, merged evidence rollup, and task audit now exist; archive moves remain approval-gated | Claude W4 |

## Next Recommended Action

Use `2026-06-06-w1-next-wave-multiagent-claude-plan.md` as the single prompt source after reading the communication index and merged evidence rollup.

Suggested order:

1. Read `communication/README.md`.
2. Read `2026-06-06-current-state-rollup.md`, `2026-06-06-communication-merged-evidence-rollup.md`, `2026-06-06-task-completion-audit.md`, `2026-06-06-orchestrator-design-and-prompt-hardening-addendum.md`, and `2026-06-06-next-wave-execution-guide-and-solution-architecture.md`.
3. Paste W0 Lead Architecture prompt to Claude.
4. Wait for W0 to return baseline, shared-surface matrix, and worker report template.
5. Paste W1, W2, W3, and W4 prompts into separate Claude windows only after W0 freezes scope.
6. Require each worker to submit an Investigation Report before implementation.
7. Merge W1 first, then W2, then W3, then W4 QA/docs.

## Do Not Do Yet

- Do not delete or move old communication reports.
- Do not run live external provider import without explicit user approval.
- Do not treat Chromium Playwright coverage as full Electron acceptance.
- Do not accept shallow fixes that lack root-cause chain, screenshots/artifacts, and tests.
