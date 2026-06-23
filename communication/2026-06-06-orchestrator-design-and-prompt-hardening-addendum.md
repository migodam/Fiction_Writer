# Narrative IDE Orchestrator Design And Prompt Hardening Addendum

Date: 2026-06-06  
Author: Codex  
Scope: strengthen the next-wave Claude handoff after reviewing the user's orchestrator critique and the current W1 supervisor/planner code.

## Short Verdict

The previous Claude plan was not useless, but it was not strong enough. It listed the right workstreams and many acceptance gates, but it did not force Claude workers to produce the deeper architecture artifacts that would make their output better than a normal task prompt.

The missing layer was:

- orchestrator architecture judgment;
- subagent decision trace;
- algorithm invariants;
- must-fail acceptance boundaries;
- explicit "do not just patch the pipeline" language.

This addendum upgrades the handoff.

## Evaluation Of The User's Orchestrator Analysis

I basically agree with the user's analysis.

Current W1 is not a true model-driven orchestrator. It is closer to:

```text
deterministic pipeline
+ supervisor QA/rerun loop
+ bounded planner proposal contract
```

What the current system does:

```text
validate/split
-> segment_manifest
-> extract windows
-> cross_validate
-> bounded rerun_window
-> reduce_entities
-> reduce_world_entities
-> minor_repair
-> architect_timeline
-> qa_review
-> judge_import
-> thematic rerun loop
-> proposal_write
```

What it does not yet do:

```text
model sees state
-> model chooses next tool
-> model decides whether to skip/merge/reorder stages
-> model adapts strategy freely by novel structure
```

Important nuance:

- `tool_registry.py` is not fake. It is a real callable registry.
- The weak part is not the registry. The weak part is that the registry is consumed by a fixed policy loop, not by a model-driven tool selector.
- `planner_llm.py` is scaffolding: it builds prompt context, parses JSON, and creates a deterministic stub. It does not call a model.
- `llm_planner_mode="live"` currently hard-fails instead of calling a model.

## Code Facts Verified

| Fact | Code surface |
|---|---|
| W1 active runner can enter supervisor mode | `sidecar/workflows/w1_import.py` |
| Supervisor policy has fixed stages | `sidecar/supervisor/policy.py::run_supervisor_policy` |
| `llm_planner_mode="live"` is gated and makes no model call | `sidecar/supervisor/policy.py::_ensure_orchestrator_plan` |
| LLM planner module is zero-cost scaffolding | `sidecar/supervisor/planner_llm.py` |
| Planner proposal is bounded and validator-gated | `sidecar/supervisor/planner.py`, `sidecar/models/state.py::PlannerProposal` |
| Tool registry is real but statically consumed | `sidecar/supervisor/tool_registry.py` |
| Judge is deterministic gate logic with bounded thematic reruns | `sidecar/supervisor/tools.py::judge_import`, `policy.py::_apply_thematic_reruns` |

## Final Design Direction

Do not jump from deterministic pipeline to a fully free agent. That would make tests, cost, and debugging much worse.

The right design is an **orchestrated pipeline**:

```text
fixed safe spine
+ model-proposed planning decisions
+ validator-enforced execution
+ model-assisted judge/rerun strategy
+ artifact-backed audit trail
```

Plain language:

- Keep the train tracks.
- Let the model choose the route switches.
- Never let the model remove brakes, rewrite raw prompts, bypass proposal gates, or run unbounded loops.

## What To Change Conceptually

### 1. Planner

Current:

```text
rules choose source profile, granularity, window strategy, prompt policy
```

Target:

```text
LLM reads bounded source_profile + cheap diagnostics
-> emits PlannerProposal JSON only
-> validate_planner_proposal checks it
-> planner_proposal_to_import_plan converts it
-> validate_import_plan checks required tools and safety
-> deterministic executor runs the plan
```

Allowed LLM planner decisions:

- source type;
- granularity profile;
- chapters per window;
- prompt variant keys from allowlist;
- event density strategy;
- world boundary strictness;
- reviewer/organizer strictness knobs;
- rerun scope suggestions.

