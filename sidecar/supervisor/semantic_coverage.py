"""Pure, deterministic semantic acceptance checks for staged W1 artifacts.

This module deliberately has no file, database, network, proposal, or canonical
storage dependency.  It reports what must be repaired; a later integration owns
turning that report into a proposal gate.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable

from sidecar.supervisor.semantic_coverage_contracts import SemanticCoverageInput, SemanticCoverageReport


_DOMAINS = ("characters", "relationships", "world", "events", "scenes")
_LONG_TERM_RELATIONSHIPS = frozenset({"亲属关系", "师徒关系", "恋爱关系", "盟友关系", "竞争关系", "敌对关系", "政治关系", "组织隶属", "朋友关系"})
_EVENT_ACTION_MARKERS = ("选拔", "解惑", "护行", "承诺", "行礼", "战斗", "比试", "梦中", "冷冰冰")
_ROLE_OR_RANK_NAMES = frozenset({"内门", "外门", "内门弟子", "外门弟子", "正式弟子", "记名弟子", "护法", "堂主", "师兄", "师姐", "师弟", "师妹", "掌门", "门主", "长老", "执事"})
_AMBIGUOUS_INSTITUTION_SUFFIXES = ("堂", "院", "阁")
_LOCATION_EVIDENCE = ("地点", "建筑", "位于", "坐落", "入口", "山谷", "山峰", "占据", "通道")
_ORGANIZATION_EVIDENCE = ("门派", "宗门", "帮派", "组织", "势力", "议事机构", "长老组成", "公会", "分堂")
_PUNCTUATION = re.compile(r"[\s\-_.·,，。()（）\[\]{}]+")


def _json_safe(value: Any) -> Any:
    """Convert arbitrary staged values into deterministic JSON-safe values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        normalized = [_json_safe(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    if isinstance(value, set):
        return _json_safe(sorted(value, key=str))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def semantic_coverage_input_hash(payload: dict[str, Any]) -> str:
    """Return a stable hash independent of candidate/list ordering."""
    serialized = json.dumps(_json_safe(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _values(item: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = item.get(key)
        if isinstance(value, list):
            return value
        if value is not None:
            return [value]
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_identity(value: Any) -> str:
    return _PUNCTUATION.sub("", _text(value))


def _identity_terms(candidate: dict[str, Any]) -> set[str]:
    fields = candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}
    raw_terms = [_text(candidate.get("name")), *(_text(value) for value in _values(fields, "aliases", "alias"))]
    result: set[str] = set()
    for raw in raw_terms:
        normalized = _normalize_identity(raw)
        if normalized:
            result.add(normalized)
        parenthetical = re.findall(r"[（(]([^（）()]+)[）)]", raw)
        for term in parenthetical:
            nested = _normalize_identity(term)
            if nested:
                result.add(nested)
        base = re.split(r"[（(]", raw, maxsplit=1)[0]
        normalized_base = _normalize_identity(base)
        if normalized_base:
            result.add(normalized_base)
    return result


def _evidence_ids(candidate: dict[str, Any]) -> list[str]:
    fields = candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}
    values = _values(candidate, "evidence_refs", "evidenceRefs") + _values(fields, "evidence_refs", "evidenceRefs", "evidence")
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            evidence_id = _text(value.get("evidence_id") or value.get("id"))
        else:
            evidence_id = _text(value)
        if evidence_id and evidence_id not in result:
            result.append(evidence_id)
    return result


def _chapter_ids(candidate: dict[str, Any]) -> list[str]:
    fields = candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}
    chapter_ids = _values(candidate, "chapter_ids", "chapterIds") + _values(fields, "chapter_ids", "chapterIds", "chapter_id", "chapterId")
    for evidence in _values(candidate, "evidence_refs", "evidenceRefs"):
        if isinstance(evidence, dict):
            span = evidence.get("source_span") or evidence.get("sourceSpan")
            if isinstance(span, dict) and span.get("chapter_id"):
                chapter_ids.append(span["chapter_id"])
    return sorted({_text(value) for value in chapter_ids if _text(value)})


def _finding(code: str, severity: str, *, entity_ids: Iterable[str] = (), chapter_ids: Iterable[str] = (), evidence_refs: Iterable[str] = (), message: str, repair_action: str) -> dict[str, Any]:
    return {
        "code": code, "severity": severity, "entity_ids": sorted({_text(item) for item in entity_ids if _text(item)}),
        "chapter_ids": sorted({_text(item) for item in chapter_ids if _text(item)}),
        "evidence_refs": sorted({_text(item) for item in evidence_refs if _text(item)}),
        "message": message, "repair_action": repair_action,
    }


def _candidate_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}


def _candidate_id(candidate: dict[str, Any]) -> str:
    return _text(candidate.get("candidate_id") or candidate.get("id"))


def _coverage(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    chapter_ids = sorted({_text(chapter) for chunk in chunks for chapter in _values(chunk, "chapter_ids", "chapterIds") if _text(chapter)})
    rows.append({"domain": "chapters", "expected": len(chapter_ids), "observed": len(chapter_ids), "complete": len(chapter_ids), "failed": 0, "unknown": 0, "coverage_ratio": 1.0 if chapter_ids else 0.0})
    for domain in _DOMAINS:
        complete = failed = unknown = 0
        for chunk in chunks:
            status = _text((chunk.get("domain_status") or chunk.get("domainStatus") or {}).get(domain)).lower()
            if status in {"complete", "empty_valid"}:
                complete += 1
            elif status == "unknown":
                unknown += 1
                findings.append(_finding("chunk_domain_unknown", "blocking", entity_ids=[_text(chunk.get("chunk_id"))], chapter_ids=_values(chunk, "chapter_ids", "chapterIds"), message=f"Chunk semantic domain '{domain}' has unknown status.", repair_action="rerun_chunk"))
            else:
                failed += 1
                if status == "failed":
                    findings.append(_finding("chunk_domain_failed", "blocking", entity_ids=[_text(chunk.get("chunk_id"))], chapter_ids=_values(chunk, "chapter_ids", "chapterIds"), message=f"Chunk semantic domain '{domain}' failed.", repair_action="rerun_chunk"))
                else:
                    findings.append(_finding("chunk_domain_missing", "blocking", entity_ids=[_text(chunk.get("chunk_id"))], chapter_ids=_values(chunk, "chapter_ids", "chapterIds"), message=f"Chunk semantic domain '{domain}' has no durable status.", repair_action="rerun_chunk"))
        expected = len(chunks)
        rows.append({"domain": domain, "expected": expected, "observed": complete + failed + unknown, "complete": complete, "failed": failed, "unknown": unknown, "coverage_ratio": round(complete / expected, 4) if expected else 0.0})
    return rows, findings


def _character_checks(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    characters = [item for item in candidates if _text(item.get("entity_type")) == "character"]
    term_index: dict[str, set[str]] = defaultdict(set)
    by_id = {_candidate_id(item): item for item in characters}
    for item in characters:
        candidate_id = _candidate_id(item)
        for term in _identity_terms(item):
            term_index[term].add(candidate_id)
        fields = _candidate_fields(item)
        importance = _text(fields.get("importance") or fields.get("importance_level")).lower()
        is_major = importance in {"major", "core", "protagonist", "main"}
        evidence = _evidence_ids(item)
        if is_major and not evidence:
            findings.append(_finding("major_character_missing_evidence", "blocking", entity_ids=[candidate_id], chapter_ids=_chapter_ids(item), message="A major character has no source evidence.", repair_action="rerun_chunk"))
        if is_major and not _text(fields.get("background")):
            findings.append(_finding("major_character_missing_background", "blocking", entity_ids=[candidate_id], chapter_ids=_chapter_ids(item), evidence_refs=evidence, message="A major character has no background.", repair_action="rerun_chunk"))
    groups: dict[frozenset[str], set[str]] = {}
    for term, ids in term_index.items():
        if len(ids) > 1:
            groups.setdefault(frozenset(ids), set()).add(term)
    merge_candidates: list[dict[str, Any]] = []
    for ids, terms in sorted(groups.items(), key=lambda pair: (sorted(pair[0]), sorted(pair[1]))):
        candidate_ids = sorted(ids)
        evidence = [evidence for candidate_id in candidate_ids for evidence in _evidence_ids(by_id[candidate_id])]
        merge_candidates.append({"candidate_ids": candidate_ids, "identity_terms": sorted(terms), "evidence_refs": sorted(set(evidence)), "confidence": "high"})
        findings.append(_finding("character_alias_collision", "blocking", entity_ids=candidate_ids, evidence_refs=evidence, message="Multiple character candidates share an explicit canonical name or alias.", repair_action="merge"))
    return {"candidate_count": len(characters), "merge_candidates": merge_candidates}, findings


def _relationship_checks(candidates: list[dict[str, Any]], character_ids: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for item in candidates:
        if _text(item.get("entity_type")) != "relationship":
            continue
        candidate_id = _candidate_id(item)
        fields = _candidate_fields(item)
        source_id = _text(fields.get("source_id") or fields.get("sourceId"))
        target_id = _text(fields.get("target_id") or fields.get("targetId"))
        relationship_type = _text(fields.get("type") or fields.get("relationship_type") or fields.get("relationshipType"))
        label_text = " ".join([relationship_type, _text(fields.get("source_label") or fields.get("sourceLabel")), _text(fields.get("description"))])
        evidence = _evidence_ids(item)
        if any(marker in label_text for marker in _EVENT_ACTION_MARKERS):
            disposition = "event_participation"
            findings.append(_finding("relationship_event_action", "blocking", entity_ids=[candidate_id, source_id, target_id], evidence_refs=evidence, message="An event action or description was promoted to a long-term relationship.", repair_action="demote_to_evidence"))
        elif relationship_type not in _LONG_TERM_RELATIONSHIPS:
            disposition = "quarantine"
            findings.append(_finding("relationship_type_not_allowed", "blocking", entity_ids=[candidate_id, source_id, target_id], evidence_refs=evidence, message="Relationship type is outside the Chinese long-term relationship allowlist.", repair_action="quarantine"))
        else:
            disposition = "long_term_relationship"
        if source_id not in character_ids or target_id not in character_ids:
            findings.append(_finding("relationship_endpoint_missing", "blocking", entity_ids=[candidate_id, source_id, target_id], evidence_refs=evidence, message="A relationship endpoint is not a staged character.", repair_action="repair_link"))
        if not evidence:
            findings.append(_finding("relationship_missing_evidence", "blocking", entity_ids=[candidate_id], message="A long-term relationship has no source evidence.", repair_action="rerun_chunk"))
        dispositions.append({"relationship_id": candidate_id, "disposition": disposition, "ontology_type": relationship_type if disposition == "long_term_relationship" else None, "evidence_refs": evidence})
    return {"dispositions": dispositions}, findings


def _world_checks(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for item in candidates:
        if _text(item.get("entity_type")) != "world_item":
            continue
        candidate_id = _candidate_id(item)
        name = _text(item.get("name"))
        fields = _candidate_fields(item)
        declared_type = _text(fields.get("entity_type") or fields.get("world_entity_type") or fields.get("category"))
        folder_id = _text(fields.get("target_folder_id") or fields.get("targetFolderId") or fields.get("container_id") or fields.get("containerId"))
        description = " ".join(_text(fields.get(key)) for key in ("description", "summary", "notes"))
        evidence = _evidence_ids(item)
        if name in _ROLE_OR_RANK_NAMES:
            findings.append(_finding("world_role_or_rank_contamination", "blocking", entity_ids=[candidate_id], evidence_refs=evidence, message="A role or institutional rank was routed into World Model.", repair_action="quarantine"))
            decisions.append({"entity_id": candidate_id, "entity_type": declared_type or "unknown", "target_folder_id": folder_id or None, "action": "reject", "reason_codes": ["role_or_rank_contamination"]})
            continue
        if not folder_id:
            findings.append(_finding("world_missing_target_folder", "blocking", entity_ids=[candidate_id], evidence_refs=evidence, message="A World item has no stable target folder.", repair_action="repair_link"))
        if name.endswith(_AMBIGUOUS_INSTITUTION_SUFFIXES) and not any(token in description for token in (*_LOCATION_EVIDENCE, *_ORGANIZATION_EVIDENCE)):
            findings.append(_finding("world_ambiguous_institution", "warning", entity_ids=[candidate_id], evidence_refs=evidence, message="A hall, academy, or pavilion lacks evidence for location versus organization routing.", repair_action="request_human_review"))
            decisions.append({"entity_id": candidate_id, "entity_type": declared_type or "unknown", "target_folder_id": None, "action": "hold", "reason_codes": ["ambiguous_institution"]})
        else:
            decisions.append({"entity_id": candidate_id, "entity_type": declared_type or "unknown", "target_folder_id": folder_id or None, "action": "accept", "reason_codes": []})
    return {"decisions": decisions}, findings


def _linkage_checks(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    scene_ids = {_candidate_id(item) for item in candidates if _text(item.get("entity_type")) == "scene"}
    event_ids = {_candidate_id(item) for item in candidates if _text(item.get("entity_type")) == "timeline_event"}
    world_ids = {_candidate_id(item) for item in candidates if _text(item.get("entity_type")) == "world_item"}
    linked_events = linked_scenes = linked_world = 0
    for item in candidates:
        candidate_id = _candidate_id(item)
        kind = _text(item.get("entity_type"))
        fields = _candidate_fields(item)
        evidence = _evidence_ids(item)
        if kind == "scene":
            if _text(item.get("name")) in {"章节正文", "Chapter body", ""}:
                findings.append(_finding("scene_generic_title", "blocking", entity_ids=[candidate_id], evidence_refs=evidence, message="An accepted scene has a generic body title instead of an outline title.", repair_action="rerun_chunk"))
            linked = [_text(value) for value in _values(fields, "linked_event_ids", "linkedEventIds") if _text(value)]
            linked_events += len(linked)
            if not linked:
                findings.append(_finding("scene_missing_event_link", "warning", entity_ids=[candidate_id], evidence_refs=evidence, message="A scene has no linked event.", repair_action="repair_link"))
            for target in linked:
                if target not in event_ids:
                    findings.append(_finding("scene_event_link_missing_target", "blocking", entity_ids=[candidate_id, target], evidence_refs=evidence, message="A scene links to a missing event.", repair_action="repair_link"))
            world_links = [_text(value) for value in _values(fields, "linked_world_item_ids", "linkedWorldItemIds", "location_ids", "locationIds") if _text(value)]
            linked_world += len(world_links)
            for target in world_links:
                if target not in world_ids:
                    findings.append(_finding("scene_world_link_missing_target", "blocking", entity_ids=[candidate_id, target], evidence_refs=evidence, message="A scene links to a missing World item.", repair_action="repair_link"))
        if kind == "timeline_event":
            linked = [_text(value) for value in _values(fields, "linked_scene_ids", "linkedSceneIds") if _text(value)]
            linked_scenes += len(linked)
            if not linked:
                findings.append(_finding("event_missing_scene_link", "blocking", entity_ids=[candidate_id], evidence_refs=evidence, message="A canonical event has no linked scene.", repair_action="repair_link"))
            for target in linked:
                if target not in scene_ids:
                    findings.append(_finding("event_scene_link_missing_target", "blocking", entity_ids=[candidate_id, target], evidence_refs=evidence, message="An event links to a missing scene.", repair_action="repair_link"))
            world_links = [_text(value) for value in _values(fields, "linked_world_item_ids", "linkedWorldItemIds", "location_ids", "locationIds") if _text(value)]
            linked_world += len(world_links)
            for target in world_links:
                if target not in world_ids:
                    findings.append(_finding("event_world_link_missing_target", "blocking", entity_ids=[candidate_id, target], evidence_refs=evidence, message="An event links to a missing World item.", repair_action="repair_link"))
    return {"scene_count": len(scene_ids), "event_count": len(event_ids), "world_item_count": len(world_ids), "scene_to_event_links": linked_events, "event_to_scene_links": linked_scenes, "scene_or_event_to_world_links": linked_world}, findings


def compile_semantic_coverage(payload: SemanticCoverageInput | dict[str, Any]) -> SemanticCoverageReport:
    """Compile a deterministic, read-only semantic report for staged W1 input."""
    normalized = _json_safe(dict(payload))
    chunks = [item for item in normalized.get("chunks", []) if isinstance(item, dict)]
    candidates = [item for item in normalized.get("candidates", []) if isinstance(item, dict)]
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    infos: list[dict[str, Any]] = []
    for chunk in chunks:
        truth = _text(chunk.get("semantic_status") or chunk.get("truth"))
        if truth != "semantic_complete":
            blocking.append(_finding("chunk_not_semantically_complete", "blocking", entity_ids=[_text(chunk.get("chunk_id"))], chapter_ids=_values(chunk, "chapter_ids", "chapterIds"), message=f"Chunk truth is '{truth or 'missing'}', not semantic_complete.", repair_action="rerun_chunk"))
        if truth == "manuscript_only":
            infos.append(_finding("chunk_manuscript_preserved_only", "info", entity_ids=[_text(chunk.get("chunk_id"))], chapter_ids=_values(chunk, "chapter_ids", "chapterIds"), message="Manuscript text is preserved but semantic data is not acceptable for canonical commit.", repair_action="rerun_chunk"))
    coverage, coverage_findings = _coverage(chunks)
    blocking.extend(coverage_findings)
    character_report, character_findings = _character_checks(candidates)
    blocking.extend(character_findings)
    character_ids = {_candidate_id(item) for item in candidates if _text(item.get("entity_type")) == "character"}
    relationship_report, relationship_findings = _relationship_checks(candidates, character_ids)
    blocking.extend(relationship_findings)
    world_report, world_findings = _world_checks(candidates)
    for finding in world_findings:
        (warnings if finding["severity"] == "warning" else blocking).append(finding)
    linkage_report, linkage_findings = _linkage_checks(candidates)
    for finding in linkage_findings:
        (warnings if finding["severity"] == "warning" else blocking).append(finding)
    if blocking:
        verdict = "blocked"
    elif warnings:
        verdict = "warning"
    else:
        verdict = "pass"
    return {
        "contract_version": "w1-semantic-coverage-report/v1",
        "import_run_id": _text(normalized.get("import_run_id")), "lineage_id": _text(normalized.get("lineage_id")), "attempt_id": _text(normalized.get("attempt_id")),
        "input_hash": semantic_coverage_input_hash(normalized), "verdict": verdict,
        "blocking_findings": sorted(blocking, key=lambda item: (item["code"], item["entity_ids"])),
        "warnings": sorted(warnings, key=lambda item: (item["code"], item["entity_ids"])),
        "infos": sorted(infos, key=lambda item: (item["code"], item["entity_ids"])), "coverage": coverage,
        "character_merge_report": character_report, "relationship_report": relationship_report,
        "world_routing_report": world_report, "linkage_report": linkage_report,
        "acceptance_policy": {"automatic_acceptance": verdict == "pass", "requires_human_review": verdict == "warning", "blocks_package_acceptance": verdict == "blocked"},
        "generated_by": "deterministic",
    }
