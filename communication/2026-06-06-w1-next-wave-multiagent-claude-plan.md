# Narrative IDE Next-Wave Multi-Agent Claude Plan

Date: 2026-06-06  
Author: Codex Lead  
Purpose: package the next repair wave into a deep multi-Claude workflow. This is not a shallow bug prompt. Each Claude window must investigate, design, write an implementation prompt, and pass Lead review before coding where required.

Single-file usage:

- This file is now the only file you need to copy from for Claude execution.
- Do not separately paste the old hardening addendum. Its required content is merged into this file.
- Start with W0. Paste Section 5 only. The W0 hardening block is already merged into Section 5.
- In Claude Code, use `/plan` first for every W0-W4 window. The plan must explicitly list which skills/plugins it will use before any investigation or implementation.
- After W0 returns its Architecture Contract, ask Codex/human to review it.
- Only after W0 review passes, open W1/W2/W3/W4 Claude windows and paste their corresponding sections. The required hardening instructions are merged into the relevant copy blocks.
- Every worker must first return an Investigation Report and Implementation Prompt. Do not let workers immediately code unless the review rules in this file say they can.

---

## 0. Executive Summary

### 0.1 User Intent To Preserve

Claude must read this as a product-quality mandate, not as a narrow bug ticket.

The user is building a Chinese novelist's desktop IDE. They are not asking for small UI patches. They want the system to understand imported novels, preserve source text, organize characters/world/relationships like a serious writing tool, and support normal desktop operations such as right-click, copy/cut/paste, drag/drop, merge, archive, and undo.

The user's original quality complaints are:

1. Chapter splitting is wrong: the LLM must not output full chapter bodies because it wastes tokens and can truncate the novel. It should output spans/metadata; the app should reconstruct chapter body from raw source.
2. Manuscript and Chapter are currently indistinguishable. Chapter should be source structure; Manuscript should be the author's editable/outlining projection.
3. Character module is weak: Han Li's background/experience is empty, profile text duplicates, custom attributes are missing, dedupe/merge is incomplete, and right-click does nothing useful.
4. Relationship module is weak: relationship rows are flat, relationship graph is messy, and phrases such as `解惑`, `选拔`, `启明者冷冰冰的师兄` must not become relationship types.
5. Chinese project labels must be Chinese. English tags/traits/relationship labels in a Chinese novel are a failure unless they are hidden internal enum keys.
6. Timeline undo is broken after dragging events. Drag must become one undoable transaction, not scattered snapshots.
7. World Model is conceptually confused. User-visible `category` should disappear. World data should behave like a stable notebook/folder/item tree with valid drag nesting.
8. Right-click and overall operation logic must be designed as a real desktop command system, not ad hoc callbacks.
9. Claude workers must investigate, think, design algorithms/data structures/frontend/backend changes, write their own implementation prompts, and improve/refactor code when architecture is the problem.
10. Reports must include evidence: screenshots, code paths, artifacts, tests, root-cause chains, subagent decision traces, and must-fail acceptance boundaries.

Every Claude worker must preserve this intent. If a proposed fix only adds a button, adjusts a label, or patches one prompt without addressing data flow, evidence, and user workflow, it should be rejected.

The current post-smoke failures are structural, not cosmetic:

| Area | User-visible defect | Required response |
|---|---|---|
| Chapter / Manuscript | Chapter body appears truncated; Manuscript and Chapter are indistinguishable | Rebuild the import text contract around source spans and deterministic body reconstruction |
| Characters | Han Li background/experience empty; duplicate profile text; no flexible attributes | Fix extraction contract, schema/UI reachability, dedupe, and custom attributes |
| Relationships | False relation labels such as `解惑`, `选拔`, `冷冰冰的师兄`; graph is hard to read | Add relationship ontology, demotion rules, grouped UI, and graph layout algorithms |
| Tags | Chinese novel imports show English character tags | Enforce zh user-facing labels in prompts, reducers, reviewers, and tests |
| Undo | Timeline drag breaks undo or rolls back too far | Move from snapshot patchwork toward transaction/command semantics |
| World Model | Visible `category` model is confusing; hierarchy and drag nesting do not match file/folder mental model | Use stable notebook/folder/item IDs and treat `categoryPath` as compatibility metadata only |
| Right-click | Electron app has no coherent desktop context-menu behavior | Build typed command registry, typed clipboard, and menu matrix by object/surface |
| Communication docs | Too many dated reports with no index or superseded policy | Add README/index and rollups; do not delete history first |

Use five Claude windows, including Lead:

| Window | Scope | Merge order | Review before coding |
|---|---|---:|---:|
| W0 Lead Architecture | Baseline, ontology, orchestrator architecture decision, shared-surface ownership, merge gate | Coordination only | Required |
| W1 Backend Import Quality | Chapter/manuscript, bounded orchestrated import planner, characters/tags, relationships, reviewer/organizer | 1 | Required |
| W2 Character / Relationship / Command UI | Character profile, custom attributes, merge UX, command registry | 2 | Required if schema/ontology changes |
| W3 World / Timeline / Graph Algorithms | World tree, timeline undo, graph layout | 3 | Required |
| W4 QA + Communication Merge | Electron/Playwright acceptance, docs index/rollup | 4 / final QA | Required for world schema and archive/delete |

---

## 1. Codex Lead Facts To Preserve

### Repo baseline facts

- Current checkout observed by Codex/subagents: `codex/w1-orchestrated-import-quality`, ahead of origin by many commits and with dirty tracked/untracked files.
- Target output file did not exist before this plan.
- Initial Codex observation found `communication/` had many dated reports and no index. This cleanup now adds `communication/README.md`, `2026-06-06-current-state-rollup.md`, `2026-06-06-communication-merged-evidence-rollup.md`, and `2026-06-06-task-completion-audit.md`; Claude W4 must verify and extend them rather than assuming docs are still unindexed.
- Active implementation stack remains `src/ui-react`, `src/electron`, and `sidecar`; legacy `src/ui` is reference-only.
- Current governance requires reading `dev_docs/README.md`, `dev_docs/DEV_RULES.md`, and task-relevant canonical docs before edits.

### Frontend evidence already observed

Codex Playwright browser probes against Vite showed:

- `/characters`, `/world`, `/timeline/timeline`, and `/characters/relationship-graph` render, but right-click probes did not reveal `global-context-menu`.
- `ContextMenu.tsx` is only a light `{ id, label, action, destructive }` renderer, not a command system.
- Character profile route currently shows only a thin Profile tab in the normal path; richer fields are effectively unreachable.
- `/writing/manuscript` starter project still says no chapters, so imported-project visual acceptance must be checked separately.

### Backend evidence already observed

Subagent read-only inspection found:

