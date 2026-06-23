"""Tests for validate_import_plan() — W1 ImportPlan execution contract enforcement."""
import copy

import pytest

from sidecar.models.state import (
    ImportPlan,
    plan_import_pipeline,
    plan_tool_operating_spec,
    select_granularity_profile,
    validate_import_plan,
)


def _valid_plan() -> dict:
    tos = plan_tool_operating_spec("deep", "zh", 50)
    profile = select_granularity_profile(50, "zh", "deep")
    return copy.deepcopy(
        plan_import_pipeline(profile, tos, source_language="zh", prompt_profile="deep", chapter_count=50)
    )


class TestValidateImportPlan:
    def test_valid_deterministic_plan(self):
        ok, errors = validate_import_plan(_valid_plan())
        assert ok is True
        assert errors == []

    def test_valid_llm_proposed_plan(self):
        plan = _valid_plan()
        plan["planner_kind"] = "llm_proposed"
        ok, errors = validate_import_plan(plan)
        assert ok is True

    # ---- planner_kind --------------------------------------------------------

    def test_rejects_unknown_planner_kind(self):
        plan = _valid_plan()
        plan["planner_kind"] = "neural_planner"
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("planner_kind" in e for e in errors)

    # ---- source_type ---------------------------------------------------------

    def test_rejects_unknown_source_type(self):
        plan = _valid_plan()
        plan["source_type"] = "raw_fanfic"
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("source_type" in e for e in errors)

    # ---- tools list presence -------------------------------------------------

    def test_rejects_empty_tools_list(self):
        plan = _valid_plan()
        plan["tools"] = []
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("tools" in e for e in errors)

    def test_rejects_missing_tools_list(self):
        plan = _valid_plan()
        del plan["tools"]
        ok, errors = validate_import_plan(plan)
        assert not ok

    # ---- tool step validation ------------------------------------------------

    def test_rejects_unknown_tool(self):
        plan = _valid_plan()
        plan["tools"].append({"tool": "inject_beats", "enabled": True, "order": 99})
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("inject_beats" in e for e in errors)

    def test_rejects_duplicate_order(self):
        plan = _valid_plan()
        plan["tools"].append(copy.deepcopy(plan["tools"][0]))  # same order value
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("duplicate order" in e for e in errors)

    def test_rejects_missing_tool_key(self):
        plan = _valid_plan()
        plan["tools"].append({"enabled": True, "order": 99})
        ok, errors = validate_import_plan(plan)
        assert not ok

    def test_rejects_missing_enabled_key(self):
        plan = _valid_plan()
        plan["tools"].append({"tool": "judge_import", "order": 99})
        ok, errors = validate_import_plan(plan)
        assert not ok

    def test_rejects_missing_order_key(self):
        plan = _valid_plan()
        plan["tools"].append({"tool": "judge_import", "enabled": True})
        ok, errors = validate_import_plan(plan)
        assert not ok

    # ---- required tool presence + enabled ------------------------------------

    def test_rejects_missing_required_tool_proposal_write(self):
        plan = _valid_plan()
        plan["tools"] = [s for s in plan["tools"] if s.get("tool") != "proposal_write"]
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("proposal_write" in e for e in errors)

    def test_rejects_required_tool_disabled_proposal_write(self):
        plan = _valid_plan()
        for step in plan["tools"]:
            if step.get("tool") == "proposal_write":
                step["enabled"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("proposal_write" in e for e in errors)

    def test_rejects_required_tool_disabled_extract_character(self):
        plan = _valid_plan()
        for step in plan["tools"]:
            if step.get("tool") == "extract_character":
                step["enabled"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("extract_character" in e for e in errors)

    # ---- prompt_policy -------------------------------------------------------

    def test_rejects_missing_prompt_policy(self):
        plan = _valid_plan()
        del plan["prompt_policy"]
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("dynamic_prompt_edits_allowed" in e for e in errors)

    def test_rejects_dynamic_prompt_edits_true(self):
        plan = _valid_plan()
        plan["prompt_policy"]["dynamic_prompt_edits_allowed"] = True
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("dynamic_prompt_edits_allowed" in e for e in errors)

    # ---- cost_policy ---------------------------------------------------------

    def test_rejects_missing_cost_policy(self):
        plan = _valid_plan()
        del plan["cost_policy"]
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("stop_on_api_402" in e for e in errors)

    def test_rejects_stop_on_api_402_false(self):
        plan = _valid_plan()
        plan["cost_policy"]["stop_on_api_402"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("stop_on_api_402" in e for e in errors)

    # ---- safety --------------------------------------------------------------

    def test_rejects_missing_safety(self):
        plan = _valid_plan()
        del plan["safety"]
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("proposal_gate_required" in e for e in errors)

    def test_rejects_proposal_gate_required_false(self):
        plan = _valid_plan()
        plan["safety"]["proposal_gate_required"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("proposal_gate_required" in e for e in errors)

    def test_rejects_schema_validated_plan_false(self):
        plan = _valid_plan()
        plan["safety"]["schema_validated_plan"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("schema_validated_plan" in e for e in errors)

    def test_rejects_llm_planner_can_propose_only_false(self):
        plan = _valid_plan()
        plan["safety"]["llm_planner_can_propose_only"] = False
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert any("llm_planner_can_propose_only" in e for e in errors)

    # ---- accumulation --------------------------------------------------------

    def test_multiple_errors_all_reported(self):
        plan = _valid_plan()
        plan["planner_kind"] = "bad_kind"
        plan["prompt_policy"]["dynamic_prompt_edits_allowed"] = True
        ok, errors = validate_import_plan(plan)
        assert not ok
        assert len(errors) >= 2
