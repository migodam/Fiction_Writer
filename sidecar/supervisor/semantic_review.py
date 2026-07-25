"""Deterministic semantic-review contracts for W1 candidate handoff.

The extraction/organizer path may suggest a module, but it is never allowed to
silently make a cross-module canonical mutation.  This module keeps the
decision material JSON serializable so the reviewer, proposal writer, and
human gate can exchange the same durable records.
"""
from __future__ import annotations

import re
from typing import Any, Literal, NotRequired, TypedDict


class CandidateLedgerEntry(TypedDict):
    candidate_id: str
    raw_name: str
    normalized_name: str
    candidate_kind: Literal["character", "world_item", "organization", "location", "event", "relationship", "unknown"]
    source_spans: list[dict[str, Any]]
    evidence_refs: list[str]
    aliases: list[str]
    attributes: dict[str, Any]
    proposed_category: str
    proposed_container_id: str | None
    confidence: float
    classification_confidence: float
    status: Literal["collected", "review_required", "approved", "quarantined", "relocation_required", "committed"]
    reason_codes: list[str]


class WorldReviewDecision(TypedDict):
    item_id: str
    proposed_type: Literal["location", "organization", "cultivation", "rule", "object", "unknown", "character"]
    target_folder_id: str | None
    confidence: float
    evidence_refs: list[str]
    reason: str
    action: Literal["accept", "move", "hold", "reject"]


class RelocationPlan(TypedDict):
    plan_id: str
    source_candidate_id: str
    source_kind: str
    target_kind: str
    target_entity_id: str | None
    target_container_id: str | None
    field_merge_plan: dict[str, Any]
    evidence_refs: list[str]
    confidence: float
    reason_codes: list[str]
    requires_human_gate: bool
    status: Literal["proposed", "approved", "rejected", "committed", "blocked"]
    deterministic: bool


class SemanticAssessment(TypedDict):
    ledger: CandidateLedgerEntry
    decision: WorldReviewDecision
    relocation_plan: NotRequired[RelocationPlan]


_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_DIGIT_TO_ZH = str.maketrans("0123456789", "零一二三四五六七八九")
_TITLE_TOKENS = (
    "副掌门", "副门主", "大门主", "正门主", "掌门", "门主", "堂主", "长老",
    "供奉", "护法", "执事", "师父", "师傅", "师兄", "师姐", "师弟", "师妹",
)
_STRONG_ORG_DESCRIPTION = ("门派", "宗门", "帮派", "组织", "势力", "议事机构", "长老组成", "公会", "分堂")
_STRONG_LOCATION_DESCRIPTION = ("地点", "建筑", "位于", "坐落", "入口", "山谷", "山峰", "占据", "通道", "大殿")
_PERSON_OR_RELATIONSHIP_PHRASES = ("夫人", "表姐夫", "表姐", "妻子", "丈夫", "岳父", "岳母")
_PERSON_APPELLATION_SUFFIXES = ("父", "母", "兄", "弟", "姐", "妹", "叔", "伯", "婶", "姑", "爷", "奶")


def normalize_candidate_name(value: Any) -> str:
    """Normalize display/OCR variants without inventing a semantic identity."""
    text = str(value or "").strip().translate(_FULLWIDTH_DIGITS)
    text = re.sub(r"[\s\-_.·,，。]+", "", text)
    return text.translate(_DIGIT_TO_ZH)


def parse_person_title_expression(value: Any) -> tuple[str, str] | None:
    """Return ``(role, person_name)`` for title-plus-name expressions."""
    name = normalize_candidate_name(value)
    for title in _TITLE_TOKENS:
        if name.startswith(title) and 1 <= len(name) - len(title) <= 3:
            remainder = name[len(title):]
            if remainder not in {"会", "堂", "院", "门", "宗", "派"}:
                return title, remainder
        if name.endswith(title) and 1 <= len(name) - len(title) <= 3:
            return title, name[:-len(title)]
    return None


