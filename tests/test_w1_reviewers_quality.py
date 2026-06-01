"""Zero-cost tests for QualityReviewer."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer


def _make_event_proposal(event_id, *, branch_id="main", order=1, timeline_class="canonical_event"):
    fields = {
        "title": f"Event {event_id}",
        "orderIndex": order,
        "branchId": branch_id,
        "timelineClass": timeline_class,
    }
    return {
        "id": f"prop_{event_id}",
        "operations": [{"op": "create", "entityType": "timeline_event", "entityId": event_id, "fields": fields}],
    }


def _make_char_proposal(char_id, name, *, summary="A well-developed character with a detailed backstory."):
    return {
        "id": f"prop_{char_id}",
        "operations": [{"op": "create", "entityType": "character", "entityId": char_id, "fields": {"name": name, "summary": summary}}],
    }


def _make_world_proposal(world_id, name, *, category="location", description="A notable place in the story world."):
    return {
        "id": f"prop_{world_id}",
        "operations": [{"op": "create", "entityType": "world", "entityId": world_id, "fields": {"name": name, "category": category, "description": description}}],
    }


def _make_rel_proposal(rel_id, *, evidence="They first met in Chapter 1 during the festival."):
    fields = {"sourceId": "char_1", "targetId": "char_2"}
    if evidence:
        fields["evidence"] = evidence
    return {
        "id": f"prop_{rel_id}",
        "operations": [{"op": "create", "entityType": "relationship", "entityId": rel_id, "fields": fields}],
    }


def _make_state(**overrides):
    state = {
        "proposals": [],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "converge_target": {},
        "manuscript_chapters": ["Chapter 1 content"],
    }
    state.update(overrides)
    return state


class TestQualityReviewer(unittest.TestCase):

    def setUp(self):
        self.reviewer = QualityReviewer()

    def test_quality_catches_50_trivial_events(self):
        proposals = [_make_event_proposal(f"ev_{i}", timeline_class="scene_beat") for i in range(50)]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("timeline_stream_of_consciousness", check_names)
        self.assertEqual(report["verdict"], "needs_repair")

    def test_quality_catches_single_root_branch(self):
        proposals = [_make_event_proposal(f"ev_{i}", branch_id="main", timeline_class="canonical_event") for i in range(10)]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("mainline_share_too_high", check_names)
        self.assertIn(report["verdict"], ("warn", "needs_repair", "needs_orchestrator_rerun"))

    def test_quality_catches_empty_world_containers(self):
        proposals = [_make_world_proposal("w1", "The Void", description="")]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("world_empty_container", check_names)

    def test_quality_catches_relationship_missing_evidence(self):
        proposals = [_make_rel_proposal("rel_1", evidence="")]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("relationship_no_evidence", check_names)

    def test_quality_catches_character_missing_major(self):
        state = _make_state(
            proposals=[],
            converge_target={"protagonist_list": ["Hero"]},
            entity_registry={"characters": {"char_1": {"name": "Villain"}}, "events": {}, "world": {}},
        )
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("character_missing_major", check_names)
        self.assertEqual(report["verdict"], "needs_orchestrator_rerun")
        self.assertTrue(any(r["theme"] == "character_undercoverage" for r in report["orchestrator_requests"]))

    def test_quality_pass_on_clean_state(self):
        proposals = [
            _make_char_proposal("char_1", "Hero", summary="A brave hero with a long complicated backstory."),
            _make_event_proposal("ev_1", branch_id="branch_arc1", timeline_class="canonical_event"),
            _make_event_proposal("ev_2", branch_id="branch_arc2", timeline_class="canonical_event"),
            _make_world_proposal("w1", "Verdant Forest"),
            _make_rel_proposal("rel_1"),
        ]
        state = _make_state(
            proposals=proposals,
            converge_target={"protagonist_list": ["Hero"]},
            entity_registry={"characters": {"char_1": {"name": "Hero"}}, "events": {}, "world": {}},
        )
        report = self.reviewer.review(state)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["findings"], [])

    def test_quality_token_ledger_is_zero_cost(self):
        state = _make_state()
        report = self.reviewer.review(state)
        ledger = report["token_cost_ledger"]
        self.assertFalse(ledger["live_model_calls"])
        self.assertFalse(ledger["full50_run"])
        self.assertIsNone(ledger["model_used"])
        self.assertEqual(ledger["estimated_api_calls"], 0)

    def test_quality_catches_character_repeated_phrase(self):
        # Summary contains a phrase that appears twice.
        repeated = "十三岁锦衣少年"
        proposals = [_make_char_proposal(
            "char_wuyan",
            "五言",
            summary=f"出生于武林世家，{repeated}，自幼习武，{repeated}，成为一代宗师。",
        )]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("character_repeated_phrase", check_names)
        # Repair must carry a frontend-executable op:update.
        repair = next(
            (r for r in report["local_repair_actions"] if r["action_type"] == "clean_repeated_phrase"),
            None,
        )
        self.assertIsNotNone(repair, "Expected a clean_repeated_phrase repair action")
        ops = repair.get("proposed_operations", [])
        self.assertTrue(ops, "Repair must have proposed_operations")
        self.assertEqual(ops[0]["op"], "update")
        self.assertEqual(ops[0]["entityType"], "character")
        self.assertEqual(ops[0]["entityId"], "char_wuyan")
        cleaned = ops[0]["fields"].get("summary", "")
        self.assertNotEqual(cleaned, "", "Cleaned summary must not be empty")
        self.assertLess(cleaned.count(repeated), 2, "Repeated phrase must appear fewer times after cleaning")

    def test_quality_duplicate_name_repair_has_executable_ops(self):
        proposals = [
            _make_char_proposal("char_han_1", "韩铸"),
            _make_char_proposal("char_han_2", "韩铸"),
            _make_char_proposal("char_han_3", "韩铸"),
        ]
        state = _make_state(proposals=proposals)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("character_duplicate_name", check_names)
        repair = next(
            (r for r in report["local_repair_actions"] if r["action_type"] == "merge_duplicate"),
            None,
        )
        self.assertIsNotNone(repair, "Expected a merge_duplicate repair action")
        ops = repair.get("proposed_operations", [])
        self.assertTrue(ops, "Duplicate repair must have proposed_operations")
        # All ops should be deletes targeting the non-primary IDs.
        for op in ops:
            self.assertEqual(op["op"], "delete")
            self.assertEqual(op["entityType"], "character")
        # Primary (char_han_1) must NOT appear in delete targets.
        delete_ids = {op["entityId"] for op in ops}
        self.assertNotIn("char_han_1", delete_ids)
        self.assertIn("char_han_2", delete_ids)
        self.assertIn("char_han_3", delete_ids)


if __name__ == "__main__":
    unittest.main()
