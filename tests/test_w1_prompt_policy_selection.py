"""Tests for W1 prompt policy selection and sparse event prompt quality."""
from __future__ import annotations

import pytest

from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_SPARSE,
)
from sidecar.supervisor.prompt_policy import (
    choose_prompt_policy_patch,
    prompt_policy_decision,
)
from sidecar.supervisor.tools import _EVENT_PROMPT_BY_DENSITY


# ── 1. Dispatch identity ──────────────────────────────────────────────────────

def test_sparse_maps_to_sparse_not_arc():
    assert _EVENT_PROMPT_BY_DENSITY["sparse_turning_points"] is W1_EXTRACT_EVENTS_DEEP_SPARSE
    assert _EVENT_PROMPT_BY_DENSITY["sparse_turning_points"] is not W1_EXTRACT_EVENTS_DEEP_ARC


# ── 2. Sparse prompt — three-criteria gate strings ────────────────────────────

def test_sparse_prompt_contains_three_criteria_gate():
    p = W1_EXTRACT_EVENTS_DEEP_SPARSE
    assert "ALL THREE" in p
    assert "≤4 canonical_event" in p
    assert "confidence ≥ 0.90" in p
    assert "state_change is REQUIRED" in p
    assert "why_timeline_worthy is REQUIRED" in p


# ── 3. Sparse prompt — logistics exclusion ────────────────────────────────────

def test_sparse_prompt_explicitly_excludes_logistics():
    p = W1_EXTRACT_EVENTS_DEEP_SPARSE
    assert "supply-gathering" in p or "Logistics sequences" in p


# ── 4. Fixture: schema supports logistics demotion ───────────────────────────

def _make_logistics_event() -> dict:
    return {
        "dedupeKey": "hanlì_market_supplies_ch3",
        "eventClass": "scene_beat",
        "label": "韩立前往集市购买药材",
        "chapter": 3,
        "state_change": "",
        "why_timeline_worthy": "",
        "confidence": 0.45,
    }


def _make_breakthrough_event() -> dict:
    return {
        "dedupeKey": "hanlì_breakthrough_jizhu_ch7",
        "eventClass": "canonical_event",
        "label": "韩立冲破筑基期",
        "chapter": 7,
        "state_change": "韩立 advances to 筑基期",
        "why_timeline_worthy": "Permanent power-level advancement — defines protagonist arc and unlocks new faction interactions.",
        "confidence": 0.93,
    }


def test_sparse_logistics_fixture_schema():
    logistics = _make_logistics_event()
    breakthrough = _make_breakthrough_event()

    # Logistics event is a scene_beat with empty state fields and low confidence
    assert logistics["eventClass"] == "scene_beat"
    assert logistics["state_change"] == ""
    assert logistics["why_timeline_worthy"] == ""
    assert logistics["confidence"] < 0.90

    # Breakthrough event is canonical with required state fields and high confidence
    assert breakthrough["eventClass"] == "canonical_event"
    assert breakthrough["state_change"] != ""
    assert breakthrough["why_timeline_worthy"] != ""
    assert breakthrough["confidence"] >= 0.90


# ── 5. prompt_policy_decision v2 fields ──────────────────────────────────────

def _zh_50ch_profile() -> dict:
    return {
        "chapter_count": 50,
        "avg_chars_per_chapter": 2800,
        "source_language": "zh",
        "estimated_source_type": "coarse_webnovel",
        "dialogue_density_hint": "low",
        "named_entity_density_hint": "high",
    }


def test_policy_decision_v2_fields_present():
    profile = _zh_50ch_profile()
    patch = choose_prompt_policy_patch(profile)
    decision = prompt_policy_decision(profile, patch)

    assert decision["decision_version"] == "w1-prompt-policy-decision-v2"
    assert "chosen_density" in decision
    assert "reason_for_density" in decision
    assert "source_profile_signals" in decision
    assert "existing_timeline_topology_signals" in decision
    assert "reviewer_feedback_used" in decision


# ── 6. topology_signals=None is safe ─────────────────────────────────────────

def test_topology_signals_none_safe():
    profile = _zh_50ch_profile()
    patch = choose_prompt_policy_patch(profile)
    decision = prompt_policy_decision(profile, patch, topology_signals=None)

    topo = decision["existing_timeline_topology_signals"]
    assert topo["branch_count"] == 0
    assert topo["canonical_event_count"] == 0
    assert topo["scene_beat_count"] == 0


# ── 7. topology_signals from timeline_architecture ───────────────────────────

def test_topology_signals_from_timeline_architecture():
    profile = _zh_50ch_profile()
    patch = choose_prompt_policy_patch(profile)
    topo_dict = {
        "branches": [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}],
        "canonical_events": [{"id": f"e{i}"} for i in range(12)],
        "scene_beats": [{"id": f"sb{i}"} for i in range(5)],
        "density_policy": "sparse_turning_points",
    }
    decision = prompt_policy_decision(profile, patch, topology_signals=topo_dict)

    topo = decision["existing_timeline_topology_signals"]
    assert topo["branch_count"] == 3
    assert topo["canonical_event_count"] == 12
    assert topo["scene_beat_count"] == 5
    assert topo["density_policy"] == "sparse_turning_points"


# ── 8. CJK webnovel → sparse_turning_points density ──────────────────────────

def test_zh_webnovel_selects_sparse_density():
    profile = _zh_50ch_profile()
    patch = choose_prompt_policy_patch(profile)
    assert patch["event_density_strategy"] == "sparse_turning_points"
