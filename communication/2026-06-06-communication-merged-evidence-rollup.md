# Narrative IDE Communication Merged Evidence Rollup

Date: 2026-06-06  
Author: Codex  
Scope: merge the useful evidence from older `communication/` reports into a compact reading layer without deleting provenance files.

## Verdict

The previous cleanup created an index and a current-state rollup, but it did not actually merge the older reports. This document is the missing merge layer.

Use this document to understand the historical evidence. Use `2026-06-06-w1-next-wave-multiagent-claude-plan.md` for the current Claude handoff.

## Merge Policy

- Old reports are not deleted or moved in this pass.
- Old reports are now treated as `merged-retained` unless the README marks them current.
- When old reports conflict with current docs, prefer the 2026-06-06 current docs and then verify against code/tests.
- Any archive move must be a later explicit `git mv` pass after Lead approval.

## Merged Source Groups

| Group | Source files | Merged status |
|---|---|---|
| 2026-05-31 baseline import/reviewer plans | `2026-05-31-w1-import-industrial-report.md`, `2026-05-31-w1-import-test11-delivery-report.md`, `2026-05-31-w1-reviewer-organizer-multiagent-plan-prompt.md` | Superseded by June repair and next-wave plans |
| 2026-06-01 reviewer/organizer integration | `2026-06-01-w1-reviewer-organizer-*.md`, `2026-06-01-w1-lead-integration-*.md` | Merged evidence; retain for schema/provenance |
| 2026-06-01 smoke worker reports A-G | `2026-06-01-worker-a-*` through `2026-06-01-worker-g-*` | Already summarized by 2026-06-02 report; retained because files still exist |
| 2026-06-01 to 2026-06-02 smoke repair closure | `2026-06-01-w1-smoke-*`, `2026-06-02-w1-smoke-*` | Historical closeout; current user defects supersede its PASS verdict |
| 2026-06-04 AI import/frontend wave | `2026-06-04-w1-*`, `2026-06-04-w2-*`, `2026-06-04-w4-*`, `2026-06-04-w5-*` | Merged as implementation evidence and risk register |
| 2026-06-05 post-smoke/fixback wave | `2026-06-05-w1-*`, `2026-06-05-w2-*`, `2026-06-05-w4-*`, `2026-06-05-w5-*`, `2026-06-05-w7-*` | Merged as latest pre-2026-06-06 automated evidence |
| 2026-06-06 current wave | `2026-06-06-*`, `README.md` | Current communication layer |

## Evidence Consolidation

## Detailed Evidence By Historical Wave

### 2026-05-31 Baseline / import_test11

Merged source files:

- `2026-05-31-w1-import-industrial-report.md`
- `2026-05-31-w1-import-test11-delivery-report.md`

Preserved evidence:

- `import_test11` was the earliest durable defect baseline for W1 import quality.
- Historical reports recorded timeline recovery from 0 events to a populated timeline, but also carried branch topology, dangling references, duplicate characters, and blank starter-writing artifacts as unresolved quality risks.
- The reports distinguished zero-cost automated evidence from live quality certification; that boundary still matters for the current 10-chapter smoke gate.

Current interpretation:

- Use these files for historical problem framing only.
- Do not use their acceptance verdict as current truth after later W1/W7 changes.

### 2026-06-01 Reviewer / Organizer Integration Chain

Merged source files:

- `2026-06-01-w1-reviewer-organizer-verification-report.md`
- `2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md`
- `2026-06-01-w1-lead-integration-patch-report.md`
- `2026-06-01-w1-lead-integration-codex-acceptance-addendum.md`

Preserved evidence:

- The chain records a real integration gap: reviewer/organizer helpers existed before every path reliably invoked or displayed them.
- It also records the repair path: single-proposal package UI fixes, reviewer/organizer patching, timeline regression protection, and later Codex acceptance.
- Keep exact command outputs in source reports; this rollup preserves the cause-and-effect chain.

Current interpretation:

- The current next-wave plan must still verify supervisor and legacy paths both invoke organizer/reviewer logic, because later user defects show contract drift is possible.

### 2026-06-01 To 2026-06-02 Smoke Repair Closure

Merged source files:

- `2026-06-01-w1-smoke-repair-lead-data-contracts.md`
- `2026-06-01-worker-a-project-loader-report.md`
- `2026-06-01-worker-b-manuscript-report.md`
- `2026-06-01-worker-c-timeline-report.md`
- `2026-06-01-worker-d-world-hierarchy-report.md`
- `2026-06-01-worker-e-character-repair-report.md`
- `2026-06-01-worker-f-token-cost-report.md`
- `2026-06-01-worker-g-orchestrator-data-architecture-report.md`
- `2026-06-01-w1-smoke-repair-lead-report.md`
- `2026-06-02-w1-smoke-repair-verification-report.md`
- `2026-06-02-w1-smoke-repair-closeout-report.md`

Preserved evidence:

- Closeout reported targeted pytest at `226/226` and the repaired Playwright set green after follow-up.
- Worker A preserved split-file hydration and Chinese chapter sort evidence.
- Worker B added manuscript chapter enrichment, including summary/goal/notes.
- Worker C blocked timeline branch pollution and added source-order/topology tests.
- Worker D normalized world hierarchy and filtered contamination in UI rendering.
- Worker E fixed executable reviewer repair schema and added duplicate/repeated phrase checks.
- Worker F added token/cost ledger plumbing.
- Worker G proposed workflow/data architecture improvements but did not implement them.

Current interpretation:

- This wave explains why several symptoms appeared "fixed" by automated tests, but it does not prove the current user-reported Electron/import quality defects are solved.
- The June 2 report's "merged and deleted" table is treated as historical intent, not current filesystem truth; those files are still present and retained as provenance.

### 2026-06-04 import_test13 Real-Project Defect Repair

Merged source files:

- `2026-06-04-w1-import-test13-defect-repair-report.md`
- `2026-06-04-w1-ai-import-orchestrator-delivery-report.md`
- `2026-06-04-w2-reviewer-organizer-manifest-report.md`

Preserved evidence:

- This wave contains real-project investigation against `import_test13`, not just mocked fixtures.
- It recorded repeated/duplicate chapter and metadata-quality problems, empty/weak timeline branches, reviewer loop gaps, and organizer/prompt-policy defects.
- It introduced or documented sparse prompt policy, manifest revision validation, age-phrase detection, duplicate chapter detection, and snippet-only fact review boundaries.

Current interpretation:

- This wave is important evidence for the current "do not ask the LLM to output full chapters" and "reviewer/organizer must be wired, not just present" requirements.

### 2026-06-04 Frontend Interaction Capability Wave

Merged source files:

- `2026-06-04-w1-worker3-timeline-sync-layout-report.md`
- `2026-06-04-w4-global-undo-report.md`
- `2026-06-04-w5-hierarchical-tags-report.md`
- `2026-06-04-w1-worker6-sidebar-graph-linkage-report.md`

Preserved evidence:

- Timeline frontend/backend consistency work reported dense event label tests, drag-save-reload round trip, and topology preservation.
- Global undo work wrapped many mutations but remained snapshot-based.
- Hierarchical tags work added schema v5 tree behavior and dnd-kit-like drag/drop expectations.
- Sidebar/graph linkage work connected collapsed groups to graph node visibility.

Current interpretation:

- These are partial capability foundations, not sufficient final solutions for the current user issues.
- The current plan must evolve undo from snapshot coverage into transaction/command semantics for timeline drag.
- The current World Model needs stable folder IDs, not only hierarchical tag/tree UI primitives.

### 2026-06-05 W7 QA / Readiness

Merged source files:

- `2026-06-05-w1-w7-integration-readiness-report.md`
- `2026-06-05-w1-import-ai-frontend-final-qa-report.md`
- `2026-06-05-w7-qa-followup-codex-addendum.md`