- Supervisor extraction appears to rebuild prompt text from `chunk["content"]`, while manuscript persistence uses `manuscript_content`; this can split the source-of-truth for extraction vs manuscript body.
- `node_organize_project` exists, but supervisor tool registry exposes `reduce_world_entities`, not a full organizer lifecycle tool.
- Relationship synthesis preserves evidence-backed free-text labels, so action/description labels can survive as canonical relationship types.
- zh leakage is detected as a warning in some QA paths, but tag classification must be checked for source-language policy injection.

### Shared surfaces

Treat these as serial merge surfaces:

| Surface | Primary owner | Notes |
|---|---|---|
| `sidecar/workflows/w1_import.py` | W1 | No UI worker edits |
| `sidecar/routers/workflows.py` | W1 + Lead | Bridge/status only with Lead approval |
| `sidecar/models/state.py` | W1 + Lead | Schema/state contract, serial review |
| `src/ui-react/models/project.ts` | W2/W4 with Lead | Schema changes must update `DATA_MODEL.md` |
| `src/ui-react/store.ts` | W3 primary | W2/W4 may submit patch plans, not uncoordinated edits |
| `src/ui-react/services/projectService.ts` | Lead serial merge | Persistence changes from W1/W3/W4 must not overlap blindly |
| `src/ui-react/services/electronApi.ts` | W1 or W3 only if bridge changes | Update bridge docs if touched |
| `src/ui-react/i18n.ts` | Batch after UI changes | Avoid unrelated translation churn |
| `communication/` | All write reports; W4 owns index | No delete/move without Lead approval |

---

## 2. Required Claude Skill Usage

All Claude windows:

- `superpowers:using-superpowers`
- `superpowers:brainstorming`
- `superpowers:systematic-debugging`
- `superpowers:subagent-driven-development`
- `superpowers:writing-plans`
- `superpowers:verification-before-completion`

Implementation windows:

- `superpowers:using-git-worktrees`
- `superpowers:test-driven-development`
- `superpowers:requesting-code-review`
- `superpowers:receiving-code-review`

Frontend/interaction windows:

- `frontend-design:frontend-design`
- `playwright MCP`
- `context7 MCP`
- `brave-search MCP`
- `typescript-lsp`

Docs/QA window:

- `claude-md-management:claude-md-improver`
- `investment-master` may be used only for PM-style synthesis. It must not replace engineering verification.

External references Claude must re-check and cite in its reports:

- Scrivener Binder, custom metadata, and character sketch/reference workflow.
- novelWriter chapter/scene/manuscript/outline workflow.
- React Flow docs for `EdgeLabelRenderer` and custom edge labels.
- dnd-kit docs for sortable trees, multiple containers, collision detection, keyboard-accessible drag/drop.
- Command-pattern or transaction-based undo/redo patterns for graph/desktop editors.

---

## 3. Global Worker Protocol

Every Claude worker must produce an Investigation Report before coding.

Required report template:

```markdown
# Worker X Investigation Report

## Product Intent
What creator workflow this module should support.

## Current Behavior Evidence
- UI screenshot path:
- Artifact path:
- Storage path:
- Code path:
- Reproduction command:

## Root Cause Chain
1. User-visible symptom
2. UI state / behavior
3. Stored project data
4. Backend / prompt / reviewer / persistence source
5. Why previous tests or fixes did not catch it

## External References
- Brave Search findings:
- Context7 docs:
- Playwright screenshots:
- Frontend design notes:

## Proposed Architecture
- Data structure:
- Algorithm:
- Frontend interaction:
- Backend pipeline:
- Prompt / reviewer changes:

## Rejected Alternatives
- Alternative:
- Why rejected:

## Implementation Prompt Draft
The worker writes the next Claude prompt here.

## Acceptance Criteria
- Unit tests:
- Backend tests:
- Playwright:
- Electron/manual smoke:
- Must not pass if:
```

Lead should reject reports that:

- have no real screenshot, artifact, storage, or code evidence;
- only add UI buttons without command/data path;
- keep LLM-generated full chapter bodies as canonical text;
- keep `categoryPath` as the primary World Model structure;
- add more snapshot special-cases instead of a transaction model;
- write reviewer reports with no repair/apply path;
- lack failing tests or acceptance scenarios;
- skip required external reference research.

---

## 4. Window Compression Strategy

Do not open 10-11 Claude implementation windows. Compress into 5:

| Original needs | Compressed owner |
|---|---|
| Chapter split, manuscript semantics, import granularity, token/billing surface if needed, reviewer/organizer, prompt quality | W1 Backend Import Quality |
| Character background/experience, custom attributes, duplicate/merge, relationship organization, right-click command registry | W2 Character / Relationship / Command UI |
| World folder tree, drag nesting, timeline undo, relationship graph algorithm | W3 World / Timeline / Graph Algorithms |
| Electron/Playwright proof, screenshot acceptance, communication README/rollups | W4 QA + Communication Merge |
| Baseline, shared-surface arbitration, merge order, review gate | W0 Lead Architecture |

Merge order:

1. W0 freezes the contract; no coding.
2. W1 lands backend contracts first.
3. W2 lands entity and command UI after W1 source/ontology contracts are stable.
4. W3 lands algorithmic state changes after W2 claims are known.
5. W4 lands docs/QA after integration gates pass.

---

## 5. Copy Prompt: Claude W0 Lead Architecture

