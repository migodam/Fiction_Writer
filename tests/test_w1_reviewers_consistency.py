"""Zero-cost tests for ConsistencyReviewer."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer


def _make_digest(characters=None, world_items=None, relationships=None, branches=None):
    return {
        "characters": characters or {},
        "world_items": world_items or {},
        "relationships": relationships or {},
        "timeline_branches": branches or [],
    }


def _make_state(registry=None, digest=None, **overrides):
    state = {
        "entity_registry": registry or {"characters": {}, "events": {}, "world": {}, "world_detailed": {}, "relationships": {}},
        "project_structure_digest": digest,
    }
    state.update(overrides)
    return state


class TestConsistencyReviewer(unittest.TestCase):

    def setUp(self):
        self.reviewer = ConsistencyReviewer()

    def test_consistency_catches_duplicate_character_across_two_imports(self):
        digest = _make_digest(characters={"existing_hero": {"name": "Hero"}})
        registry = {"characters": {"new_char_1": {"name": "Hero"}}, "events": {}, "world": {}, "world_detailed": {}, "relationships": {}}
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("character_duplicate_across_imports", check_names)
        self.assertEqual(report["verdict"], "needs_repair")

    def test_consistency_catches_branch_continuity_break(self):
        digest = _make_digest(branches=["branch_main"])
        registry = {
            "characters": {},
            "events": {"ev_1": {"branchId": "branch_arc2"}, "ev_2": {"branchId": "branch_arc3"}},
            "world": {},
            "world_detailed": {},
            "relationships": {},
        }
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("timeline_branch_continuity", check_names)

    def test_consistency_catches_world_item_conflict(self):
        digest = _make_digest(world_items={"w1": {"name": "Sect", "category": "location"}})
        registry = {
            "characters": {},
            "events": {},
            "world_detailed": {"w_new": {"name": "Sect", "category": "organization"}},
            "world": {},
            "relationships": {},
        }
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("world_item_conflict", check_names)
        self.assertEqual(report["verdict"], "needs_repair")

    def test_consistency_catches_redundant_relationship(self):
        digest = _make_digest(relationships={
            "rel_1": {"sourceId": "char_hero", "targetId": "char_villain"}
        })
        registry = {
            "characters": {},
            "events": {},
            "world": {},
            "world_detailed": {},
            "relationships": {
                "rel_new": {"sourceId": "char_hero", "targetId": "char_villain", "id": "rel_new"}
            },
        }
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("relationship_redundant", check_names)
        self.assertEqual(report["verdict"], "needs_repair")

    def test_consistency_pass_on_new_project(self):
        state = _make_state(digest=None)
        report = self.reviewer.review(state)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["findings"], [])

    def test_consistency_produces_manifest_revision_diffs(self):
        digest = _make_digest(characters={
            "existing_hanli": {"name": "韩立", "summary": "韩立，七玄门弟子，23岁入门，天赋平庸但意志坚定。"}
        })
        registry = {
            "characters": {"new_hanli": {"name": "韩立", "summary": "韩立，七玄门核心弟子，天赋卓越，已突破炼气期。"}},
            "events": {}, "world": {}, "world_detailed": {}, "relationships": {},
        }
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        self.assertIn("manifest_revision_diffs", report)
        diffs = report["manifest_revision_diffs"]
        self.assertTrue(len(diffs) > 0, "Expected at least one manifest_revision_diff")
        diff = diffs[0]
        for key in ("revision_id", "entity_type", "entity_id", "field", "old_value", "new_value", "action", "reason"):
            self.assertIn(key, diff)
        self.assertEqual(diff["entity_type"], "character")
        self.assertEqual(diff["action"], "protect")

    def test_manifest_revision_diff_absent_when_no_change(self):
        same_summary = "韩立，七玄门弟子，意志坚定。"
        digest = _make_digest(characters={"existing": {"name": "韩立", "summary": same_summary}})
        registry = {
            "characters": {"new": {"name": "韩立", "summary": same_summary}},
            "events": {}, "world": {}, "world_detailed": {}, "relationships": {},
        }
        state = _make_state(registry=registry, digest=digest)
        report = self.reviewer.review(state)
        self.assertEqual(report["manifest_revision_diffs"], [])


if __name__ == "__main__":
    unittest.main()
