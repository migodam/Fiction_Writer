"""Tests for sidecar/supervisor/quality.py — zero-cost import quality rubric."""
from __future__ import annotations

import unittest

from sidecar.supervisor.quality import evaluate_import_quality


def _make_valid_plan_state(**overrides) -> dict:
    """Minimal state with a valid import_plan and safety gates."""
    state = {
        "import_plan_validation": {"ok": True, "errors": []},
        "import_plan": {
            "planner_kind": "deterministic_rules",
            "source_type": "balanced_novel",
            "safety": {
                "proposal_gate_required": True,
                "schema_validated_plan": True,
                "llm_planner_can_propose_only": True,
            },
            "cost_policy": {"stop_on_api_402": True},
            "tools": [],
        },
        "source_profile": {"recommended_granularity_profile": "balanced_novel"},
        "converge_target": {"expected_min_characters": 0},
    }
    state.update(overrides)
    return state


def _make_char_proposal(char_id: str = "char_1", name: str = "Hero") -> dict:
    return {
        "id": f"prop_{char_id}",
        "operations": [{"op": "create", "entityType": "character", "entityId": char_id, "fields": {"name": name}}],
    }


def _make_event_proposal(event_id: str = "ev_1", *, branch_id: str = "main", order: int = 1) -> dict:
    fields: dict = {"title": "Event", "orderIndex": order}
    if branch_id:
        fields["branchId"] = branch_id
    return {
        "id": f"prop_{event_id}",
        "operations": [{"op": "create", "entityType": "timeline_event", "entityId": event_id, "fields": fields}],
    }


def _make_rel_proposal(rel_id: str = "rel_1", *, evidence: str = "met in chapter 1") -> dict:
    fields: dict = {"sourceId": "char_1", "targetId": "char_2"}
    if evidence:
        fields["evidence"] = evidence
    return {
        "id": f"prop_{rel_id}",
        "operations": [{"op": "create", "entityType": "relationship", "entityId": rel_id, "fields": fields}],
    }


def _make_world_proposal(world_id: str = "world_1", name: str = "Sect") -> dict:
    return {
        "id": f"prop_{world_id}",
        "operations": [{"op": "create", "entityType": "world", "entityId": world_id, "fields": {"name": name}}],
    }