Preserved evidence:

- W7 reported W1-W6 owned Playwright coverage green and targeted backend suites green.
- The final QA report explicitly stated the first-10-chapter live experiment was not run.
- Later addendum/follow-up material tightened stale fixture status and dry-run coverage.

Current interpretation:

- Automated gates are useful, but not enough for the user's Electron-visible defects.
- Live 10-chapter import remains gated by explicit user approval because it can send manuscript text to an external provider and incur cost.

### 2026-06-05 Post-Smoke Repair Wave

Merged source files:

- `2026-06-05-w1-post-smoke-lead-baseline-dispatch.md`
- `2026-06-05-w1-manuscript-canonical-pipeline-report.md`
- `2026-06-05-w1-manuscript-integration-fixback-report.md`
- `2026-06-05-w2-import-granularity-token-billing-report.md`
- `2026-06-05-w4-world-taxonomy-dragdrop-report.md`
- `2026-06-05-w5-timeline-undo-transaction-report.md`
- `2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md`

Preserved evidence:

- Manuscript pipeline reports established early-write ManuscriptNode behavior and integration fixback details.
- W2 granularity/token billing reports added import presets, extraction toggles, cost model display, and later fixback details.
- W4 world taxonomy/drag-drop report added semantic classification and item drag/drop evidence.
- W5 timeline undo transaction report added transaction-scoped undo tests for timeline interactions.
- The prompt package carries useful hard constraints and merge order, but is superseded by the 2026-06-06 next-wave plan.

Current interpretation:

- This is the most relevant old implementation layer for the current defects.
- Its fixes are foundations; the current user reports prove the next wave must investigate real UI/data state again instead of assuming these reports are sufficient.

### Old Prompt Packages / Dispatch Docs

Merged source files:

- `2026-05-31-w1-reviewer-organizer-multiagent-plan-prompt.md`
- `2026-06-01-w1-reviewer-organizer-lead-plan.md`
- `2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md`
- `2026-06-04-w1-import-ai-frontend-lead-plan.md`
- `2026-06-04-w1-import-ai-frontend-parallel-claude-prompts.md`
- `2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md`

Preserved evidence:

- Root-cause tables.
- Hard constraints.
- Dispatch hashes and merge-order reasoning.
- Acceptance criteria.
- Live-smoke stop rules.

Current interpretation:

- Do not paste these prompts as the current plan.
- Use `2026-06-06-w1-next-wave-multiagent-claude-plan.md` instead.
- If an old prompt has a uniquely useful test or hard constraint, carry that evidence forward into the worker's Investigation Report.

## File Classification Inventory