Forbidden LLM planner decisions:

- raw prompt text injection;
- arbitrary tool names;
- disabling required tools;
- skipping proposal gate;
- direct writes to project data;
- unbounded loops;
- external API calls without user approval.

### 2. Judge / Rerun

Current:

```text
deterministic thresholds decide character/event/world/language gates
```

Target:

```text
deterministic judge computes metrics
+ optional LLM judge advisor proposes rerun plan
+ validator clamps scope, budget, tools, and strategy
+ executor runs bounded repairs
```

Allowed LLM judge decisions:

- which windows deserve rerun;
- split vs augment;
- what recovery theme to use;
- whether to prioritize character, relationship, world, or timeline repair;
- whether a defect should become Workbench proposal or unresolved risk.

Forbidden LLM judge decisions:

- calling tools directly;
- editing canonical project state;
- marking acceptance without tests/artifacts;
- exceeding rerun budget;
- retrying after provider/budget hard fail.

### 3. Import Text Contract

Current risk:

```text
LLM and pipeline may treat chapter body as text to generate or transform.
```

Target:

```text
raw source is canonical
chapter/scene store spans
LLM emits metadata only
UI reconstructs body deterministically
```

Rule:

- LLM may summarize, classify, and cite spans.
- LLM may not output canonical full chapter bodies.

### 4. Frontend Interaction Contract

Current risk:

```text
right-click and undo are UI behaviors without a shared command model.
```

Target:

```text
CommandContext + AppCommand + typed clipboard + transaction undo
```

Rule:

- Context menu, command palette, keyboard shortcuts, and buttons must call the same command registry.
- Timeline drag must be one transaction.
- World drag/drop must be tree move with cycle prevention.

## Subagent Decision Trace

This is the concise, evidence-grounded trace from the subagents. It is not a raw hidden chain-of-thought transcript.

| Subagent | Question Assigned | Evidence Found | Recommendation | Lead Decision |
|---|---|---|---|---|
| Prompt-depth auditor | Is the next-wave plan shallow? | Plan has good workstream split, shared surfaces, worker template, and hard fails, but lacks state machines/invariants/must-fail contracts | Add depth-hardening section requiring state machines, algorithm specs, decision trace, and must-fail tests | Accepted |
| Orchestrator auditor | Is user's orchestrator critique accurate? | W1 supervisor policy is fixed-stage; LLM live planner is gated; planner proposal is validator-bound; tool registry is real but not model-selected | Do bounded `PlannerProposal`-driven orchestrated pipeline, not fully free ReAct agent | Accepted |
| Docs merge auditor | Were old docs actually merged? | README was an index, not evidence merge | Add merged evidence rollup and file classification inventory | Already completed |

## Copy Prompt Addendum For Claude W0

Paste this after the W0 prompt in `2026-06-06-w1-next-wave-multiagent-claude-plan.md`.

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
1. Is W1 currently controlled by a fixed stage order in `run_supervisor_policy()`?
2. Can any model output directly reorder tools, disable required tools, inject raw prompt text, or bypass proposal gates?
3. Is `tool_registry` a real callable registry or a stub?
4. Is `planner_llm.py` currently making live model calls?
5. What exactly happens when `llm_planner_mode="live"`?
6. Which planning decisions are already schema-safe in `PlannerProposal`?
7. Which decisions should remain deterministic forever?

Required architecture decision:
Choose one:
- A. Keep deterministic-only supervisor.
- B. Build bounded `PlannerProposal`-driven orchestrated pipeline.
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

## Copy Prompt Addendum For Claude W1

Paste this after the W1 Backend Import Quality prompt.

