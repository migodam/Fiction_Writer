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


def _normalized(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", unicodedata.normalize("NFKC", text).lower())


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n。！？.!?;；]+", text) if part.strip()]


def _meaningfully_matches(entity_desc: str, snippets: list[str], names: list[str]) -> bool:
    """Use direct names and CJK clause/bigram overlap; Jaccard is only a backstop."""
    snippet_text = " ".join(snippets)
    normalized_snippet = _normalized(snippet_text)
    normalized_names = [_normalized(name) for name in names if _normalized(name)]
    if any(len(name) >= 2 and name in normalized_snippet for name in normalized_names):
        return True

    desc_tokens = _tokenize(entity_desc)
    snippet_tokens = _tokenize(snippet_text)
    if not desc_tokens or not snippet_tokens:
        return True
    shared = desc_tokens & snippet_tokens
    if len(shared) >= (1 if _is_cjk(entity_desc + snippet_text) else 2):
        return True
    for clause in _clauses(entity_desc):
        clause_tokens = _tokenize(clause)
        if clause_tokens and clause_tokens & snippet_tokens:
            return True
    # A small positive score avoids declaring a contradiction from differing prose.
    return _jaccard(desc_tokens, snippet_tokens) >= 0.12


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

        entity_to_cards: dict[str, list[dict]] = {}
        for card in evidence_cards:
            raw = card.get("raw") if isinstance(card.get("raw"), dict) else {}
            entity_ids = {
                str(value)
                for value in (
                    card.get("entityId"),
                    card.get("entity_id"),
                    raw.get("canonical_id"),
                    raw.get("event_id"),
                    *(card.get("candidate_ids") or []),
                )
                if value
            }
            for entity_id in entity_ids:
                entity_to_cards.setdefault(entity_id, []).append(card)

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
                or fields.get("sourceSegmentId")
                or fields.get("source_span")
                or fields.get("sourceSpan")
                or fields.get("evidence")
                or fields.get("evidence_card_id")
                or fields.get("evidenceCardId")
                or fields.get("evidence_refs")
                or fields.get("evidenceRefs")
                or entity_id in entity_to_cards
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

            cards = entity_to_cards.get(str(entity_id), [])
            snippets: list[str] = []
            token_count = 0
            for card in cards:
                raw_snippets = card.get("snippets") or []
                if isinstance(raw_snippets, str):
                    raw_snippets = [raw_snippets]
                for snippet in raw_snippets:
                    clean = str(snippet).strip()
                    estimate = max(1, len(clean) // 4)
                    if not clean or len(snippets) >= self.max_snippets or token_count + estimate > self.max_total_tokens:
                        continue
                    snippets.append(clean)
                    token_count += estimate
            snippets_consumed += len(snippets)

            if cards and not snippets:
                findings.append(self._finding(
                    "evidence_unusable",
                    f"Entity '{fields.get('name') or fields.get('title') or entity_id}' has evidence cards but no usable claim-local snippet",
                    "medium",
                    entity_refs=[entity_id],
                    evidence_refs=[card.get("card_id") or card.get("id") or entity_id for card in cards],
                    entity_id=entity_id,
                ))
                continue

            if snippets:
                entity_desc = (
                    fields.get("summary") or fields.get("description") or
                    fields.get("title") or fields.get("name") or ""
                )
                names = [fields.get("name", ""), fields.get("title", ""), *(fields.get("aliases") or [])]
                llm_result = self._llm_mismatch_check(entity_desc, snippets)
                is_mismatch = llm_result is True or (
                    llm_result is None and not _meaningfully_matches(entity_desc, snippets, names)
                )

                if is_mismatch and (_tokenize(entity_desc) or _tokenize(" ".join(snippets))):
                    findings.append(self._finding(
                        "evidence_entity_mismatch",
                        f"Entity '{entity_id}' description has no claim-level match in its evidence snippets",
                        "high",
                        entity_refs=[entity_id],
                        evidence_refs=[card.get("card_id") or card.get("id") or entity_id for card in cards],
                        entity_id=entity_id,
                    ))
                    repairs.append(self._repair(
                        "add_evidence_ref",
                        [entity_id],
                        f"Re-link or correct evidence for entity '{entity_id}'",
                        deterministic=False,
                    ))

        return self._build_report(findings, repairs, [], snippets_consumed)
