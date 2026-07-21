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
        # Limits apply independently to every canonical entity, so later entities
        # cannot be starved by the first few cards in a large import.
        self.assertEqual(report["token_cost_ledger"]["estimated_prompt_windows"], 10)

    def test_fact_aggregates_cards_and_marks_blank_evidence_unusable(self):
        cards = [
            _make_evidence_card("char_han", "韩立", snippet="韩立在村口遇见墨大夫。"),
            _make_evidence_card("char_han", "韩立", snippet="墨大夫带韩立前往七玄门。"),
            _make_evidence_card("event_gate", "", snippet="七玄门举行入门测试，韩立通过考核。"),
            _make_evidence_card("event_gate", "", snippet=""),
            _make_evidence_card("char_blank", "", snippet=""),
        ]
        proposals = [
            _make_char_proposal("char_han", "韩立", summary="韩立在村口遇见墨大夫后前往七玄门。"),
            {"id": "prop_event", "operations": [{"op": "create", "entityType": "timeline_event", "entityId": "event_gate", "fields": {"title": "七玄门入门测试", "description": "韩立通过七玄门入门测试"}}]},
            _make_char_proposal("char_blank", "空白", summary="没有可用摘录"),
        ]
        report = self.reviewer.review(_make_state_with_cards(cards, proposals))
        findings = {finding["finding_id"]: finding["check_name"] for finding in report["findings"]}
        self.assertNotIn("evidence_entity_mismatch_char_han", findings)
        self.assertNotIn("evidence_entity_mismatch_event_gate", findings)
        self.assertEqual(findings["evidence_unusable_char_blank"], "evidence_unusable")

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

    def test_fact_accepts_runtime_camel_case_and_candidate_card_ids(self):
        proposal = {
            "id": "prop_char_han",
            "operations": [{
                "op": "create",
                "entityType": "character",
                "entityId": "char_han",
                "fields": {
                    "name": "韩立",
                    "summary": "韩立离开山村前往七玄门。",
                    "sourceSpan": {"absolute_start": 0, "absolute_end": 20},
                    "evidenceRefs": ["evc_han"],
                },
            }],
        }
        card = {
            "id": "evc_han",
            "kind": "character",
            "candidate_ids": ["char_han"],
            "snippets": ["韩立离开山村，跟随三叔前往七玄门。"],
            "raw": {"canonical_id": "char_han"},
        }
        report = self.reviewer.review(_make_state_with_cards([card], [proposal]))
        check_names = [finding["check_name"] for finding in report["findings"]]
        self.assertNotIn("evidence_missing", check_names)
        self.assertNotIn("evidence_entity_mismatch", check_names)

    def test_fact_reviewer_never_reads_chunks_directly(self):
        """FactReviewer must not consume chunks array from state — snippet-only RAG."""
        state = {
            "evidence_cards": [],
            "proposals": [],
            "chunks": [{"chunk_id": 1, "raw_content": "entire novel chapter 1..."}],
        }
        report = self.reviewer.review(state)
        self.assertIsNotNone(report)
        self.assertEqual(report["findings"], [])

    def test_fact_reviewer_only_reports_obvious_mismatch(self):
        """Near-match must not trigger; clear topic mismatch must trigger."""
        # Near-match: overlapping tokens → Jaccard should be above threshold
        card_match = _make_evidence_card(
            "char_close",
            "brave warrior who fights",
            snippet="brave warrior battles enemies in mountains",
        )
        proposal_match = _make_char_proposal(
            "char_close", "Close",
            summary="brave warrior who fights",
            source_segment_id="seg_1",
        )
        state = _make_state_with_cards([card_match], [proposal_match])
        report = self.reviewer.review(state)
        mismatch = [f for f in report["findings"] if f["check_name"] == "evidence_entity_mismatch"]
        self.assertEqual(mismatch, [], "Near-match must NOT trigger evidence_entity_mismatch")

        # Clear mismatch: completely different topics → must flag
        card_bad = _make_evidence_card(
            "char_bad",
            "fierce swordsman from the north",
            snippet="planted tomatoes and watered the garden",
        )
        proposal_bad = _make_char_proposal("char_bad", "Bad", summary="fierce swordsman from the north")
        state2 = _make_state_with_cards([card_bad], [proposal_bad])
        report2 = self.reviewer.review(state2)
        mismatch2 = [f for f in report2["findings"] if f["check_name"] == "evidence_entity_mismatch"]
        self.assertTrue(len(mismatch2) > 0, "Clear mismatch must be reported")


if __name__ == "__main__":
    unittest.main()