| File | Classification |
|---|---|
| `README.md` | current-handoff-entry |
| `2026-06-06-w1-next-wave-multiagent-claude-plan.md` | canonical-current prompt package |
| `2026-06-06-current-state-rollup.md` | current rollup |
| `2026-06-06-communication-merged-evidence-rollup.md` | merged evidence rollup |
| `2026-06-06-task-completion-audit.md` | current audit |
| `2026-06-06-w7-post-smoke-final-qa-report.md` | current QA evidence |
| `2026-06-06-w1-import-p0-bug-checklist.md` | current P0 checklist |
| `2026-06-06-w1-live-smoke-runner-and-hardfail-report.md` | current live-smoke boundary evidence |
| `2026-06-06-w1-deep-diagnostic-multiagent-flow.md` | supporting current plan |
| `2026-06-05-w7-qa-followup-codex-addendum.md` | supporting evidence, merged-retained |
| `2026-06-05-w1-import-ai-frontend-final-qa-report.md` | supporting QA evidence, merged-retained |
| `2026-06-05-w1-w7-integration-readiness-report.md` | supporting readiness evidence, merged-retained |
| `2026-06-05-w1-post-smoke-lead-baseline-dispatch.md` | superseded dispatch, merged-retained |
| `2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md` | superseded prompt package, merged-retained |
| `2026-06-05-w1-manuscript-canonical-pipeline-report.md` | supporting evidence, merged-retained |
| `2026-06-05-w1-manuscript-integration-fixback-report.md` | supporting evidence, merged-retained |
| `2026-06-05-w2-import-granularity-token-billing-report.md` | supporting evidence, merged-retained |
| `2026-06-05-w4-world-taxonomy-dragdrop-report.md` | supporting evidence, merged-retained |
| `2026-06-05-w5-timeline-undo-transaction-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w1-import-ai-frontend-lead-plan.md` | superseded dispatch, merged-retained |
| `2026-06-04-w1-import-ai-frontend-parallel-claude-prompts.md` | superseded prompt package, merged-retained |
| `2026-06-04-w1-ai-import-orchestrator-delivery-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w1-import-test13-defect-repair-report.md` | supporting real-project evidence, merged-retained |
| `2026-06-04-w1-worker3-timeline-sync-layout-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w1-worker6-sidebar-graph-linkage-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w2-reviewer-organizer-manifest-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w4-global-undo-report.md` | supporting evidence, merged-retained |
| `2026-06-04-w5-hierarchical-tags-report.md` | supporting evidence, merged-retained |
| `2026-06-02-w1-smoke-repair-verification-report.md` | historical closeout evidence, merged-retained |
| `2026-06-02-w1-smoke-repair-closeout-report.md` | historical closeout evidence, merged-retained |
| `2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md` | superseded prompt package, merged-retained |
| `2026-06-01-w1-smoke-repair-lead-data-contracts.md` | historical contract evidence, merged-retained |
| `2026-06-01-w1-smoke-repair-lead-report.md` | historical lead report, merged-retained |
| `2026-06-01-worker-a-project-loader-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-b-manuscript-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-c-timeline-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-d-world-hierarchy-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-e-character-repair-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-f-token-cost-report.md` | historical worker evidence, merged-retained |
| `2026-06-01-worker-g-orchestrator-data-architecture-report.md` | historical architecture proposal, merged-retained |
| `2026-06-01-w1-reviewer-organizer-lead-plan.md` | superseded prompt package, merged-retained |
| `2026-06-01-w1-reviewer-organizer-verification-report.md` | historical verification evidence, merged-retained |
| `2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md` | historical acceptance evidence, merged-retained |
| `2026-06-01-w1-lead-integration-patch-report.md` | historical implementation evidence, merged-retained |
| `2026-06-01-w1-lead-integration-codex-acceptance-addendum.md` | historical acceptance evidence, merged-retained |
| `2026-05-31-w1-reviewer-organizer-multiagent-plan-prompt.md` | superseded prompt package, merged-retained |
| `2026-05-31-w1-import-industrial-report.md` | historical baseline evidence, merged-retained |
| `2026-05-31-w1-import-test11-delivery-report.md` | historical baseline evidence, merged-retained |

### 1. Chapter And Manuscript

Historical evidence:

- Worker A/B and the 2026-06-02 verification report fixed chapter display, Chinese numeral sorting, starter artifact cleanup, and non-empty chapter summary/goal/notes for new imports.
- The 2026-06-05 manuscript pipeline reports made Writing Studio read canonical manuscript nodes and added normalization on load.
- The 2026-06-05 final QA report still required manual live confirmation for imported manuscript quality.

Current merged conclusion:

- Old fixes focused on UI display and enriched chapter cards, but the current user defect is deeper: the LLM/source-span contract must not ask the model to output full chapter bodies.
- The current design target is: LLM returns `source_start`, `source_end`, `summary`, `beats`, and evidence metadata; chapter body is rebuilt deterministically from raw source spans.
- `Chapter` and `ManuscriptNode` must be different product objects: Chapter is structural source segmentation; ManuscriptNode is the author's writing/outlining projection.

Current owner:

- Claude W1 Backend Import Quality in `2026-06-06-w1-next-wave-multiagent-claude-plan.md`.