```text
## W0 Lead Architecture Section - Baseline, Ownership, Merge Gate

You are W0 Lead Architecture for Narrative_IDE. This is a read-first architecture and coordination window. Do not implement feature code.

Repository:
/Volumes/migodam's-external-brain/Development/Narrative_IDE

Goal:
Compress the current 10-11 post-smoke work requests into five Claude windows while preventing shared-surface collisions and shallow symptom fixes.

Start:
0. Use Claude Code `/plan` first. In the plan, explicitly list the skills/plugins you will use:
   - superpowers:using-superpowers
   - superpowers:brainstorming
   - superpowers:systematic-debugging
   - superpowers:subagent-driven-development
   - superpowers:writing-plans
   - superpowers:verification-before-completion
   - context7 MCP if inspecting library/framework docs
   - brave-search MCP if using external product/UX references
   - playwright MCP if verifying UI behavior
   Do not begin implementation; W0 is architecture-only.
1. Run:
   - git status --short --branch
   - git log --oneline -12
   - git worktree list --porcelain
2. Record:
   - current branch
   - current HEAD as BASELINE_HASH
   - dirty tracked files
   - untracked files
   - recent communication reports inspected
3. Read:
   - communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md Section 0.1 User Intent To Preserve
   - dev_docs/README.md
   - dev_docs/DEV_RULES.md
   - dev_docs/PARALLEL_WORKTREE_PROTOCOL.md
   - dev_docs/SHARED_SURFACES.md
   - dev_docs/WORKSTREAM_BOARD.md
   - communication/2026-06-06-w1-import-p0-bug-checklist.md
   - communication/2026-06-06-w1-live-smoke-runner-and-hardfail-report.md
   - communication/2026-06-06-w7-post-smoke-final-qa-report.md
   - communication/2026-06-06-w1-deep-diagnostic-multiagent-flow.md

Lead decisions to produce:

1. Freeze baseline:
   - Declare BASELINE_HASH and whether workers fork from it or from a cleaned integration commit.
   - No worker may start coding until owned paths, forbidden paths, shared-surface claims, and tests are written down.

2. Compress windows:
   - W1 Import Pipeline: chapter/manuscript, prompt/reviewer/organizer, character/tag quality, relationship ontology, console activity, live-smoke hard-fail guard.
   - W2 Entities + Graph/Command UI: character model, custom attributes, duplicate merge, Chinese labels, relationship organization, command registry, typed clipboard.
   - W3 World/Timeline/Graph Algorithms: world notebook/folder model, taxonomy repair, drag/drop, undo transactions, relationship graph layout.
   - W4 QA + Docs: Electron acceptance, screenshot protocol, Playwright gap review, communication index and rollup.
   - W0 Lead owns product ontology, merge order, shared-surface arbitration, and review gates.

3. Shared-surface ownership:
   - sidecar/workflows/w1_import.py: W1 only.
   - sidecar/routers/workflows.py and sidecar/models/state.py: W1 only with Lead approval.
   - src/ui-react/models/project.ts: W2/W4 only after schema contract review.
   - src/ui-react/store.ts: W3 primary; W1/W2/W4 must isolate slices and submit patch plan.
   - src/ui-react/services/projectService.ts: W1/W3/W4 serial merge only.
   - src/ui-react/services/electronApi.ts: W1 or W3 only if bridge contract changes.
   - communication/: all workers write reports; W4 may create index; no deletion/move without Lead approval.

4. Mandatory worker protocol:
   Every worker must first write an Investigation Report before any implementation prompt. The report must include:
   - product intent
   - current behavior evidence
   - root cause chain
   - external references / docs used
   - proposed architecture
   - rejected alternatives
   - implementation prompt draft
   - acceptance criteria and tests
   Workers must not code until Lead approves the report when the task touches architecture-critical surfaces.

5. Review-before-coding gates:
   - W1: required.
   - W2: required if schema, relationship ontology, prompt schema, canonical tags, or command registry touch shared surfaces.
   - W3: required.
   - W4: required for world schema/taxonomy; docs consolidation requires approval before archive/delete.
   - QA/live smoke: only after integration gates; no live API/model calls without explicit approval.

6. Merge gate:
   - Merge W1 first, then W2, then W3, then W4 QA/docs.
   - Shared surfaces merge one at a time.
   - Reject workers that mock success without fixing the real path.
   - Required final gates: targeted pytest, npm run ui:build, targeted Playwright, dry-run harness, communication report, unresolved-risk table.

7. Orchestrator architecture review:
   Before approving W1/W2/W3/W4 implementation, perform an explicit orchestrator architecture review.

   User critique to evaluate:
   Current W1 is a fixed LangGraph/policy pipeline plus bounded supervisor rerun loop. It is not a true model-driven orchestrator. A better next step is not a fully free agent, but an orchestrated pipeline where LLM planner/judge proposes bounded strategy and validators/executors enforce safety.

   Read first:
   - dev_docs/W1_IMPORT_COMPILER.md
   - dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md
   - sidecar/workflows/w1_import.py
   - sidecar/supervisor/policy.py
   - sidecar/supervisor/planner.py
   - sidecar/supervisor/planner_llm.py
   - sidecar/supervisor/tool_registry.py
   - sidecar/supervisor/tools.py
   - sidecar/models/state.py
   - tests/test_w1_supervisor_policy.py
   - tests/test_w1_orchestrator_artifacts.py

   Answer these questions with code paths and line references:
   1. Is W1 currently controlled by a fixed stage order in run_supervisor_policy()?
   2. Can any model output directly reorder tools, disable required tools, inject raw prompt text, or bypass proposal gates?
   3. Is tool_registry a real callable registry or a stub?
   4. Is planner_llm.py currently making live model calls?
   5. What exactly happens when llm_planner_mode="live"?
   6. Which planning decisions are already schema-safe in PlannerProposal?
   7. Which decisions should remain deterministic forever?

   Required architecture decision:
   Choose one:
   - A. Keep deterministic-only supervisor.
   - B. Build bounded PlannerProposal-driven orchestrated pipeline.
   - C. Build fully free model-driven ReAct agent.

   Default recommendation is B unless evidence proves otherwise.

   If choosing B, produce:
   - allowed LLM planner decisions;
   - forbidden LLM planner decisions;
   - validator gates;
   - artifact outputs;
   - minimum implementation patch;
   - tests that prove no unsafe dynamic execution is possible.

   Reject any W1 worker prompt that treats "orchestrator" as just another name for the existing fixed pipeline.

Deliverable:
Return a concise W0 Architecture Contract with:
- BASELINE_HASH
- five-window compression table
- shared-surface ownership matrix
- review gates
- merge order
- orchestrator architecture decision
- exact worker Investigation Report template
- explicit "no implementation yet" instruction
```

---

## 6. Copy Prompt: Claude W1 Backend Import Quality

