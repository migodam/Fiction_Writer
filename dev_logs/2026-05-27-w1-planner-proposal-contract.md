# W1 V2 PlannerProposal Contract — 2026-05-27

## What was added

- **`PlannerProposalToolOverride` TypedDict** — `sidecar/models/state.py` (after `ImportPlan`):
  tool-level override with only `tool`, `prompt_granularity`, `rerun_allowed`.

- **`PlannerProposal` TypedDict** — `sidecar/models/state.py`: the only channel through which
  a future LLM/RAG planner may influence W1 execution. 10 top-level fields.

- **`sidecar/supervisor/planner.py`** (new module):
  - `validate_planner_proposal(proposal) → tuple[bool, list[str]]`
  - `planner_proposal_to_import_plan(proposal, tos, *, ...) → ImportPlan`

- **`tests/test_w1_planner_proposal.py`** — 18 tests, all passing.

- **`dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`** — new PlannerProposal Safety Boundary section.

- **`dev_docs/W1_IMPORT_COMPILER.md`** — updated planner line to reference `PlannerProposal`.

## Safety boundary enforced

| Check | Mechanism |
|-------|-----------|
| Unknown top-level keys | `_PROPOSAL_ALLOWED_FIELDS` frozenset |
| planner_kind / source_type | `_VALID_PLANNER_KINDS` / `_VALID_SOURCE_TYPES` from state.py |
| Tool overrides | `_OVERRIDE_ALLOWED_FIELDS`; tool must be in `_KNOWN_TOOLS` |
| Variant keys | Per-tool frozenset allowlists (`_TOOL_VARIANT_ALLOWLISTS`); no regex, no prose |
| Granularity profile | `_GP_ALLOWED_FIELDS` (no unknown keys); `_GP_LITERAL_FIELDS` + `_GP_NUMERIC_BOUNDS` |
| Window strategy | `_KNOWN_WINDOW_STRATEGY_KEYS`; `_WINDOW_NUMERIC_BOUNDS` |
| Final plan gate | `validate_import_plan()` after conversion |

## Deferred

- `w1_planner_prompts.py` — system prompt for LLM to produce a `PlannerProposal` (model-call session)
- Wire `planner_proposal_to_import_plan()` into `_ensure_orchestrator_plan()` (policy.py plan)
- `state["planner_proposal"]` field on `ImportSupervisorState` (policy.py plan)
