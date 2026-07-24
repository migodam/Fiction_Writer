"""Focused contract tests for the opt-in W1 live planner boundary."""
from __future__ import annotations

import json

import pytest

from sidecar.models.state import (
    analyze_source_profile,
    plan_tool_operating_spec,
    select_granularity_profile,
)
from sidecar.supervisor.planner import planner_proposal_to_import_plan, validate_planner_proposal
from sidecar.supervisor.planner_llm import (
    PlannerUnknownOutcomeError,
    generate_live_planner_proposal,
)
from sidecar.supervisor.policy import _ensure_orchestrator_plan


def _state(*, context: dict | None = None) -> dict:
    chunks = [{"id": f"chunk_{index}", "content": f"第{index + 1}章 韩立进入七玄门。"} for index in range(3)]
    return {
        "chunks": chunks,
        "prompt_profile": "balanced",
        "source_language": "zh",
        "import_mode": "import_all",
        "use_supervisor": True,
        "context": context or {},
    }


def _proposal() -> dict:
    source_profile = analyze_source_profile([], source_language="zh", prompt_profile="balanced")
    profile = select_granularity_profile(3, "zh", "balanced", "import_all")
    return {
        "planner_kind": "llm_proposed",
        "source_profile": source_profile,
        "proposed_source_type": "balanced_novel",
        "proposed_granularity_profile": profile,
        "rationale": "three chapters have a stable mainline",
        "confidence": 0.8,
        "next_action": {"kind": "tool", "tool": "segment_manifest", "reason": "start"},
        "proposed_actions": [
            {"kind": "tool", "tool": "segment_manifest", "scope": "current_import", "reason": "start"},
            {"kind": "stop", "scope": "current_import", "reason": "await deterministic gate"},
        ],
        "evidence_questions": ["是否存在需要独立时间线分支的倒叙章节？"],
        "budget_adjustment": {"max_additional_calls": 1, "max_additional_cost_usd": 0.1},
        "prompt_policy_patch": {"require_source_provenance": True},
    }


def _callback(payload: dict) -> str:
    assert payload["schema"] == "PlannerProposal"
    return json.dumps(_proposal())


def test_default_mode_makes_zero_callback_calls() -> None:
    calls = 0

    def callback(_payload: dict) -> str:
        nonlocal calls
        calls += 1
        return json.dumps(_proposal())

    result = _ensure_orchestrator_plan(_state(context={"planner_model_callback": callback}))

    assert calls == 0
    assert result["import_plan_validation"]["ok"] is True
    assert "planner_decision_record" not in result


def test_live_mode_requires_explicit_approval_before_callback() -> None:
    calls = 0

    def callback(_payload: dict) -> str:
        nonlocal calls
        calls += 1
        return json.dumps(_proposal())

    result = _ensure_orchestrator_plan(_state(context={
        "llm_planner_mode": "live",
        "planner_model_callback": callback,
    }))

    assert calls == 0
    assert result["converge_status"] == "hard_fail"
    assert result["planner_decision_record"]["error_code"] == "approval_required"


def test_live_mode_uses_one_approved_callback_and_keeps_proposal_gate() -> None:
    calls = 0

    def callback(payload: dict) -> str:
        nonlocal calls
        calls += 1
        return _callback(payload)

    result = _ensure_orchestrator_plan(_state(context={
        "llm_planner_mode": "live",
        "planner_live_approval": {"approved": True, "decision_id": "decision_live_1"},
        "planner_model_callback": callback,
    }))

    assert calls == 1
    assert result["import_plan_validation"]["ok"] is True
    assert result["planner_decision_record"]["status"] == "accepted"
    assert result["planner_decision_record"]["approval_decision_id"] == "decision_live_1"
    assert result["import_plan"]["safety"]["proposal_gate_required"] is True
    assert result["import_plan"]["safety"]["llm_planner_can_propose_only"] is True


def test_unknown_tool_and_bounds_are_rejected_deterministically() -> None:
    invalid = _proposal()
    invalid["proposed_actions"] = [{"kind": "tool", "tool": "erase_project", "scope": "current_import"}]
    invalid["budget_adjustment"] = {"max_additional_calls": 3, "max_additional_cost_usd": 2.0}
    ok, errors = validate_planner_proposal(invalid)
    assert not ok
    assert any("erase_project" in error for error in errors)
    assert any("max_additional_calls" in error for error in errors)
    assert any("max_additional_cost_usd" in error for error in errors)


def test_live_mode_rejects_malformed_json_without_retry() -> None:
    calls = 0

    def callback(_payload: dict) -> str:
        nonlocal calls
        calls += 1
        return "not json"

    result = _ensure_orchestrator_plan(_state(context={
        "llm_planner_mode": "live",
        "planner_live_approval": {"approved": True, "decision_id": "decision_live_2"},
        "planner_model_callback": callback,
    }))

    assert calls == 1
    assert result["converge_status"] == "hard_fail"
    assert result["planner_decision_record"]["error_code"] == "response_invalid"


def test_unknown_outcome_never_retries_automatically() -> None:
    calls = 0

    def callback(_payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"status": "unknown_outcome"}

    with pytest.raises(PlannerUnknownOutcomeError):
        generate_live_planner_proposal(_state(context={
            "planner_live_approval": {"approved": True, "decision_id": "decision_live_3"},
        }), model_callback=callback)
    assert calls == 1


def test_live_planner_decision_record_is_stable_and_never_applies_budget() -> None:
    state = _state(context={
        "planner_live_approval": {"approved": True, "decision_id": "decision_live_4"},
    })
    first, first_record = generate_live_planner_proposal(state, model_callback=_callback)
    second, second_record = generate_live_planner_proposal(state, model_callback=_callback)

    assert first == second
    assert first_record["proposal_sha256"] == second_record["proposal_sha256"]
    assert first_record["budget_adjustment"] == {"max_additional_calls": 1, "max_additional_cost_usd": 0.1}
    plan = planner_proposal_to_import_plan(
        first,
        plan_tool_operating_spec("balanced", "zh", 3),
        source_language="zh",
        prompt_profile="balanced",
        chapter_count=3,
    )
    assert "budget_adjustment" not in plan
    assert plan["safety"]["proposal_gate_required"] is True