```text
## Claude W1 Backend Import Quality Window

You are the W1 Backend Import Quality Claude window for Narrative_IDE.

Repository:
/Volumes/migodam's-external-brain/Development/Narrative_IDE

Read first:
0. communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md Section 0.1 User Intent To Preserve
0a. Use Claude Code `/plan` first. The plan must name the required skills/plugins for this window and must not start coding until the Investigation Report is approved.
1. dev_docs/README.md
2. dev_docs/DEV_RULES.md
3. dev_docs/W1_IMPORT_COMPILER.md

Use required skills:
- superpowers:using-superpowers
- superpowers:brainstorming
- superpowers:systematic-debugging
- superpowers:subagent-driven-development
- superpowers:test-driven-development
- superpowers:verification-before-completion
- context7 MCP for structured output/schema/library references where useful
- brave-search MCP for extraction/reviewer/LLM repair-loop references where useful

Goal:
Investigate and fix W1 import quality defects without changing UI behavior unless tests prove a backend contract mismatch.

Focus defects:
- chapter truncation / prompt-window splitting
- Manuscript vs Chapter contract divergence
- empty or duplicate character background/experience-like fields
- English user-facing tags/traits/relationship text in zh novels
- false relationship labels: 解惑, 选拔, 冷冰冰的师兄
- supervisor / legacy organizer / reviewer lifecycle gaps

Start by inspecting:
- sidecar/workflows/w1_import.py
- sidecar/supervisor/tools.py
- sidecar/supervisor/policy.py
- sidecar/supervisor/tool_registry.py
- sidecar/supervisor/organizer.py
- sidecar/prompts/w1_prompts.py
- tests/test_w1_prompt_windows.py
- tests/test_w1_supervisor_tools.py
- tests/test_w1_supervisor_policy.py
- tests/test_w1_organizer.py
- tests/test_w1_reviewers_quality.py

Known facts to verify:
- W1 contract says complete normal chapters must be preserved. Only a single oversized chapter may split by paragraph/scene boundary.
- Supervisor extraction may rebuild prompt text from chunk["content"] while manuscript persistence uses manuscript_content.
- node_organize_project exists but supervisor registry may not invoke it before proposal write.
- Relationship synthesis may preserve free-text labels as canonical type.
- zh leakage is likely warning-level only in some QA paths; tag prompt/source-language policy may be incomplete.

Specific questions to answer before edits:
1. Does supervised windowing ever split a normal chapter inside a multi-chapter batch?
2. Does supervisor extraction use the same source text as manuscript persistence?
3. Is node_organize_project actually invoked in supervisor mode before world proposals?
4. Are manuscript JSON, ManuscriptNode markdown, chapter proposals, and scene proposals content-equivalent?
5. Which fields produce duplicate or empty character background/experience-like content?
6. Are relationship type/category fields normalized separately from raw evidence labels?
7. Does zh import have deterministic guards against English user-facing tags, traits, relationship text, and world text?

Implementation targets:
- Use a shared full-source-text accessor prioritizing manuscript_content > raw_content > content > text.
- Preserve complete normal chapters; only split a single oversized chapter by paragraph/scene boundary with explicit metadata.
- Make LLM output source spans, summaries, beats, evidence, and metadata only. Do not ask the LLM to output full chapter bodies.
- Wire deterministic organizer into supervisor lifecycle and artifact output.
- Normalize relationship labels into canonical Chinese categories/types. Preserve raw phrases only as evidence/sourceLabel/description.
- Demote 解惑, 选拔, 冷冰冰的师兄 from canonical relationship type into event/note/trait/evidence fields.
- Add zh language leakage validation for tags, traits, relationships, and world text.
- Keep reviewer repair proposals advisory and Workbench-gated.

Bounded orchestrated import planner target:
- Verify whether W1 is currently fixed supervisor pipeline plus bounded planner hooks.
- Do not build a fully free agent.
- Design a bounded LLM planner where the model may only output PlannerProposal JSON.
- LLM planner may propose:
  - source type;
  - granularity profile;
  - chapter/window strategy;
  - prompt variant keys from allowlist;
  - prompt policy knobs;
  - rerun scope/strategy suggestions.
- LLM planner may not:
  - inject raw prompt text;
  - invent arbitrary tools;
  - reorder required tools without validator approval;
  - disable proposal_write;
  - bypass Workbench/proposal gates;
  - write canonical project data;
  - run unbounded retries;
  - call live provider without explicit user approval.
- Required implementation design:
  - build_planner_proposal_prompt_context(state) remains bounded and source-safe.
  - Add a live planner adapter only behind explicit config/approval.
  - Adapter returns JSON only.
  - Parse with parse_planner_proposal_json.
  - Validate with validate_planner_proposal.
  - Convert with planner_proposal_to_import_plan.
  - Validate with validate_import_plan.
  - Write artifacts: planner_prompt_context.json, planner_proposal.json, planner_proposal_validation.json, import_plan.json, import_plan_validation.json.
- Required planner tests:
  - deterministic default path still works;
  - stub mode still makes no model/API call;
  - live mode without approval still fails safely;
  - valid llm_proposed proposal converts into safe import plan;
  - proposal with raw prompt text fails validation;
  - proposal with unknown tool fails validation;
  - proposal that disables required tool fails validation;
  - converted plan keeps proposal_gate_required=true;
  - converted plan keeps all required tools enabled;
  - 402/budget hard fail prevents further planner/rerun calls.

Shared depth hardening requirements:
- Include a subagent decision trace:
  | Subagent | Question Assigned | Files / Artifacts Read | Evidence Found | Recommendation | Confidence | Lead Decision |
  |---|---|---|---|---|---|---|
- Include algorithm mini-specs for source-span reconstruction, relationship ontology normalization, reviewer/organizer lifecycle, and planner proposal validation.
- Split acceptance into must pass, must fail before fix, must not pass if, and deferred/gated.
- Do not include raw hidden chain-of-thought; provide concise evidence-grounded reasoning with code/artifact/test citations.

Acceptance:
- Targeted pytest passes for W1 prompt windows, supervisor tools/policy, organizer, quality reviewer/rubric, and relationship/tag cases.
- New tests cover the exact symptoms listed above.
- No live LLM/full import unless the user explicitly approves provider/content/cost risk.
- Update canonical docs/dev_logs only if implementation changes contracts.

Required report before coding:
Write an Investigation Report with root cause chains, artifact/code evidence, algorithm proposal, rejected alternatives, and implementation prompt draft. Paste it to Lead before coding.
```

---

## 7. Copy Prompt: Claude W2 Character / Relationship / Command UI