def character_identity_index(characters: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map normalized canonical names and aliases to registry ID/name pairs."""
    result: dict[str, tuple[str, str]] = {}
    for entity_id, candidate in characters.items():
        if not isinstance(candidate, dict):
            continue
        canonical = str(candidate.get("name") or candidate.get("canonical_name") or candidate.get("canonicalName") or entity_id).strip()
        for value in [canonical, *(candidate.get("aliases") or [])]:
            normalized = normalize_candidate_name(value)
            if normalized:
                result.setdefault(normalized, (str(entity_id), canonical))
    return result


def _candidate_evidence(candidate: dict[str, Any]) -> list[str]:
    raw = candidate.get("evidence_refs") or candidate.get("evidenceRefs") or []
    return [str(item) for item in raw if str(item)] if isinstance(raw, list) else []


def _candidate_spans(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    raw = candidate.get("source_spans") or candidate.get("sourceSpans") or []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def assess_world_candidate(
    *, candidate_id: str, raw_name: str, candidate: dict[str, Any],
    character_index: dict[str, tuple[str, str]], category: str, container_id: str | None,
) -> SemanticAssessment:
    """Build a pure, conservative semantic assessment for one World candidate."""
    normalized = normalize_candidate_name(raw_name)
    confidence = float(candidate.get("confidence") or 0.0)
    description = str(candidate.get("description") or candidate.get("summary") or candidate.get("notes") or "")
    evidence_refs = _candidate_evidence(candidate)
    ledger: CandidateLedgerEntry = {
        "candidate_id": candidate_id, "raw_name": raw_name, "normalized_name": normalized,
        "candidate_kind": "world_item", "source_spans": _candidate_spans(candidate),
        "evidence_refs": evidence_refs, "aliases": [raw_name] if raw_name != normalized else [],
        "attributes": dict(candidate.get("attributes") or {}) if isinstance(candidate.get("attributes"), dict) else {},
        "proposed_category": category, "proposed_container_id": container_id,
        "confidence": confidence, "classification_confidence": confidence,
        "status": "collected", "reason_codes": [],
    }
    title = parse_person_title_expression(raw_name)
    if title:
        role, person_name = title
        target = character_index.get(person_name)
        ledger["candidate_kind"] = "character"
        ledger["status"] = "relocation_required" if target else "quarantined"
        ledger["reason_codes"] = ["person_title_expression", "known_alias_match" if target else "unresolved_person_title"]
        decision: WorldReviewDecision = {
            "item_id": candidate_id, "proposed_type": "character", "target_folder_id": None,
            "confidence": 0.98 if target else confidence, "evidence_refs": evidence_refs,
            "reason": "人物职务与姓名混合表达，不能作为 World 条目", "action": "move" if target else "hold",
        }
        if not target:
            return {"ledger": ledger, "decision": decision}
        target_id, _target_name = target
        plan: RelocationPlan = {
            "plan_id": f"relocate_{candidate_id}_to_{target_id}", "source_candidate_id": candidate_id,
            "source_kind": "world_item", "target_kind": "character", "target_entity_id": target_id,
            "target_container_id": None,
            "field_merge_plan": {"aliases": [raw_name], "role": role, "evidence_refs": evidence_refs},
            "evidence_refs": evidence_refs, "confidence": 0.98,
            "reason_codes": ledger["reason_codes"], "requires_human_gate": False,
            "status": "approved", "deterministic": True,
        }
        return {"ledger": ledger, "decision": decision, "relocation_plan": plan}

    # A relation-bearing appellation without a stable person identity is not
    # durable World lore.  Keep it for the reviewer instead of inventing a
    # concept node that can later be accepted as canonical data.
    if (
        any(token in normalized for token in _PERSON_OR_RELATIONSHIP_PHRASES)
        or (len(normalized) >= 2 and normalized.endswith(_PERSON_APPELLATION_SUFFIXES))
    ):
        ledger["candidate_kind"] = "unknown"
        ledger["status"] = "quarantined"
        ledger["reason_codes"] = ["person_or_relationship_phrase"]
        return {"ledger": ledger, "decision": {
            "item_id": candidate_id, "proposed_type": "unknown", "target_folder_id": None,
            "confidence": confidence, "evidence_refs": evidence_refs,
            "reason": "亲属或配偶称谓缺少可确认的人物身份，需人工归属到人物或关系证据", "action": "hold",
        }}

    ambiguous_name = normalized in {"正门", "主门", "大门"}
    ambiguous_hall = normalized.endswith(("堂", "院")) and not any(
        hint in description for hint in (*_STRONG_ORG_DESCRIPTION, *_STRONG_LOCATION_DESCRIPTION)
    )
    ambiguous_council = normalized.endswith("会") and any(
        title in normalized for title in ("长老", "堂主", "掌门")
    ) and not any(hint in description for hint in _STRONG_ORG_DESCRIPTION)
    has_semantic_org_name = normalized.endswith(("门", "宗", "派", "会", "盟", "帮"))
    unknown_or_weak = confidence < 0.85 and (
        category in {"", "concept", "custom"}
        or (category in {"organization", "faction"} and not has_semantic_org_name)
    )
    if ambiguous_name or ambiguous_hall or ambiguous_council or unknown_or_weak:
        reasons = []
        if ambiguous_name:
            reasons.append("ambiguous_gate_or_role")
        if ambiguous_hall:
            reasons.append("ambiguous_hall")
        if ambiguous_council:
            reasons.append("ambiguous_council")
        if unknown_or_weak:
            reasons.append("low_confidence_unknown")
        ledger["candidate_kind"] = "unknown"
        ledger["status"] = "quarantined"
        ledger["reason_codes"] = reasons
        return {"ledger": ledger, "decision": {
            "item_id": candidate_id, "proposed_type": "unknown", "target_folder_id": None,
            "confidence": confidence, "evidence_refs": evidence_refs,
            "reason": "候选缺少可安全落入正式 World 的确定性证据", "action": "hold",
        }}

    ledger["candidate_kind"] = "organization" if category in {"organization", "faction"} else "location" if category == "location" else "world_item"
    ledger["status"] = "approved"
    return {"ledger": ledger, "decision": {
        "item_id": candidate_id,
        "proposed_type": "organization" if category in {"organization", "faction"} else "location" if category == "location" else "cultivation" if category == "cultivation_method" else "rule" if category in {"rule", "system"} else "object",
        "target_folder_id": container_id, "confidence": confidence, "evidence_refs": evidence_refs,
        "reason": "分类与确定性名称/上下文规则一致", "action": "accept",
    }}