class TestImportQualityRubric(unittest.TestCase):

    # ── 1. Empty state → warn, not fail ──────────────────────────────────────

    def test_empty_state_returns_warn_not_fail(self):
        result = evaluate_import_quality({})
        self.assertEqual(result["verdict"], "warn")
        self.assertEqual(result["hard_failures"], [])
        self.assertGreater(len(result["warnings"]), 0)

    # ── 2. Plan validation False → hard fail ─────────────────────────────────

    def test_plan_validation_false_causes_fail(self):
        state = _make_valid_plan_state(
            import_plan_validation={"ok": False, "errors": ["missing planner_kind"]}
        )
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("import_plan_validation" in f for f in result["hard_failures"]))
        self.assertEqual(result["checks"]["import_plan_validation"]["result"], "fail")

    # ── 3. Safety gate missing → hard fail ───────────────────────────────────

    def test_safety_gate_missing_causes_fail(self):
        state = _make_valid_plan_state()
        # Remove safety entirely
        state["import_plan"].pop("safety")
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("safety" in f for f in result["hard_failures"]))

    def test_safety_gate_proposal_gate_false_causes_fail(self):
        state = _make_valid_plan_state()
        state["import_plan"]["safety"]["proposal_gate_required"] = False
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "fail")

    # ── 4. Valid plan state with no proposals → warn ──────────────────────────

    def test_valid_plan_state_no_proposals_warns(self):
        state = _make_valid_plan_state(converge_target={"expected_min_characters": 10})
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "warn")
        self.assertEqual(result["hard_failures"], [])
        self.assertTrue(any("character" in w for w in result["warnings"]))

    # ── 5. Valid full state with proposals → pass ─────────────────────────────

    def test_valid_full_state_with_proposals_passes(self):
        state = _make_valid_plan_state(converge_target={"expected_min_characters": 1})
        state["inbox_proposals"] = [
            _make_char_proposal(),
            _make_event_proposal(branch_id="main", order=1),
        ]
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["hard_failures"], [])

    # ── 6. Relationship missing evidence → warn, not fail ────────────────────

    def test_relationship_no_evidence_warns(self):
        state = _make_valid_plan_state()
        state["inbox_proposals"] = [_make_rel_proposal(evidence="")]
        result = evaluate_import_quality(state)
        self.assertNotEqual(result["verdict"], "fail")
        self.assertTrue(any("relationship" in w.lower() for w in result["warnings"]))
        self.assertEqual(result["checks"]["relationship_evidence"]["result"], "warn")

    # ── 7. planner_proposal_validation False → hard fail ─────────────────────

    def test_planner_proposal_validation_false_causes_fail(self):
        state = _make_valid_plan_state(
            planner_proposal={"planner_kind": "llm_proposed"},
            planner_proposal_validation={"ok": False, "errors": ["unknown field: raw_prompt_text"]},
        )
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("planner_proposal_validation" in f for f in result["hard_failures"]))

    # ── 8. Token cost ledger is always zero-cost ──────────────────────────────

    def test_token_cost_ledger_always_zero_cost(self):
        result = evaluate_import_quality({})
        ledger = result["token_cost_ledger"]
        self.assertIs(ledger["live_model_calls"], False)
        self.assertIs(ledger["full50_run"], False)
        self.assertIsNone(ledger["model_used"])
        self.assertEqual(ledger["estimated_api_calls"], 0)

    # ── 9. Event missing branchId → warn ─────────────────────────────────────

    def test_event_missing_branch_id_warns(self):
        state = _make_valid_plan_state()
        state["inbox_proposals"] = [_make_event_proposal(branch_id="", order=1)]
        result = evaluate_import_quality(state)
        self.assertNotEqual(result["verdict"], "fail")
        self.assertTrue(any("branchId" in w for w in result["warnings"]))

    # ── 10. Proposal gate bypass → hard fail ─────────────────────────────────

    def test_proposal_gate_bypass_causes_fail(self):
        """If a planner_proposal is present but plan's planner_kind is still deterministic, fail."""
        state = _make_valid_plan_state(
            planner_proposal={"planner_kind": "llm_proposed"},
            planner_proposal_validation={"ok": True, "errors": []},
        )
        # import_plan still says deterministic_rules — gate bypass
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("gate" in f.lower() or "planner_kind" in f for f in result["hard_failures"]))

    # ── 11. Structured checks dict always present ─────────────────────────────

    def test_checks_dict_always_present(self):
        result = evaluate_import_quality({})
        self.assertIsInstance(result["checks"], dict)
        self.assertGreater(len(result["checks"]), 0)

    # ── 12. suggested_next_actions non-empty when warnings present ────────────

    def test_suggested_next_actions_present_when_warnings(self):
        state = _make_valid_plan_state(converge_target={"expected_min_characters": 5})
        result = evaluate_import_quality(state)
        if result["warnings"]:
            self.assertIsInstance(result["suggested_next_actions"], list)

    # ── 13. World/person boundary collision is soft warning ─────────────────

    def test_world_person_exact_name_collision_warns(self):
        state = _make_valid_plan_state(converge_target={"expected_min_characters": 1})
        state["inbox_proposals"] = [
            _make_char_proposal(name="青云宗"),
            _make_world_proposal(name="青云宗"),
        ]
        result = evaluate_import_quality(state)
        self.assertEqual(result["verdict"], "warn")
        self.assertEqual(result["checks"]["world_person_boundary"]["result"], "warn")
        self.assertTrue(any("world/person" in w for w in result["warnings"]))

    # ── 14. Prompt window count is reflected in zero-cost ledger ─────────────

    def test_token_cost_ledger_estimates_prompt_windows(self):
        state = {"prompt_windows": [{"id": "pwin_1"}, {"id": "pwin_2"}]}
        result = evaluate_import_quality(state)
        self.assertEqual(result["token_cost_ledger"]["estimated_prompt_windows"], 2)


if __name__ == "__main__":
    unittest.main()