```text
## W2 Claude Task: Character / Relationship / Command UI

You are working in:
/Volumes/migodam's-external-brain/Development/Narrative_IDE

Read first:
0. communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md Section 0.1 User Intent To Preserve
0a. Use Claude Code `/plan` first. The plan must name the required skills/plugins for this window and must not start coding until the Investigation Report is approved when schema/store/command surfaces are touched.
1. dev_docs/README.md
2. dev_docs/DEV_RULES.md
3. dev_docs/UI_logic.txt
4. dev_docs/UX_rules.txt
5. dev_docs/DATA_MODEL.md
6. dev_docs/TEST_SELECTORS.txt
7. dev_docs/TEST_PLAN.md

Use required skills:
- superpowers:using-superpowers
- superpowers:brainstorming
- superpowers:systematic-debugging
- superpowers:subagent-driven-development
- superpowers:test-driven-development
- superpowers:verification-before-completion
- frontend-design:frontend-design
- playwright MCP
- context7 MCP
- brave-search MCP
- typescript-lsp

Primary files:
- src/ui-react/components/CharactersWorkspace.tsx
- src/ui-react/components/ContextMenu.tsx
- src/ui-react/components/CommandPalette.tsx if command registry integration needs it
- src/ui-react/components/graph/CharacterRelationshipFlow.tsx
- src/ui-react/store.ts
- src/ui-react/models/project.ts
- tests/e2e/p0 and tests/e2e/p1 character/context-menu/graph tests

Goal:
Make Character profile, relationship management, right-click actions, and desktop commands coherent and testable.

Current root causes to verify:
- Normal Profile tab only exposes name/background; richer profile fields are effectively unreachable.
- Invalid /characters/profile/:id falls back to another character instead of showing not-found.
- Direct profile routes do not reliably sync global selection/status.
- Character has no canonical custom attributes; only WorldItem has dynamic attributes.
- Delete hard-removes characters/relationships despite docs requiring archive-first and hard-delete safety.
- Import-time duplicate merge exists, but no manual duplicate/merge UX exists.
- Relationship rows are flat; no category/direction/counterpart indentation.
- Context menus are generic and not command-backed.
- No typed clipboard or desktop command registry exists for copy/cut/paste/new/delete/move/merge.

Investigation questions:
1. Should Character custom attributes be canonical as attributes: { key, value }[]? If yes, update DATA_MODEL and project.ts in the same change.
2. Should manual merge be immediate local mutation or Workbench proposal-backed? Default recommendation: explicit modal + direct local mutation with reference-impact preview.
3. Should delete become archive-first for all characters, or only referenced characters?
4. Should /characters/profile/:id be the source of truth for selection, or should all profile navigation call setSelectedEntity('character', id)?
5. Which existing selectors/tests are stale or insufficient for right-click and relationship organization?

Implementation targets:
1. Restore/rebuild reachable Character Profile UI with documented fields and stable selectors.
2. Add route not-found handling and route-to-selection sync.
3. Add character custom attributes if canonical docs/model are updated in the same change.
4. Add duplicate and merge character UX with reference remapping preview.
5. Replace unsafe hard delete UX with archive-first/impact-list behavior.
6. Organize relationship rows with indentation/grouping by relationship category, direction, counterpart, and status.
7. Introduce typed desktop command registry used by command palette, context menus, and shortcuts.
8. Add typed clipboard for character/relationship copy, cut, paste, duplicate, move, merge.
9. Expand right-click menus for character cards, relationship rows/edges, graph nodes, and groups:
   - New
   - Rename/Edit
   - Copy
   - Cut
   - Paste
   - Duplicate
   - Move To Group
   - Merge
   - Archive/Delete
10. Record implementation and test results in dev_logs; update canonical docs/selectors if behavior or schema changes.

Depth hardening requirements:
- Include a subagent decision trace:
  | Subagent | Question Assigned | Files / Artifacts Read | Evidence Found | Recommendation | Confidence | Lead Decision |
  |---|---|---|---|---|---|---|
- Include algorithm mini-specs for command registry, typed clipboard, character custom attributes, duplicate merge/remap, relationship grouping, and archive/delete behavior.
- Split acceptance into must pass, must fail before fix, must not pass if, and deferred/gated.
- Must not pass if right-click is only visual and does not execute through the command registry.
- Must not pass if zh project user-visible tags/relationship labels/menu labels leak English.
- Do not include raw hidden chain-of-thought; provide concise evidence-grounded reasoning with code/artifact/test/screenshot citations.

Acceptance:
- /characters/profile/missing-character shows entity-not-found and recovery path.
- Profile tab exposes full documented fields and saves.
- Direct profile route updates global selection/status.
- Right-click character and relationship surfaces expose command-backed actions.
- Cmd/Ctrl+C/X/V works outside text inputs with typed clipboard.
- Duplicate and merge preserve/remap references correctly.
- Referenced delete shows impact list and defaults to archive; hard delete is blocked unless no refs.
- Relationship organization is readable and deterministic.
- For zh projects, all user-visible character tags, relationship labels, trait badges, and menu labels are Chinese; English enum/internal values may exist only if hidden from users.
- Command palette can run New Character, Delete/Archive Character, Duplicate, Merge, Copy/Cut/Paste.
- Existing character, graph, and route tests continue passing.

Required report before coding:
Write an Investigation Report with UI screenshots, code references, command registry design, data model decision, acceptance tests, and implementation prompt draft. Paste it to Lead before coding if schema or shared-surface changes are needed.
```

---

## 8. Copy Prompt: Claude W3 World / Timeline / Relationship Graph Algorithms

```text
## W3 Claude Prompt Section: World / Timeline / Relationship Graph Algorithms

You are working in Narrative_IDE:
/Volumes/migodam's-external-brain/Development/Narrative_IDE

Follow AGENTS.md and dev_docs/README.md + DEV_RULES.md first.
Also read communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md Section 0.1 User Intent To Preserve.
Use Claude Code `/plan` first. The plan must name the required skills/plugins for this window and must not start coding until the Investigation Report is approved.
No legacy src/ui work. Active stack is src/ui-react, Electron services, Zustand store.

Use required skills:
- superpowers:using-superpowers
- superpowers:brainstorming
- superpowers:systematic-debugging
- superpowers:subagent-driven-development
- superpowers:test-driven-development
- superpowers:verification-before-completion
- frontend-design:frontend-design
- playwright MCP
- context7 MCP
- brave-search MCP
- typescript-lsp

Goal:
Implement W3 algorithmic hardening for:
1. World Model folder tree with no visible top-level category.
2. Stable notebook/folder/item IDs and drag nesting.
3. Timeline command/patch undo transactions.
4. Relationship graph cluster/radial/force-lite layout and label collision.

Files to inspect first:
- src/ui-react/components/WorldWorkspace.tsx
- src/ui-react/components/TagTreePanel.tsx
- src/ui-react/models/project.ts
- src/ui-react/store.ts
- src/ui-react/services/projectService.ts
- src/ui-react/components/timeline/TimelineCanvas.tsx
- src/ui-react/components/timeline/TimelineEventNode.tsx
- src/ui-react/components/timeline/TimelineOperations.ts
- src/ui-react/components/timeline/timelineLayoutEngine.ts
- src/ui-react/components/graph/CharacterRelationshipFlow.tsx
- tests/e2e/p1/*world*
- tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts
- tests/e2e/p1/timeline_undo_transactions.spec.ts
- tests/e2e/p1/character_relationship_flow_layout.spec.ts
- tests/timeline_layout_engine_check.ts

Current facts to verify:
- World currently has separate containers and category tree.
- Category filtering/grouping still depends on categoryPath strings, not stable category IDs.
- Item drag maps drop headers back to containers by name/importCategoryKey.
- WorldItem has categoryId? and parentId?, but current movement can reset parentId to null.
- TagTreePanel already supports drop-before/drop-inside, flattening, collapse, and cycle prevention.
- Timeline branch drags use undo transactions, but event drag can commit updateTimelineEventPosition plus moveTimelineEvent.
- Relationship graph has degree-priority radial layout and simple edge-label offsets, but no explicit cluster/radial/force-lite mode abstraction or label collision helper.

Investigation questions:
1. Should the hidden World top node still exist in data as wcat_root, while UI renders only its children?
2. Should folder nesting be represented by WorldCategoryNode only, or should WorldItem.parentId allow item-inside-item nesting?
3. Are imported categoryPath arrays compatibility metadata only after this change, with categoryId becoming canonical?
4. Should graph layout mode persist globally, per relationship graph, or only as transient UI choice?
5. How should undo transactions represent a drag that changes position, branch, and orderIndex together?

World requirements:
- Keep stable IDs canonical: WorldCategoryNode.id, WorldContainer.id, WorldItem.id.
- Do not show the top-level “世界模型” category as a visible folder row; render its children as visual roots.
- Preserve backward compatibility with existing categoryPath, but stop using display strings as the primary membership key when a stable ID is available.
- Support folder/item nesting with deterministic ordering and cycle prevention.
- Drag/drop must support before/inside/root moves and must not orphan items.
- Update persistence normalization so legacy items without categoryId or categoryPath still render.

Timeline requirements:
- Keep applyTimelineOperation pure.
- Event drag/drop must be one undoable transaction, not multiple snapshots.
- A drag that updates visual position and branch/order must undo in one Command+Z.
- No-op transaction commits must not push undo entries.
- Cancel/Escape/pointercancel must leave undo stack unchanged.

Graph requirements:
- Extract deterministic relationship layout helpers from CharacterRelationshipFlow.
- Support at least: radial, cluster, force-lite.
- Cluster mode should group by importance/community/connected component without random output.
- Force-lite must use bounded deterministic iterations and stable seed/order.
- Add label collision resolution for node labels and edge labels; high-priority labels should win, lower priority labels should offset or hide.
- Preserve existing selectors such as relationship-character-node-<id> and relationship-edge-label-<id>.

Depth hardening requirements:
- Include a subagent decision trace:
  | Subagent | Question Assigned | Files / Artifacts Read | Evidence Found | Recommendation | Confidence | Lead Decision |
  |---|---|---|---|---|---|---|
- Include algorithm mini-specs for world tree normalization/move/cycle prevention, timeline drag transaction, and radial/cluster/force-lite graph layout.
- Split acceptance into must pass, must fail before fix, must not pass if, and deferred/gated.
- Must not pass if timeline event drag creates multiple undo entries or reverts unrelated state.
- Must not pass if world hierarchy still depends on display categoryPath as the primary membership key.
- Must not pass if graph labels overlap in the dense fixture beyond the stated tolerance.
- Do not include raw hidden chain-of-thought; provide concise evidence-grounded reasoning with code/artifact/test/screenshot citations.

Acceptance tests:
- World: hidden root category is not visible; child folders are visible roots.
- World: moving folder/item inside another folder persists parentId/categoryId.
- World: cycle attempts are rejected.
- World: legacy categoryPath items still render.
- World undo: moving a world item/folder creates one undo entry and restores original parent/container/category.
- Timeline: event drag transaction creates exactly one undo entry and restores position + branch/order.
- Timeline: branch transaction tests continue passing.
- Graph: radial star topology is not a single row.
- Graph: cluster layout separates importance/community groups.
- Graph: force-lite is deterministic across reloads.
- Graph: labels do not overlap beyond small tolerance.
- Run targeted Playwright tests plus tests/timeline_layout_engine_check.ts and npm run ui:build.

Required report before coding:
Write an Investigation Report with current data truth table, algorithms, test gaps, shared-surface patch plan, and implementation prompt draft. Paste it to Lead before coding.
```