### 2. Character Module

Historical evidence:

- Worker E added duplicate-name and repeated-phrase reviewer checks and repair proposals.
- 2026-06-02 verification still found stale import data with duplicate character groups.
- 2026-06-05 QA had automated reviewer checks for repeated age phrases, but live character bio quality remained only partially proven.
- Existing P1 failures in `characters_routes.spec.ts` were explicitly listed as pre-existing in the June 5 QA report.

Current merged conclusion:

- Backend reviewer checks are not enough. The product needs a reachable character profile UI, background/experience fields that actually populate, dedupe/merge UX, route not-found handling, route-selection sync, archive-first delete, and flexible custom attributes.
- Chinese project visible tags must not leak English labels.

Current owner:

- Claude W1 for extraction quality.
- Claude W2 for Character UI, custom attributes, duplicate merge, typed commands, and right-click behavior.

### 3. Relationship Module And Graph

Historical evidence:

- Earlier reports improved relationship graph linkage and sidebar collapse behavior.
- Timeline and graph layout reports added frontend tests for dense timeline/graph cases.
- The current user still reports relationship rows are flat, internal relationship organization is weak, false relationship types appear, and the graph is visually chaotic.

Current merged conclusion:

- Relationship type must be an allowlisted Chinese ontology, not a raw LLM phrase.
- Phrases like `解惑`, `选拔`, and `启明者冷冰冰的师兄` belong in event, note, trait, or evidence fields, not canonical relationship type.
- UI must group/indent relationships by category, direction, counterpart, and status.
- Graph layout should use deterministic cluster/radial/force-lite strategies with label collision handling and reset/auto-layout.

Current owner:

- Claude W1 for ontology and prompt/reviewer normalization.
- Claude W2 for relationship list/group UI and commands.
- Claude W3 for graph layout algorithms.

### 4. Tags And Chinese Localization

Historical evidence:

- June 4/5 tag work introduced hierarchical tag trees and drag/drop, but it did not fully prove that imported Chinese novels never surface English tags.
- Current reports mention zh leakage as a warning-level risk in some paths.

Current merged conclusion:

- For zh novel imports, user-visible tags, traits, relationship labels, and world labels must be Chinese.
- English default labels are a failure unless they are raw source evidence or internal enum values hidden from the user.
- W2 UI acceptance must explicitly inspect visible chips/badges/relationship labels, not only backend warnings.

Current owner:

- Claude W1 for prompt/reducer/reviewer language policy.
- Claude W2/W4 for UI-visible zh acceptance.

### 5. Undo / Timeline Drag

Historical evidence:

- June 4 global undo implemented snapshot-based undo/redo with many mutations wrapped.
- June 5 timeline undo transaction report moved timeline drag toward transaction APIs and required a single undo entry for drag.
- Current user still reports dragging an event breaks undo.

Current merged conclusion:

- Snapshot-based undo is insufficient for editor-like timeline/graph interactions.
- Timeline drag must capture `before` on pointerdown, stage changes during drag, commit one transaction on pointerup, and cancel cleanly on Esc/pointercancel.
- Undo must restore position, branch/order, and persistence as one operation without reverting unrelated import/workbench state.

Current owner:

- Claude W3 World / Timeline / Graph Algorithms.

### 6. World Model

Historical evidence:

- Worker D added world hierarchy normalization and render filtering for contaminated containers.
- June 4 hierarchical tags introduced drag/drop for tag trees.
- June 5 world taxonomy repair added classification and item drag/drop tests.
- Reports still admitted `parentId` and `categoryPath` weaknesses, including grouping by display strings and `parentId` reset/null cases.

Current merged conclusion:

- User-visible top-level `category` must be removed from the mental model.
- The World Model should behave like a notebook/folder/item tree with stable IDs.
- `categoryPath` is compatibility metadata only. Organizer output should target stable folder IDs.
- Items like `七仙门十三处兽卡` should route by semantic type, not by arbitrary `categoryPath[1]`.
- Timeline and character/concept data must not appear under World Model unless intentionally linked.

