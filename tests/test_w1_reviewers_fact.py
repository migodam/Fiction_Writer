"""Zero-cost tests for FactReviewer."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer


def _make_evidence_card(entity_id, description, *, snippet=""):
    return {
        "card_id": f"card_{entity_id}",
        "entityId": entity_id,
        "description": description,
        "snippets": [snippet] if snippet else [],
    }


def _make_char_proposal(entity_id, name, *, summary="", source_segment_id="", confidence=None):
    fields = {"name": name, "summary": summary}
    if source_segment_id:
        fields["source_segment_id"] = source_segment_id
    if confidence is not None:
        fields["confidence"] = confidence
    return {
        "id": f"prop_{entity_id}",
        "operations": [{"op": "create", "entityType": "character", "entityId": entity_id, "fields": fields}],
    }


def _make_state_with_cards(cards, proposals=None):
    return {
        "evidence_cards": cards,
        "proposals": proposals or [],
    }


class TestFactReviewer(unittest.TestCase):

    def setUp(self):
        self.reviewer = FactReviewer()

    def test_fact_catches_synthetic_mismatch(self):
        card = _make_evidence_card(
            "char_hero",
            "A fierce warrior who fights dragons",
            snippet="planted tomatoes in garden yesterday morning",
        )
        proposal = _make_char_proposal(
            "char_hero",
            "Hero",
            summary="A fierce warrior who fights dragons",
        )
        state = _make_state_with_cards([card], [proposal])
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("evidence_entity_mismatch", check_names)

    def test_fact_does_not_read_full_source_text(self):
        card = _make_evidence_card("char_1", "brave knight", snippet="brave knight battles")
        proposal = _make_char_proposal("char_1", "Sir Knight", summary="brave knight")
        state = _make_state_with_cards([card], [proposal])
        self.assertNotIn("chunks", state)
        report = self.reviewer.review(state)
        self.assertIsNotNone(report)
        self.assertIn(report["verdict"], ("pass", "warn", "needs_repair", "needs_orchestrator_rerun"))

    def test_fact_max_snippets_respected(self):
        reviewer = FactReviewer(max_snippets=2)
        cards = [
            _make_evidence_card(f"char_{i}", f"description {i}", snippet=f"snippet {i}")
            for i in range(10)
        ]
        proposals = [
            _make_char_proposal(f"char_{i}", f"Character {i}", summary=f"description {i}")
            for i in range(10)
        ]
        state = _make_state_with_cards(cards, proposals)
        report = reviewer.review(state)
        self.assertLessEqual(report["token_cost_ledger"]["estimated_prompt_windows"], 2)

    def test_fact_pass_on_matching_evidence(self):
        card = _make_evidence_card(
            "char_hero",
            "brave warrior fights enemies",
            snippet="brave warrior fights enemies in the northern plains",
        )
        proposal = _make_char_proposal(
            "char_hero",
            "Hero",
            summary="brave warrior fights enemies",
            source_segment_id="seg_1",
        )
        state = _make_state_with_cards([card], [proposal])
        report = self.reviewer.review(state)
        mismatch_findings = [f for f in report["findings"] if f["check_name"] == "evidence_entity_mismatch"]
        self.assertEqual(mismatch_findings, [])

    def test_fact_flags_missing_evidence(self):
        proposal = _make_char_proposal("char_orphan", "Orphan", summary="A character with no evidence trail")
        state = _make_state_with_cards([], [proposal])
        report = self.reviewer.review(state)
        check_names = [f["check_name"] for f in report["findings"]]
        self.assertIn("evidence_missing", check_names)


if __name__ == "__main__":
    unittest.main()