---

## 9. Copy Prompt: Claude W4 QA + Communication Merge

```text
## Claude W4 QA + Communication Merge Prompt Section

You are Claude W4: QA + Communication Merge for Narrative_IDE.

Repository:
/Volumes/migodam's-external-brain/Development/Narrative_IDE

Mode:
Read-first, evidence-first. Do not implement until you have produced an investigation report and received approval.

Use required skills:
- superpowers:using-superpowers
- superpowers:systematic-debugging
- superpowers:verification-before-completion
- claude-md-management:claude-md-improver
- playwright MCP
- context7 MCP
- brave-search MCP
- real Electron run via npm run electron:dev when approved/available

Start by reading:
0. communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md Section 0.1 User Intent To Preserve
0a. Use Claude Code `/plan` first. The plan must name the required skills/plugins for this window and must not claim QA completion before evidence is collected.
1. dev_docs/README.md
2. dev_docs/DEV_RULES.md
3. communication/2026-06-06-w1-import-p0-bug-checklist.md
4. communication/2026-06-06-w1-live-smoke-runner-and-hardfail-report.md
5. communication/2026-06-06-w7-post-smoke-final-qa-report.md
6. communication/2026-06-06-w1-deep-diagnostic-multiagent-flow.md

Mission:
Produce a QA + communication consolidation investigation report for right-click, undo, world, manuscript, graph, and W1 diagnostics. Separate verified automated browser coverage from real Electron acceptance. Do not claim completion without Playwright/Electron evidence, screenshot paths, and command outputs.

Known facts:
- communication/ has many dated reports. A first-pass README, current-state rollup, merged evidence rollup, and task-completion audit now exist, but W4 must verify their classifications, fill any gaps, and preserve old reports as provenance.
- Current Playwright config is Chromium web-server based, not a real Electron launch.
- Reports claim strong automated gates, but live 10-chapter Electron/provider acceptance is not complete.
- Relevant test evidence exists for manuscript, undo, graph, world, and W1 diagnostics, but many specs inject Zustand state or mock Electron IPC.
- tests/e2e/p0/graph_crud.spec.ts may expect graph-context-menu/world-context-menu while active shared UI exposes global-context-menu.

Required inspections:
- communication/ inventory: identify canonical, supporting, superseded, worker-report, and archive-candidate docs.
- tests/playwright.config.ts: confirm current tests run Chromium against localhost, not Electron.
- tests/e2e/p0/graph_crud.spec.ts: check stale graph-context-menu / world-context-menu selectors.
- src/ui-react/components/ContextMenu.tsx: confirm active shared global-context-menu.
- tests/e2e/p1/global_undo.spec.ts
- tests/e2e/p1/writing_manuscript_import_display.spec.ts
- tests/e2e/p1/character_relationship_flow_layout.spec.ts
- tests/e2e/p1/world_hierarchy.spec.ts
- tests/e2e/p1/world_item_drag_drop.spec.ts
- tests/e2e/p1/import_activity_status.spec.ts
- W1 diagnostics docs and tools referenced by the 2026-06-06 reports.

Acceptance matrix to fill:
| Area | Current evidence | Gap to close | Required screenshot/artifact |
|---|---|---|---|
| Right-click/context menu |  |  |  |
| Undo |  |  |  |
| World |  |  |  |
| Manuscript |  |  |  |
| Relationship graph |  |  |  |
| W1 diagnostics |  |  |  |
| Communication |  |  |  |

Docs rules:
- Do not delete reports first.
- Keep communication/README.md as the current-state index and update it if classifications change.
- Mark each report as canonical, supporting evidence, worker report, superseded, or archive candidate.
- Keep/update the dated 2026-06-06 current-state rollup and merged evidence rollup.
- Preserve command outputs, acceptance tables, screenshot paths, artifact paths, and remaining risks.
- Only move/archive files after Lead approval.

Required output:
1. Facts found, with file paths.
2. Stale test gaps and selector mismatches.
3. Real Electron acceptance plan with screenshots required.
4. Acceptance matrix for right-click, undo, world, manuscript, graph, W1 diagnostics, communication.
5. Communication consolidation policy:
   - verify/update communication/README.md
   - verify/update dated rollups
   - classify reports
   - preserve evidence
   - do not delete/move until Lead approval
6. Implementation prompt draft for the future merge worker.

Depth hardening requirements:
- Include a subagent decision trace:
  | Subagent | Question Assigned | Files / Artifacts Read | Evidence Found | Recommendation | Confidence | Lead Decision |
  |---|---|---|---|---|---|---|
- Include an evidence matrix for right-click, undo, world, manuscript, graph, W1 diagnostics, and communication docs.
- Split acceptance into must pass, must fail before fix, must not pass if, and deferred/gated.
- Must not claim Electron completion from browser-only Playwright tests unless explicitly justified.
- Must not run live provider smoke without explicit user approval for content/API/cost risk.
- Must not delete or move docs without Lead approval.
- Do not include raw hidden chain-of-thought; provide concise evidence-grounded reasoning with command output, screenshot path, artifact path, or fixture citations.

Acceptance bar:
- Zero-cost automated gates are not enough for final acceptance.
- Real acceptance requires Electron or explicitly justified browser substitute, screenshots, and artifact evidence.
- Live 10-chapter provider import remains gated unless the user explicitly approves external API/content/cost risk.
```