```text
## W1 Addendum — Bounded Orchestrated Import Planner

Your W1 task is not only to fix chapter/character/tag/relationship defects. You must also investigate whether the import pipeline should become a bounded orchestrated pipeline.

Current suspected architecture:
- `tool_registry` exists and is real.
- `run_supervisor_policy()` consumes tools in a fixed order.
- `planner_llm.py` is zero-cost scaffolding and does not call a model.
- `llm_planner_mode="live"` is gated and fails without model call.
- `PlannerProposal` is already schema-bound and validator-gated.

Your job:
1. Verify these facts with code references.
2. Design a minimal bounded LLM planner implementation.
3. Do not build a fully free agent.

Target architecture:
LLM planner may only output `PlannerProposal` JSON.
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
- disable `proposal_write`;
- bypass Workbench/proposal gates;
- write canonical project data;
- run unbounded retries;
- call live provider without explicit user approval.

Required implementation design:
- `build_planner_proposal_prompt_context(state)` remains bounded and source-safe.
- Add a live planner adapter only behind explicit config/approval.
- Adapter returns JSON only.
- Parse with `parse_planner_proposal_json`.
- Validate with `validate_planner_proposal`.
- Convert with `planner_proposal_to_import_plan`.
- Validate with `validate_import_plan`.
- Write artifacts:
  - `planner_prompt_context.json`
  - `planner_proposal.json`
  - `planner_proposal_validation.json`
  - `import_plan.json`
  - `import_plan_validation.json`

Required tests:
- deterministic default path still works;
- stub mode still makes no model/API call;
- live mode without approval still fails safely;
- valid `llm_proposed` proposal converts into safe import plan;
- proposal with raw prompt text fails validation;
- proposal with unknown tool fails validation;
- proposal that disables required tool fails validation;
- converted plan keeps `proposal_gate_required=true`;
- converted plan keeps all required tools enabled;
- 402/budget hard fail prevents further planner/rerun calls.

Required product connection:
Use the planner to solve real novel-quality issues:
- normal chapters remain atomic;
- oversized chapters split only with metadata;
- LLM emits source spans and metadata, not full chapter bodies;
- Chinese novel visible labels remain Chinese;
- relationship labels use Chinese allowlist;
- false labels like `解惑`, `选拔`, `启明者冷冰冰的师兄` are demoted to evidence/event/note.

Deliver an Investigation Report before coding:
| Topic | Evidence | Design | Tests | Risk |
|---|---|---|---|---|
| Planner live path |  |  |  |  |
| Import text contract |  |  |  |  |
| Judge/rerun advisor |  |  |  |  |
| Safety validators |  |  |  |  |
| Artifact audit trail |  |  |  |  |
```

## Copy Prompt Addendum For All Claude Workers

Paste this after each worker prompt if the worker touches algorithms, commands, or data structures.

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
   - world hierarchy depends on display `categoryPath` as primary key;
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

## Simple Product-Level Solution Map

| Problem | Root cause in plain words | Solution |
|---|---|---|
| Chapter body truncated | The model/pipeline is treating chapter text as generated output instead of source span projection | Raw source is canonical; LLM emits spans and metadata only; UI reconstructs body |
| Manuscript equals Chapter | Product objects are blurred | Chapter is source structure; ManuscriptNode is author-facing outline/prose projection |
| Empty character background/experience | Extraction/reviewer/UI schema do not force evidence-backed fields | Extract background/experience as evidence entries; profile UI exposes editable sections |
| Duplicate characters/text | Dedupe is mostly backend advisory, not a full user workflow | Add merge preview, reference remap, archive-first delete |
| Bad relationship labels | Raw phrases are promoted into relationship type | Chinese allowlist for type; raw phrase becomes evidence/note/event |
| English tags in Chinese novel | Internal enum/default labels leak into visible UI | zh language policy across prompt, reducer, reviewer, and UI tests |
| Timeline undo broken | Drag is many state changes but undo expects one change | Command transaction: pointerdown before, pointerup commit once, Esc cancel |
| World Model category confusion | Display strings and category paths are acting like canonical structure | Stable notebook/folder/item tree; categoryPath only compatibility |
| Right-click no effect | Menus are visual callbacks, not shared commands | `CommandContext` + `AppCommand` + typed clipboard used by menu/shortcut/buttons |
| Orchestrator weak | Fixed pipeline has low strategy ceiling | Bounded LLM planner/judge advisor proposes strategy; validators execute safely |

