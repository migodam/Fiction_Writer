# W1 ImportPlan Validator — 2026-05-27

## What was added

- **`_KNOWN_TOOLS`**, **`_VALID_PLANNER_KINDS`**, **`_VALID_SOURCE_TYPES`** — module-level
  frozensets in `sidecar/models/state.py` (after `plan_import_pipeline`, before
  `plan_orchestrator_targets`).

- **`validate_import_plan(plan: ImportPlan) -> tuple[bool, list[str]]`** — standalone validator;
  no callers yet. Returns `(True, [])` for valid plans, `(False, [errors...])` for invalid.

- **`tests/test_w1_import_plan_validator.py`** — 23 tests, all passing.

## Validation rules enforced

| Rule | Check |
|------|-------|
| planner_kind | must be `deterministic_rules` or `llm_proposed` |
| source_type | must be one of 4 known profile names |
| tools present | `tools` must be non-empty |
| all 11 tools required | each of the 11 W1 tools must appear AND be `enabled=True` |
| no unknown tools | tool names must be in the known set |
| no duplicate orders | `order` values must be unique across steps |
| step keys | each step must have `tool`, `enabled`, `order` |
| prompt_policy | `dynamic_prompt_edits_allowed` must be exactly `False` |
| cost_policy | `stop_on_api_402` must be exactly `True` |
| safety | `proposal_gate_required`, `schema_validated_plan`, `llm_planner_can_propose_only` must all be exactly `True` |

## Deferred

- Wiring `validate_import_plan()` into `policy.py._ensure_orchestrator_plan()` — Codex after review.
- LLM planner proposal flow — future session.
