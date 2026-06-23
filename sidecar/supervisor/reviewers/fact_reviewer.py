"""Evidence-card-only fact checking for W1 import proposals."""
from __future__ import annotations

import re
import unicodedata
from typing import List, Literal, Optional

from sidecar.supervisor.reviewers.base import BaseReviewer
from sidecar.supervisor.reviewers.schemas import (
    RepairAction,
    ReviewFinding,
    ReviewReport,
)

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or",
    "he", "she", "his", "her", "they", "it", "was", "were", "had", "has",
    "with", "for", "that", "this", "but", "not", "are", "be", "been",
    "by", "as", "from", "have", "do", "did", "so", "we", "you", "i",
    "其", "的", "了", "在", "是", "和", "与", "也", "都", "不",
})


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[一-鿿぀-ヿ]", text))


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    text = text.lower()
    if _is_cjk(text):
        clean = re.sub(r"[^一-鿿぀-ヿa-z0-9]", "", text)
        tokens = {clean[i : i + 2] for i in range(len(clean) - 1)}
    else:
        tokens = set(re.sub(r"[^a-z0-9\s]", " ", text).split())
    return tokens - _STOPWORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class FactReviewer(BaseReviewer):
    def __init__(
        self,
        max_snippets: int = 5,
        max_total_tokens: int = 1000,
        mismatch_threshold: float = 0.05,
    ) -> None:
        self.max_snippets = max_snippets
        self.max_total_tokens = max_total_tokens
        self.mismatch_threshold = mismatch_threshold

    @property
    def reviewer_name(self) -> Literal["quality", "fact", "consistency"]:
        return "fact"

    def _llm_mismatch_check(
        self, entity_desc: str, snippets: List[str]
    ) -> Optional[bool]:
        return None

    def review(self, state: dict) -> ReviewReport:
        evidence_cards: list = state.get("evidence_cards") or []
        proposals = state.get("inbox_proposals", []) or state.get("proposals", []) or []

        findings: List[ReviewFinding] = []
        repairs: List[RepairAction] = []
        snippets_consumed = 0

        entity_to_card: dict[str, dict] = {}
        for card in evidence_cards:
            eid = card.get("entityId") or card.get("entity_id") or ""
            if eid:
                entity_to_card[eid] = card

        char_event_ops = [
            op
            for p in proposals
            for op in (p.get("operations") or [])
            if op.get("entityType", "") in {"character", "timeline_event"}
        ]

        for op in char_event_ops:
            entity_id = op.get("entityId", "?")
            fields = op.get("fields") or {}

            has_evidence = bool(
                fields.get("source_segment_id")
                or fields.get("source_span")
                or fields.get("evidence")
                or fields.get("evidence_card_id")
                or entity_id in entity_to_card
            )
            if not has_evidence:
                findings.append(self._finding(
                    "evidence_missing",
                    f"Entity '{fields.get('name') or fields.get('title') or entity_id}' has no evidence reference",
                    "medium",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))

            confidence = fields.get("confidence")
            if confidence is not None and float(confidence) < 0.65:
                findings.append(self._finding(
                    "low_confidence_entity",
                    f"Entity '{entity_id}' has confidence {confidence:.2f} (<0.65)",
                    "low",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))

            card = entity_to_card.get(entity_id)
            if card and snippets_consumed < self.max_snippets:
                entity_desc = (
                    fields.get("summary") or fields.get("description") or
                    fields.get("title") or fields.get("name") or ""
                )
                snippets = card.get("snippets") or []
                if isinstance(snippets, str):
                    snippets = [snippets]
                snippets = snippets[: self.max_snippets - snippets_consumed]
                snippets_consumed += len(snippets)

                snippet_text = " ".join(str(s) for s in snippets)
                desc_tokens = _tokenize(entity_desc)
                snip_tokens = _tokenize(snippet_text)

                llm_result = self._llm_mismatch_check(entity_desc, snippets)
                if llm_result is True:
                    is_mismatch = True
                elif llm_result is False:
                    is_mismatch = False
                else:
                    sim = _jaccard(desc_tokens, snip_tokens)
                    is_mismatch = sim < self.mismatch_threshold

                if is_mismatch and (desc_tokens or snip_tokens):
                    findings.append(self._finding(
                        "evidence_entity_mismatch",
                        f"Entity '{entity_id}' description does not match its evidence snippet (Jaccard below threshold)",
                        "high",
                        entity_refs=[entity_id],
                        evidence_refs=[card.get("card_id") or entity_id],
                        entity_id=entity_id,
                    ))
                    repairs.append(self._repair(
                        "add_evidence_ref",
                        [entity_id],
                        f"Re-link or correct evidence for entity '{entity_id}'",
                        deterministic=False,
                    ))

        return self._build_report(findings, repairs, [], snippets_consumed)