---

## 10. Lead Final Acceptance Gate

After worker implementation branches are integrated, Lead must run or collect evidence for:

| Gate | Required command/evidence |
|---|---|
| Backend import | Targeted W1 pytest, including prompt windows, supervisor policy/tools, organizer, reviewers |
| Frontend build | `npm run ui:build` |
| Frontend E2E | Targeted Playwright specs for characters, context menu, timeline undo, world hierarchy/drag, manuscript, graph |
| Diagnostics | `tools/w1_import_diagnostics.py` or equivalent fixture/artifact check |
| Docs | `communication/README.md`, dated rollup, worker reports, dev logs |
| Manual/Electron | Screenshot set for right-click, undo, world drag, manuscript, graph, W1 console |
| Live 10-ch import | Only after explicit user approval for external provider, local manuscript text upload, and cost risk |

Hard fail conditions:

- The LLM is asked to output full chapter bodies.
- A normal chapter is truncated or cross-cut without explicit oversized-chapter metadata.
- English tags survive in zh user-facing fields.
- `解惑`, `选拔`, or descriptive phrases become canonical relationship type.
- Right-click menu is only visual and not command-backed.
- Timeline drag undo reverts import package or unrelated project state.
- World UI still relies on visible top-level `category` as the primary model.
- Communication docs are deleted or moved without Lead approval.

---

## 11. Integrated Execution Guide And Hardening Addendum

This section replaces the separate hardening addendum. Use this section together with the W0-W4 prompts above.

### 11.1 Human Execution Steps

1. Open Claude Window 0.
2. Paste Section 5 only: `Copy Prompt: Claude W0 Lead Architecture`.
3. Do not separately paste Section 11.2. Its content is already merged into Section 5.
4. Wait for W0 to return its Architecture Contract.
5. Send W0's contract to Codex/human review before opening implementation windows.
6. After W0 is approved, open four Claude windows:
   - W1: paste Section 6 only.
   - W2: paste Section 7 only.
   - W3: paste Section 8 only.
   - W4: paste Section 9 only.
7. Each worker must first produce an Investigation Report and an Implementation Prompt.
8. Review before coding:
   - W0: always.
   - W1: always.
   - W3: always.
   - W2: required if schema, store, project model, command registry, or relationship ontology changes.
   - W4: required if claiming Electron completion, running live smoke, moving/deleting docs, or changing canonical docs.
9. Merge/execute in this order: W1 -> W2 -> W3 -> W4.
10. Live 10-chapter provider smoke requires explicit user approval for API provider, local text upload, token/cost risk, and stop condition.

### 11.2 W0 Orchestrator Architecture Addendum

Status: merged into Section 5. Do not paste this separately unless you intentionally want to repeat the instruction.

```text
## W0 Addendum — Orchestrator Architecture Review

Before approving W1/W2/W3/W4 implementation, perform an explicit orchestrator architecture review.

User critique to evaluate:
Current W1 is a fixed LangGraph/policy pipeline plus bounded supervisor rerun loop. It is not a true model-driven orchestrator. A better next step is not a fully free agent, but an orchestrated pipeline where LLM planner/judge proposes bounded strategy and validators/executors enforce safety.

Read first:
- dev_docs/W1_IMPORT_COMPILER.md
- dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md
- sidecar/workflows/w1_import.py
- sidecar/supervisor/policy.py
- sidecar/supervisor/planner.py
- sidecar/supervisor/planner_llm.py
- sidecar/supervisor/tool_registry.py
- sidecar/supervisor/tools.py
- sidecar/models/state.py
- tests/test_w1_supervisor_policy.py
- tests/test_w1_orchestrator_artifacts.py

Answer these questions with code paths and line references:
1. Is W1 currently controlled by a fixed stage order in run_supervisor_policy()?
2. Can any model output directly reorder tools, disable required tools, inject raw prompt text, or bypass proposal gates?
3. Is tool_registry a real callable registry or a stub?
4. Is planner_llm.py currently making live model calls?
5. What exactly happens when llm_planner_mode="live"?
6. Which planning decisions are already schema-safe in PlannerProposal?
7. Which decisions should remain deterministic forever?

Required architecture decision:
Choose one:
- A. Keep deterministic-only supervisor.
- B. Build bounded PlannerProposal-driven orchestrated pipeline.
- C. Build fully free model-driven ReAct agent.

Default recommendation is B unless evidence proves otherwise.

If choosing B, produce:
- allowed LLM planner decisions;
- forbidden LLM planner decisions;
- validator gates;
- artifact outputs;
- minimum implementation patch;
- tests that prove no unsafe dynamic execution is possible.

Reject any W1 worker prompt that treats "orchestrator" as just another name for the existing fixed pipeline.
```

### 11.3 W1 Bounded Orchestrated Import Addendum

Status: merged into Section 6. Do not paste this separately unless you intentionally want to repeat the instruction.

