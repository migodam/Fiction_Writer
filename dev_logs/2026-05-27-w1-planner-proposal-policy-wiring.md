# W1 V2 PlannerProposal Policy Wiring — 2026-05-27

## What was wired

- **`ImportSupervisorState`** (`sidecar/models/state.py`): two new optional fields —
  `planner_proposal: PlannerProposal` and `planner_proposal_validation: Dict[str, Any]`.

- **`_ensure_orchestrator_plan()`** (`sidecar/supervisor/policy.py`):
  - Added import: `from sidecar.supervisor.planner import planner_proposal_to_import_plan, validate_planner_proposal`
  - `profile_config` is now computed before any proposal branch (fixes potential `UnboundLocalError`).
  - If `state["planner_proposal"]` or `context["planner_proposal"]` is present:
    - Invalid proposal → `hard_fail` immediately, no `ImportPlan` built.
    - Valid proposal → `planner_proposal_to_import_plan()` replaces the deterministic `plan_import_pipeline()` call.
    - Both paths store results in `planner_proposal_validation`.
  - When no proposal is present, the deterministic path is 100% unchanged.
  - Codex integration added a guard for preplanned states: if `tool_operating_spec` and
    `converge_target` already exist but a new invalid `context["planner_proposal"]` is present,
    `_ensure_orchestrator_plan()` validates it and returns `hard_fail` instead of early-returning.

- **`proposal_write()`** (`sidecar/supervisor/tools.py`): two conditional artifact writes added
  after `import_plan_validation.json` — `planner_proposal.json` and
  `planner_proposal_validation.json` are written before the OOM-risk synthesis phase.

## Tests added

- `tests/test_w1_supervisor_policy.py` — 6 new methods on `TestOrchestratorPlanGranularity`:
  - `test_no_proposal_preserves_deterministic_import_plan`
  - `test_valid_llm_proposed_proposal_produces_llm_proposed_plan`
  - `test_invalid_proposal_raw_prompt_text_causes_hard_fail`
  - `test_invalid_proposal_raw_prompt_text_no_unbound_local_error`
  - `test_invalid_proposal_disabled_proposal_write_causes_hard_fail`
  - `test_context_planner_proposal_used_when_state_key_absent`
  - `test_invalid_context_proposal_rejected_on_preplanned_state`

- `tests/test_w1_supervisor_tools.py` — 1 new method on `TestProposalWriteEarlyArtifacts`:
  - `test_planner_proposal_artifacts_written_before_oom_crash`

## Test results

```
33 passed (TestOrchestratorPlanGranularity + TestProposalWriteEarlyArtifacts + TestPlannerProposal)
54 passed regression (test_w1_granularity + test_w1_import_plan_validator)
344 passed combined W1 regression after Codex integration
```

## Deferred

- `w1_planner_prompts.py` — system prompt for LLM to produce a `PlannerProposal`
- Populating `state["planner_proposal"]` from an actual LLM inference call