Current owner:

- Claude W3 for folder-tree data structure, drag nesting, persistence, cycle prevention, and world undo.
- Claude W4 for QA and docs.

### 7. Right-Click And Desktop Commands

Historical evidence:

- Current right-click probes found no useful `global-context-menu` on Characters, World, Timeline, or Relationship Graph.
- `ContextMenu.tsx` is only a lightweight list of labels/actions, not a desktop command system.

Current merged conclusion:

- The app needs a typed command registry, not one-off menus.
- Command surfaces must share `AppCommand`, `CommandContext`, and typed clipboard logic.
- Object-specific right-click menus should cover new, rename/edit, copy, cut, paste, duplicate, move, merge, archive/delete, and open/show actions.
- Long-press/drag interactions must be tested separately from context menu open.

Current owner:

- Claude W2 for Character/Relationship/Command UI.
- Claude W4 for Playwright/Electron evidence.

### 8. QA And Communication Docs

Historical evidence:

- June 2 and June 5 QA reports claimed many automated gates green, but both retained live/manual smoke gaps.
- The June 2 report said some worker reports were merged and deleted; in the current folder those files still exist. Treat this as retained provenance, not as an error to delete now.
- June 5 QA said live first-10-chapter certification was not run because it needs Electron and an API key.

Current merged conclusion:

- Current communication canonical reading order is:
  1. `communication/README.md`
  2. `communication/2026-06-06-current-state-rollup.md`
  3. `communication/2026-06-06-communication-merged-evidence-rollup.md`
  4. `communication/2026-06-06-task-completion-audit.md`
  5. `communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md`
- Do not delete old files in this pass.
- True live 10-chapter import remains gated on explicit approval for external API/content/cost risk.

## Superseded Prompt Packages

These packages are useful for history but should not be pasted as the current Claude plan:

- `2026-05-31-w1-reviewer-organizer-multiagent-plan-prompt.md`
- `2026-06-01-w1-reviewer-organizer-lead-plan.md`
- `2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md`
- `2026-06-04-w1-import-ai-frontend-lead-plan.md`
- `2026-06-04-w1-import-ai-frontend-parallel-claude-prompts.md`
- `2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md`
- `2026-06-05-w1-post-smoke-lead-baseline-dispatch.md`

Current replacement:

- `2026-06-06-w1-next-wave-multiagent-claude-plan.md`

## Preserved Unique Evidence

Keep the old files reachable because they contain details not fully repeated here:

- Exact command outputs from June 2 and June 5 verification.
- Worker-owned path matrices and conflict matrices.
- Sample JSON snippets for manuscript, reviewer reports, organizer output, token ledger, and prompt policy.
- Historical Playwright failure classifications.
- Manual Electron smoke checklists.
- Previous implementation reports for rollback/provenance analysis.

## Archive Candidates

These can be moved later only after Lead approval:

| Candidate set | Reason |
|---|---|
| Old prompt packages before 2026-06-06 | Superseded by the current five-window plan |
| June 1 worker reports A-G | Merged by June 2 and this rollup, but still useful as provenance |
| June 4 per-worker delivery reports | Merged by June 5 QA and this rollup |
| June 5 fixback reports | Merged into current state, but preserve until next implementation wave completes |

## Open Risks Carried Forward

| Risk | Current owner |
|---|---|
| Chapter body truncation and source-span contract not implemented yet | Claude W1 |
| Character background/experience empty and duplicate UI text | Claude W1 + W2 |
| English labels in zh visible UI | Claude W1 + W2 + W4 |
| False relationship labels become canonical types | Claude W1 + W2 |
| Timeline event drag undo still user-reported broken | Claude W3 |
| World tree still conceptually category-based in some paths | Claude W3 |
| Context menu is not command-backed | Claude W2 |
| Real Electron acceptance and screenshots still missing | Claude W4 |