```text
## W1 Addendum — Bounded Orchestrated Import Planner

Your W1 task is not only to fix chapter/character/tag/relationship defects. You must also investigate whether the import pipeline should become a bounded orchestrated pipeline.

Current suspected architecture:
- tool_registry exists and is real.
- run_supervisor_policy() consumes tools in a fixed order.
- planner_llm.py is zero-cost scaffolding and does not call a model.
- llm_planner_mode="live" is gated and fails without model call.
- PlannerProposal is already schema-bound and validator-gated.

Your job:
1. Verify these facts with code references.
2. Design a minimal bounded LLM planner implementation.
3. Do not build a fully free agent.

Target architecture:
LLM planner may only output PlannerProposal JSON.
It may propose:
- source type;
- granularity profile;
- chapter/window strategy;
- prompt variant keys from allowlist;
- prompt policy knobs;
- rerun scope/strategy suggestions.

It may not:
- inject raw prompt text;
- invent arbitrary tools;
- reorder required tools without validator approval;
- disable proposal_write;
- bypass Workbench/proposal gates;
- write canonical project data;
- run unbounded retries;
- call live provider without explicit user approval.

Required implementation design:
- build_planner_proposal_prompt_context(state) remains bounded and source-safe.
- Add a live planner adapter only behind explicit config/approval.
- Adapter returns JSON only.
- Parse with parse_planner_proposal_json.
- Validate with validate_planner_proposal.
- Convert with planner_proposal_to_import_plan.
- Validate with validate_import_plan.
- Write artifacts:
  - planner_prompt_context.json
  - planner_proposal.json
  - planner_proposal_validation.json
  - import_plan.json
  - import_plan_validation.json

Required tests:
- deterministic default path still works;
- stub mode still makes no model/API call;
- live mode without approval still fails safely;
- valid llm_proposed proposal converts into safe import plan;
- proposal with raw prompt text fails validation;
- proposal with unknown tool fails validation;
- proposal that disables required tool fails validation;
- converted plan keeps proposal_gate_required=true;
- converted plan keeps all required tools enabled;
- 402/budget hard fail prevents further planner/rerun calls.

Required product connection:
Use the planner to solve real novel-quality issues:
- normal chapters remain atomic;
- oversized chapters split only with metadata;
- LLM emits source spans and metadata, not full chapter bodies;
- Chinese novel visible labels remain Chinese;
- relationship labels use Chinese allowlist;
- false labels like 解惑, 选拔, 启明者冷冰冰的师兄 are demoted to evidence/event/note.

Deliver an Investigation Report before coding:
| Topic | Evidence | Design | Tests | Risk |
|---|---|---|---|---|
| Planner live path |  |  |  |  |
| Import text contract |  |  |  |  |
| Judge/rerun advisor |  |  |  |  |
| Safety validators |  |  |  |  |
| Artifact audit trail |  |  |  |  |
```

### 11.4 Shared Depth Hardening Reference

Status: reference only. Do not paste this separately. The necessary hardening requirements are already merged into Sections 5, 6, 7, 8, and 9 so each Claude window can receive one copy block.

```text
## Depth Hardening Requirements

This worker report is not acceptable if it only lists symptoms and proposed fixes. Convert investigation into enforceable contracts.

Required subagent decision trace:
| Subagent | Question Assigned | Files / Artifacts Read | Evidence Found | Recommendation | Confidence | Lead Decision |
|---|---|---|---|---|---|---|

Rules:
- Every subagent claim must cite code path, artifact path, screenshot path, command output, or fixture.
- Lead records accept/reject/defer for each recommendation.
- If subagents disagree, write the tie-break reason and the test that decides it.
- Do not include raw hidden chain-of-thought; provide concise evidence-grounded reasoning.

Required algorithm mini-spec:
- problem definition;
- inputs and outputs;
- data structures;
- deterministic behavior;
- invariants;
- complexity or bounded iteration limits;
- migration/backward compatibility;
- failure/no-op behavior;
- test fixtures.

Required acceptance split:
1. Must pass:
   - exact commands;
   - exact tests;
   - exact screenshots/artifacts.
2. Must fail before fix:
   - fixture or UI reproduction;
   - expected failing assertion.
3. Must not pass if:
   - LLM-generated full chapter body becomes canonical;
   - zh visible labels leak English;
   - relationship evidence phrase becomes canonical type;
   - context menu action bypasses command registry;
   - timeline undo rolls back unrelated state;
   - world hierarchy depends on display categoryPath as primary key;
   - Electron acceptance is claimed from browser-only tests without justification.
4. Deferred/gated:
   - live provider import;
   - external API/content/cost exposure;
   - destructive docs archive/move;
   - schema changes requiring Lead approval.

Final evidence table:
| Area | Fixture/Test | Command | Screenshot/Artifact | Pass/Fail | Remaining Risk |
|---|---|---|---|---|---|
```

### 11.5 Solution Architecture Summary

| Problem | Root cause | Required design |
|---|---|---|
| Chapter body truncated | LLM/pipeline treats body text as generated output | Raw source is canonical; LLM emits spans and metadata only; UI reconstructs body |
| Manuscript equals Chapter | Product objects are blurred | Chapter is source structure; ManuscriptNode is author-facing outline/prose projection |
| Empty character background/experience | Extraction/reviewer/UI schema do not force evidence-backed fields | Extract background/experience as evidence entries; profile UI exposes editable sections |
| Duplicate characters/text | Dedupe is advisory, not a user workflow | Add merge preview, reference remap, archive-first delete |
| Bad relationship labels | Raw phrases become relationship type | Chinese allowlist for type; raw phrase becomes evidence/note/event |
| English tags in Chinese novel | Internal enum/default labels leak into visible UI | zh language policy across prompt, reducer, reviewer, and UI tests |
| Timeline undo broken | Drag is many state changes but undo expects one change | Command transaction: pointerdown before, pointerup commit once, Esc cancel |
| World Model category confusion | Display strings/category paths act like canonical structure | Stable notebook/folder/item tree; categoryPath only compatibility |
| Right-click no effect | Menus are visual callbacks, not shared commands | CommandContext + AppCommand + typed clipboard used by menu/shortcut/buttons |
| Orchestrator weak | Fixed pipeline has low strategy ceiling | Bounded LLM planner/judge advisor proposes strategy; validators execute safely |

### 11.6 Right-Click Operation Contract

The UI must not implement right-click as isolated ad hoc callbacks. It must use a shared command registry.

Required types:

```text
CommandContext
  projectId
  surface
  targetType
  targetId
  selection
  clipboard
  permissions

AppCommand
  id
  label
  icon
  shortcut
  appliesTo(context)
  enabled(context)
  disabledReason(context)
  execute(context)
  undoMode

ClipboardPayload
  kind: copy | cut
  entityType
  entityIds
  sourceParentId
  serializedPreview
  pasteConstraints
```

Minimum menus:

| Surface | Required commands |
|---|---|
| Character | New Character, Edit, Add Attribute, Copy, Cut, Duplicate, Merge, Archive/Delete, Open Relationships |
| Relationship | Edit Type, Add Note, Copy, Cut, Delete/Archive, Open Source, Open Target |
| World folder | New Folder, New Item, Rename, Copy, Cut, Paste, Move, Delete/Archive |
| World item | Edit, Copy, Cut, Duplicate, Move To, Archive/Delete |
| Timeline event | Edit, Duplicate, Move To Branch, Copy, Cut, Delete/Archive |
| Blank workspace | New Object, Paste, Select All |

Acceptance:

- Right-click menu appears in Electron and Playwright.
- Clicking a menu item changes state.
- Same command works from shortcut/command palette.
- Undo works for mutating commands.
