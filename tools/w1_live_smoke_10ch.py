#!/usr/bin/env python3
"""Run a gated W1 10-chapter live smoke test.

This runner is intentionally conservative:
- no full50
- no provider key printed
- no live model call unless LIVE_SMOKE_APPROVED=1 and DEEPSEEK_API_KEY is set
- scratch project/output defaults to /tmp so benchmark artifacts are not
  accidentally staged in the repo
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE = (
    REPO_ROOT
    / "benchmark_results"
    / "w1_manuscript_smoke_20260526_091106"
    / "smoke_10_chapter"
    / "凡人修仙传_前10章.txt"
)
DEFAULT_OUTPUT_ROOT = Path("/tmp/narrative_ide_w1_live_smoke")
REQUIRED_IMPORT_ARTIFACTS = (
    "manifest.json",
    "prompt_windows.json",
    "evidence_cards.json",
    "cross_validation.json",
    "timeline_architecture.json",
    "review_report.json",
    "judge_artifact.json",
    "proposal_write_receipts.json",
    "raw_source.txt",
    "staged_manuscript_projection.json",
    "usage_ledger.json",
)
_SECRET_VALUE_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})", re.IGNORECASE)
_SECRET_FIELD_NAMES = {"api_key", "apikey", "authorization", "token", "password", "secret"}
_ZH_RELATIONSHIP_LABELS = frozenset({
    "家族关系", "情感关系", "竞争关系", "师徒关系", "结拜关系", "政治关系", "对立关系", "盟友关系",
})
_RELATIONSHIP_ONTOLOGY_TYPES = frozenset({
    "family", "romantic", "rivalry", "mentor_disciple", "sworn_brothers", "political", "conflict", "alliance",
})
_WORLD_CONTAMINATION_PATTERNS = (
    re.compile(r"人物关系"), re.compile(r"关系图"), re.compile(r"关系网"), re.compile(r"人物志"),
    re.compile(r"年表"), re.compile(r"时间线"), re.compile(r"timeline", re.IGNORECASE),
)
_WORLD_CONTAMINATION_FINDINGS = frozenset({"world_module_pollution", "world_module_contamination"})
_MAJOR_CHARACTER_MARKERS = frozenset({
    "protagonist", "main", "main_character", "main character", "lead", "hero",
    "主角", "主人公", "主要角色", "主要人物",
})
_ORGANIZATION_CATEGORIES = frozenset({"organization", "faction"})
_PERSON_TITLE_PATTERN = re.compile(r"(?:门主|掌门|堂主|护法|长老|大夫|师父|师傅|师兄|师姐|师弟|师妹|父|母|叔|伯|哥|姐|弟|妹)$")
_EVENT_ORGANIZATION_PATTERN = re.compile(r"(?:测试|考核|选拔|比试|决斗|大会|仪式|庆典|行动|战役|事件)$")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json_atomic(path: Path, payload: Any) -> None:
    """Write a status artifact that external watchdogs can read safely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _ensure_scratch_project(project_path: Path, project_name: str) -> None:
    """Create the minimum canonical folder layout W1 needs for proposals/artifacts."""
    for rel in [
        "system/imports",
        "writing/chapters",
        "writing/scenes",
        "writing/manuscript",
        "characters",
        "timeline",
        "world",
        "graph",
        "scripts",
        "storyboards",
        "schemas",
    ]:
        (project_path / rel).mkdir(parents=True, exist_ok=True)

    project_index = project_path / "project.json"
    if not project_index.exists():
        now = datetime.now(timezone.utc).isoformat()
        _write_json(
            project_index,
            {
                "schemaVersion": 5,
                "metadata": {
                    "schemaVersion": 5,
                    "projectId": f"w1_live_smoke_{project_path.name}",
                    "name": project_name,
                    "rootPath": str(project_path),
                    "storageMode": "nodefs",
                    "locale": "zh-CN",
                    "version": 5,
                    "createdAt": now,
                    "updatedAt": now,
                    "template": "blank",
                    "capabilities": {"import": True, "rag": False, "scripts": False},
                    "storageBackends": {"canonical": "project-folder-json", "rag": "project-folder-keyword-index"},
                    "futureBackends": [],
                },
            },
        )
    _write_json(project_path / "system" / "inbox.json", _read_json(project_path / "system" / "inbox.json", []))
    _write_json(project_path / "system" / "history.json", _read_json(project_path / "system" / "history.json", []))
    _write_json(project_path / "system" / "issues.json", _read_json(project_path / "system" / "issues.json", []))
    _write_json(project_path / "writing" / "manuscript" / "nodes.json", _read_json(project_path / "writing" / "manuscript" / "nodes.json", []))


def _latest_import_dir(project_path: Path) -> Path | None:
    imports_dir = project_path / "system" / "imports"
    if not imports_dir.exists():
        return None
    dirs = [p for p in imports_dir.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def _chapter_number(title: str) -> int | None:
    zh_digits = {
        "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    m = re.search(r"第\s*(\d+)\s*章", title)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*([零一二两三四五六七八九十]+)\s*章", title)
    if not m:
        return None
    text = m.group(1)
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = zh_digits.get(left, 1) if left else 1
        ones = zh_digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return zh_digits.get(text)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _count_items(payload: Any, key: str) -> int:
    return len(payload.get(key, [])) if isinstance(payload, dict) and isinstance(payload.get(key), list) else 0


def _receipt_entity_counts(receipts: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(receipts, dict):
        return counts
    for receipt in receipts.get("receipts", []):
        if not isinstance(receipt, dict) or not isinstance(receipt.get("entity_type"), str):
            continue
        entity_type = receipt["entity_type"]
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold().replace("-", " "), flags=re.UNICODE)


def _has_identity_disambiguation(character: dict[str, Any]) -> bool:
    for key in ("identityDisambiguation", "identity_disambiguation", "identityDisambiguator", "identity_disambiguator"):
        value = character.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and value:
            return True
    return False


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return False


def _is_major_character(character: dict[str, Any], recurring_character_ids: set[str]) -> bool:
    normalized_markers = {_normalize_text(marker) for marker in _MAJOR_CHARACTER_MARKERS}
    character_id = character.get("id") or character.get("entityId")
    return str(character_id) in recurring_character_ids or any(
        _normalize_text(str(character.get(key) or "")) in normalized_markers
        for key in ("role", "storyFunction", "story_function", "importance", "importanceTier")
    )


def _major_character_profile_gaps(characters: list[dict[str, Any]], timeline: Any) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    canonical_events = _safe_list(_safe_dict(timeline).get("canonical_events"))
    participation_counts: dict[str, int] = {}
    for event in canonical_events:
        fields = _safe_dict(event)
        participant_ids = fields.get("participantCharacterIds") or fields.get("character_ids") or fields.get("characterIds")
        for entity_id in _safe_list(participant_ids):
            if entity_id:
                key = str(entity_id)
                participation_counts[key] = participation_counts.get(key, 0) + 1
    recurring_character_ids = {
        character_id
        for character_id, count in participation_counts.items()
        if count >= max(2, (len(canonical_events) + 1) // 2)
    }
    note_keys = ("notes", "evidence_notes", "evidenceNotes", "source_notes", "sourceNotes")
    for character in characters:
        if not _is_major_character(character, recurring_character_ids) or not any(_has_content(character.get(key)) for key in note_keys):
            continue
        missing_fields = [key for key in ("background", "experience") if not _has_content(character.get(key))]
        if missing_fields:
            gaps.append({
                "id": character.get("id") or character.get("entityId"),
                "name": character.get("name") or character.get("canonical_name"),
                "missing_fields": missing_fields,
            })
    return gaps


def _proposal_operations(inbox: Any) -> list[dict[str, Any]]:
    proposals = inbox if isinstance(inbox, list) else _safe_dict(inbox).get("items") or _safe_dict(inbox).get("proposals")
    operations: list[dict[str, Any]] = []
    for proposal in _safe_list(proposals):
        if not isinstance(proposal, dict):
            continue
        operations.extend(operation for operation in _safe_list(proposal.get("operations")) if isinstance(operation, dict))
    return operations


def _review_findings(review_report: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for report in _safe_dict(_safe_dict(review_report).get("reviewer_reports")).values():
        findings.extend(finding for finding in _safe_list(_safe_dict(report).get("findings")) if isinstance(finding, dict))
    return findings


def _semantic_quality_metrics(
    inbox: Any, review_report: Any, usage_artifact: Any, source_language: str, staged_chapter_count: int, timeline: Any,
) -> dict[str, Any]:
    """Summarize only semantic conditions that make a smoke run unacceptable.

    This mirrors the authoritative diagnostics checks while retaining the raw reviewer
    findings for the smoke artifact. Low-severity thin-card findings are deliberately
    absent: they are useful review signals, not product-gate failures.
    """
    characters: dict[str, list[dict[str, Any]]] = {}
    characters_by_id: dict[str, dict[str, Any]] = {}
    illegal_tags: list[str] = []
    invalid_relationships: list[dict[str, Any]] = []
    world_contamination: list[str] = []
    organization_world_items: list[dict[str, Any]] = []
    branch_counts: dict[str, int] = {}
    for operation in _proposal_operations(inbox):
        fields = _safe_dict(operation.get("fields"))
        entity_type = str(operation.get("entityType") or operation.get("entity_type") or "")
        entity_id = fields.get("id") or fields.get("entityId") or operation.get("entityId") or operation.get("entity_id")
        if entity_type == "character":
            name = str(fields.get("name") or fields.get("canonical_name") or "").strip()
            if entity_id:
                characters_by_id[str(entity_id)] = fields
            if name:
                characters.setdefault(_normalize_text(name), []).append(fields)
        elif entity_type == "character_tag" and source_language == "zh":
            name = str(fields.get("name") or "").strip()
            if name and re.search(r"[A-Za-z]", name):
                illegal_tags.append(name)
        elif entity_type == "relationship":
            label = str(fields.get("type") or "").strip()
            ontology_type = str(fields.get("ontologyType") or fields.get("ontology_type") or fields.get("category") or "").strip().lower()
            invalid = bool(ontology_type and ontology_type not in _RELATIONSHIP_ONTOLOGY_TYPES)
            if source_language == "zh" and label and label not in _ZH_RELATIONSHIP_LABELS:
                invalid = True
            if invalid:
                invalid_relationships.append({"id": entity_id, "type": label, "ontology_type": ontology_type})
        elif entity_type in {"world", "world_item"}:
            name = str(fields.get("name") or "")
            if any(pattern.search(name) for pattern in _WORLD_CONTAMINATION_PATTERNS):
                world_contamination.append(name)
            category = str(fields.get("category") or fields.get("world_category") or "").casefold()
            container_id = str(fields.get("containerId") or fields.get("container_id") or "").casefold()
            if category in _ORGANIZATION_CATEGORIES or "organization" in container_id or "faction" in container_id:
                organization_world_items.append({"id": entity_id, "name": name})
        elif entity_type in {"timeline_event", "event"} and fields.get("timelineClass") == "canonical_event":
            branch_id = str(fields.get("branchId") or fields.get("branch_id") or "")
            if branch_id:
                branch_counts[branch_id] = branch_counts.get(branch_id, 0) + 1

    for event in _safe_list(_safe_dict(timeline).get("canonical_events")):
        branch_id = str(_safe_dict(event).get("branchId") or _safe_dict(event).get("branch_id") or "")
        if branch_id:
            branch_counts[branch_id] = max(branch_counts.get(branch_id, 0), sum(
                1
                for candidate in _safe_list(_safe_dict(timeline).get("canonical_events"))
                if str(_safe_dict(candidate).get("branchId") or _safe_dict(candidate).get("branch_id") or "") == branch_id
            ))

    duplicate_names = [
        {"name": records[0].get("name") or records[0].get("canonical_name"), "entity_ids": [record.get("id") for record in records]}
        for records in characters.values()
        if len(records) > 1 and not all(_has_identity_disambiguation(record) for record in records)
    ]
    findings = _review_findings(review_report)
    finding_names = [str(finding.get("check_name") or "") for finding in findings]
    high_evidence_entity_mismatch_count = sum(
        1
        for finding in findings
        if finding.get("check_name") == "evidence_entity_mismatch" and str(finding.get("severity") or "").casefold() == "high"
    )
    for finding in findings:
        if finding.get("check_name") != "character_duplicate_name":
            continue
        refs = [str(entity_id) for entity_id in _safe_list(finding.get("entity_refs")) if entity_id]
        records = [characters_by_id[entity_id] for entity_id in refs if entity_id in characters_by_id]
        if not records or not all(_has_identity_disambiguation(record) for record in records):
            duplicate_names.append({"finding_id": finding.get("finding_id"), "entity_ids": refs})
    budget_status = _safe_dict(_safe_dict(usage_artifact).get("budget_status"))
    remaining = _safe_dict(budget_status.get("remaining"))
    character_names = {
        _normalize_text(str(character.get("name") or character.get("canonical_name") or ""))
        for character in characters_by_id.values()
    }
    event_titles = {
        _normalize_text(str(_safe_dict(event).get("title") or _safe_dict(event).get("summary") or ""))
        for event in _safe_list(_safe_dict(timeline).get("canonical_events"))
    }
    person_as_world_organization = [
        item for item in organization_world_items
        if _normalize_text(str(item["name"])) in character_names or _PERSON_TITLE_PATTERN.search(str(item["name"]))
    ]
    event_as_world_organization = [
        item for item in organization_world_items
        if _normalize_text(str(item["name"])) in event_titles or _EVENT_ORGANIZATION_PATTERN.search(str(item["name"]))
    ]
    return {
        "duplicate_character_names": duplicate_names,
        "unresolved_evidence_missing_count": finding_names.count("evidence_missing"),
        "high_evidence_entity_mismatch_count": high_evidence_entity_mismatch_count,
        "evidence_unusable_count": finding_names.count("evidence_unusable"),
        "major_character_supported_profile_gaps": _major_character_profile_gaps(list(characters_by_id.values()), timeline),
        "person_as_world_organization": person_as_world_organization,
        "event_as_world_organization": event_as_world_organization,
        "branch_over_budget_count": max(
            finding_names.count("branch_over_budget"),
            sum(1 for count in branch_counts.values() if count > 10),
        ),
        "illegal_or_english_tags": sorted(set(illegal_tags)),
        "invalid_relationships": invalid_relationships,
        "world_contamination": sorted(set(world_contamination)),
        "reviewer_world_contamination_count": sum(name in _WORLD_CONTAMINATION_FINDINGS for name in finding_names),
        # A staged projection is the authoritative manuscript before acceptance.
        "unresolved_manuscript_empty_count": 0 if staged_chapter_count > 0 else finding_names.count("manuscript_empty"),
        "usage_ledger_exhausted": budget_status.get("exhausted") is True,
        "usage_ledger_over_cap": any(isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0 for value in remaining.values()),
        "reviewer_finding_counts": {name: finding_names.count(name) for name in sorted(set(finding_names)) if name},
    }


def _validate_source_spans(raw_source: str, source_hash: str, records: list[tuple[str, Any]]) -> list[str]:
    failures: list[str] = []
    for label, record in records:
        span = record.get("source_span") if isinstance(record, dict) else None
        if not isinstance(span, dict):
            failures.append(f"raw_source_span_missing:{label}")
            continue
        start, end = span.get("absolute_start"), span.get("absolute_end")
        if span.get("raw_source_hash") != source_hash:
            failures.append(f"raw_source_hash_mismatch:{label}")
            continue
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(raw_source):
            failures.append(f"raw_source_span_bounds_invalid:{label}")
            continue
        if span.get("substring_hash") != _sha256_text(raw_source[start:end]):
            failures.append(f"raw_source_span_hash_mismatch:{label}")
    return failures


def _find_usage_ledger(payload: Any, source: str, path: str = "$") -> dict[str, Any] | None:
    """Return only a complete provider-reported usage ledger; estimates are not usage."""
    if isinstance(payload, dict):
        input_tokens = payload.get("actual_input_tokens", payload.get("input_tokens", payload.get("prompt_tokens")))
        output_tokens = payload.get("actual_output_tokens", payload.get("output_tokens", payload.get("completion_tokens")))
        calls = payload.get("actual_calls", payload.get("api_call_count", payload.get("call_count", payload.get("calls_made", payload.get("api_calls")))))
        cost = payload.get("cost_usd")
        if (
            all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (input_tokens, output_tokens, calls))
            and isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
        ):
            return {
                "source": source,
                "path": path,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "call_count": calls,
                "cost_usd": cost,
            }
        for key, value in payload.items():
            found = _find_usage_ledger(value, source, f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found = _find_usage_ledger(value, source, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _quality_probe(project_path: Path, expected_import_run_id: str | None = None) -> dict[str, Any]:
    manuscript = _read_json(project_path / "manuscript.json", {})
    chapters = manuscript.get("chapters") if isinstance(manuscript, dict) else []
    if not isinstance(chapters, list):
        chapters = []
    inbox = _read_json(project_path / "system" / "inbox.json", [])
    nodes = _read_json(project_path / "writing" / "manuscript" / "nodes.json", [])
    latest = (
        project_path / "system" / "imports" / expected_import_run_id
        if expected_import_run_id
        else _latest_import_dir(project_path)
    )
    if latest is not None and not latest.is_dir():
        latest = None
    manifest = _read_json(latest / "manifest.json", {}) if latest else {}
    review_report = _read_json(latest / "review_report.json", {}) if latest else {}
    usage_artifact = _read_json(latest / "usage_ledger.json", {}) if latest else {}
    judge_artifact = _read_json(latest / "judge_artifact.json", {}) if latest else {}
    receipts = _read_json(latest / "proposal_write_receipts.json", {}) if latest else {}
    staged = _read_json(latest / "staged_manuscript_projection.json", {}) if latest else {}
    organizer = _read_json(latest / "organizer_output.json", {}) if latest else {}

    chapter_numbers = [_chapter_number(str(ch.get("title", ""))) for ch in chapters if isinstance(ch, dict)]
    duplicates = sorted({n for n in chapter_numbers if n is not None and chapter_numbers.count(n) > 1})
    blocked = [p for p in inbox if isinstance(p, dict) and (p.get("lastBlockReason") or p.get("requiresManualReview"))]
    empty_branches = []
    timeline = _read_json(latest / "timeline_architecture.json", {}) if latest else {}
    if isinstance(timeline, dict):
        events = timeline.get("canonical_events") or timeline.get("events") or []
        event_branch_ids = {e.get("branchId") or e.get("branch_id") for e in events if isinstance(e, dict)}
        for branch in timeline.get("branches", []) or []:
            if isinstance(branch, dict) and (branch.get("id") or branch.get("branchId")) not in event_branch_ids:
                empty_branches.append(branch.get("id") or branch.get("branchId"))

    raw_source_path = latest / "raw_source.txt" if latest else None
    raw_source = raw_source_path.read_text(encoding="utf-8") if raw_source_path and raw_source_path.is_file() else ""
    source_hash = manifest.get("source_hash") if isinstance(manifest, dict) else None
    source_records: list[tuple[str, Any]] = []
    if isinstance(manifest, dict):
        source_records.extend((f"manifest.segments[{index}]", segment) for index, segment in enumerate(manifest.get("segments", [])))
    if isinstance(staged, dict):
        source_records.extend((f"staged.chapters[{index}]", chapter) for index, chapter in enumerate(staged.get("chapters", [])))
        source_records.extend((f"staged.scene_documents[{index}]", scene) for index, scene in enumerate(staged.get("scene_documents", [])))
    raw_source_failures = []
    if raw_source_path is None or not raw_source_path.is_file():
        raw_source_failures.append("raw_source_missing")
    elif not isinstance(source_hash, str) or _sha256_text(raw_source) != source_hash:
        raw_source_failures.append("raw_source_hash_mismatch")
    else:
        raw_source_failures = _validate_source_spans(raw_source, source_hash, source_records)

    usage_ledger = _find_usage_ledger(usage_artifact, "usage_ledger")
    project_metadata = _safe_dict(_safe_dict(_read_json(project_path / "project.json", {})).get("metadata"))
    source_language = str(_safe_dict(manifest).get("source_language") or project_metadata.get("locale") or "").lower()
    source_language = "zh" if source_language.startswith("zh") else source_language
    semantic_quality = _semantic_quality_metrics(
        inbox, review_report, usage_artifact, source_language, _count_items(staged, "chapters"), timeline,
    )

    return {
        "project_path": str(project_path),
        "latest_import_dir": str(latest) if latest else None,
        "expected_import_run_id": expected_import_run_id,
        "artifact_import_run_id": manifest.get("import_run_id") if isinstance(manifest, dict) else None,
        "canonical_chapter_count": len(chapters) if isinstance(chapters, list) else 0,
        "canonical_manuscript_nodes_count": len(nodes) if isinstance(nodes, list) else 0,
        "staged_acceptance_required": staged.get("acceptance_required") if isinstance(staged, dict) else None,
        "staged_chapter_count": _count_items(staged, "chapters"),
        "staged_manuscript_nodes_count": _count_items(staged, "nodes"),
        "staged_scene_documents_count": _count_items(staged, "scene_documents"),
        "proposal_write_receipt_counts": _receipt_entity_counts(receipts),
        "proposal_write_declared_counts": receipts.get("proposal_counts", {}) if isinstance(receipts, dict) else {},
        "duplicate_chapter_numbers": duplicates,
        "inbox_count": len(inbox) if isinstance(inbox, list) else 0,
        "blocked_count": len(blocked),
        "empty_branch_ids": empty_branches,
        "review_status": review_report.get("status") if isinstance(review_report, dict) else None,
        "organizer_world_items": len(organizer.get("world_items", [])) if isinstance(organizer, dict) else 0,
        "organizer_excluded_items": len(organizer.get("excluded_items", [])) if isinstance(organizer, dict) else 0,
        "raw_source_evidence": {
            "source_hash": source_hash,
            "raw_source_hash": _sha256_text(raw_source) if raw_source else None,
            "validated_span_count": len(source_records) - len(raw_source_failures),
            "failures": raw_source_failures,
        },
        "usage_ledger": usage_ledger,
        "semantic_quality": semantic_quality,
        "missing_required_artifacts": [
            name for name in REQUIRED_IMPORT_ARTIFACTS if latest is None or not (latest / name).is_file()
        ],
    }


def _quality_probe_failures(probe: dict[str, Any]) -> list[str]:
    """Return smoke-quality failures that should make the runner non-zero.

    This is intentionally conservative: the live-smoke runner is a product gate,
    not a benchmark. A run that completes but produces no visible manuscript,
    duplicate chapters, empty branches, or blocked proposals is not acceptable.
    """
    failures: list[str] = []
    acceptance_required = probe.get("staged_acceptance_required") is True
    if acceptance_required:
        if int(probe.get("canonical_chapter_count") or 0) != 0:
            failures.append("canonical_chapters_written_before_acceptance")
        if int(probe.get("canonical_manuscript_nodes_count") or 0) != 0:
            failures.append("canonical_manuscript_nodes_written_before_acceptance")
        if int(probe.get("staged_chapter_count") or 0) != 10:
            failures.append("staged_chapter_count_not_10")
        if int(probe.get("staged_manuscript_nodes_count") or 0) != 20:
            failures.append("staged_manuscript_nodes_count_not_20")
        if int(probe.get("staged_scene_documents_count") or 0) != 10:
            failures.append("staged_scene_documents_count_not_10")
    else:
        if int(probe.get("canonical_chapter_count") or 0) != 10:
            failures.append("canonical_chapter_count_not_10")
        if int(probe.get("canonical_manuscript_nodes_count") or 0) <= 0:
            failures.append("canonical_manuscript_nodes_empty")
    receipt_counts = probe.get("proposal_write_receipt_counts") or {}
    if int(receipt_counts.get("chapter") or 0) != 10:
        failures.append("proposal_write_receipts_chapter_count_not_10")
    if int(receipt_counts.get("scene") or 0) != 10:
        failures.append("proposal_write_receipts_scene_count_not_10")
    if probe.get("duplicate_chapter_numbers"):
        failures.append("duplicate_chapter_numbers")
    if int(probe.get("blocked_count") or 0) > 0:
        failures.append("blocked_proposals")
    if probe.get("empty_branch_ids"):
        failures.append("empty_timeline_branches")
    if probe.get("review_status") in {"fail", "hard_fail"}:
        failures.append("review_status_failed")
    if probe.get("missing_required_artifacts"):
        failures.append("missing_required_artifacts")
    expected_run_id = probe.get("expected_import_run_id")
    if expected_run_id and probe.get("artifact_import_run_id") != expected_run_id:
        failures.append("import_run_id_mismatch")
    if probe.get("raw_source_evidence", {}).get("failures"):
        failures.append("raw_source_evidence_invalid")
    if not probe.get("usage_ledger"):
        failures.append("usage_ledger_missing")
    semantic = _safe_dict(probe.get("semantic_quality"))
    if semantic.get("duplicate_character_names"):
        failures.append("duplicate_canonical_character_names")
    if int(semantic.get("unresolved_evidence_missing_count") or 0) > 0:
        failures.append("unresolved_evidence_missing")
    if int(semantic.get("high_evidence_entity_mismatch_count") or 0) > 0:
        failures.append("high_evidence_entity_mismatch")
    if int(semantic.get("evidence_unusable_count") or 0) > 0:
        failures.append("evidence_unusable")
    if semantic.get("major_character_supported_profile_gaps"):
        failures.append("major_character_supported_profile_gaps")
    if semantic.get("person_as_world_organization"):
        failures.append("person_as_world_organization")
    if semantic.get("event_as_world_organization"):
        failures.append("event_as_world_organization")
    if int(semantic.get("branch_over_budget_count") or 0) > 0:
        failures.append("branch_density_over_budget")
    if semantic.get("illegal_or_english_tags"):
        failures.append("illegal_or_english_tags")
    if semantic.get("invalid_relationships"):
        failures.append("invalid_relationship_types")
    if semantic.get("world_contamination") or int(semantic.get("reviewer_world_contamination_count") or 0) > 0:
        failures.append("world_module_contamination")
    if int(semantic.get("unresolved_manuscript_empty_count") or 0) > 0:
        failures.append("manuscript_empty")
    if semantic.get("usage_ledger_exhausted"):
        failures.append("usage_ledger_exhausted")
    if semantic.get("usage_ledger_over_cap"):
        failures.append("usage_ledger_over_cap")
    return failures


def _artifact_secret_leaks(output_dir: Path) -> list[str]:
    """Scan every generated artifact without loading or printing any real key."""
    leaks: list[str] = []
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _SECRET_VALUE_PATTERN.search(text):
            leaks.append(str(path.relative_to(output_dir)))
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        stack = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, child in value.items():
                    is_safe_placeholder = child is None or (isinstance(child, str) and child in {"", "***", "[redacted]"})
                    if key.lower() in _SECRET_FIELD_NAMES and not is_safe_placeholder:
                        leaks.append(str(path.relative_to(output_dir)))
                        stack = []
                        break
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)
    return sorted(set(leaks))


def _redact_terminal_payload(value: Any, key: str = "") -> Any:
    if key.lower() in _SECRET_FIELD_NAMES:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(child_key): _redact_terminal_payload(child, str(child_key)) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_redact_terminal_payload(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_PATTERN.sub("[redacted]", value)
    return value


def _smoke_result_exit_code(result: dict[str, Any]) -> int:
    terminal = result.get("terminal", {}) if isinstance(result, dict) else {}
    probe = result.get("quality_probe", {}) if isinstance(result, dict) else {}
    errors = terminal.get("errors") if isinstance(terminal, dict) else None
    status = (
        terminal.get("status")
        or terminal.get("status_text")
        or ("error" if terminal.get("current_node") == "error" or errors else "done")
    )
    converge_status = terminal.get("converge_status")
    if status in {"error", "timeout", "stalled", "cleanup_timeout", "budget_exhausted", "auth_failed"}:
        return 1
    if converge_status in {"hard_fail", "failed"}:
        return 1
    if _quality_probe_failures(probe if isinstance(probe, dict) else {}):
        return 1
    return 0


async def _watch_streaming_updates(
    stream: Any,
    output_dir: Path,
    *,
    timeout_seconds: float,
    heartbeat_seconds: float,
    stalled_seconds: float | None = None,
    cleanup_timeout_seconds: float = 15.0,
    on_update: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Consume a stream with wall-clock, silence, and cleanup deadlines.

    The runner owns an async producer rather than a child process, so it cannot
    safely kill a process tree here.  It does, however, bound cancellation and
    records a failed cleanup instead of leaving a silent task invisible.
    """
    if timeout_seconds <= 0 or heartbeat_seconds <= 0 or cleanup_timeout_seconds <= 0:
        raise ValueError("watchdog timeouts must be greater than zero")
    if stalled_seconds is not None and stalled_seconds <= 0:
        raise ValueError("stalled_seconds must be greater than zero")
    start = time.monotonic()
    state: dict[str, Any] = {
        "last_update_at": start,
        "last_node": None,
        "update_count": 0,
    }
    updates: list[dict[str, Any]] = []
    watchdog_events: list[dict[str, Any]] = []
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    stop_heartbeat = asyncio.Event()

    def write_heartbeat() -> None:
        now = time.monotonic()
        payload = {
            "elapsed": round(now - start, 3),
            "last_update_age": round(now - state["last_update_at"], 3),
            "last_node": state["last_node"],
            "update_count": state["update_count"],
        }
        _write_json_atomic(output_dir / "heartbeat.json", payload)

    def record_watchdog_event(event_type: str, **details: Any) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "last_update_age_seconds": round(time.monotonic() - state["last_update_at"], 3),
            "last_node": state["last_node"],
            **details,
        }
        watchdog_events.append(event)
        _write_json_atomic(output_dir / "watchdog_events.json", watchdog_events)
        return event

    async def produce_updates() -> None:
        try:
            async for update in stream:
                await queue.put(("update", dict(update or {})))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(("error", exc))
        finally:
            await queue.put(("done", None))

    async def heartbeat() -> None:
        while not stop_heartbeat.is_set():
            write_heartbeat()
            print(
                "[live-smoke]",
                f"heartbeat elapsed={int(time.monotonic() - start)}s",
                f"last_node={state['last_node'] or '?'}",
                f"updates={state['update_count']}",
                flush=True,
            )
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=heartbeat_seconds)
            except TimeoutError:
                continue

    # Write immediately so an external watchdog has a status file even before
    # the first interval, or if a short stream completes before the task runs.
    write_heartbeat()
    producer = asyncio.create_task(produce_updates(), name="w1-live-smoke-producer")
    heartbeat_task = asyncio.create_task(heartbeat(), name="w1-live-smoke-heartbeat")
    terminal: dict[str, Any] = {"status": "done"}
    producer_cancelled_by_runner = False
    try:
        while True:
            remaining = timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                terminal = {"status": "timeout", "elapsed_seconds": int(time.monotonic() - start), "watchdog_events": [record_watchdog_event("wall_clock_timeout")]}
                break
            silence_remaining = (
                stalled_seconds - (time.monotonic() - state["last_update_at"])
                if stalled_seconds is not None
                else remaining
            )
            if stalled_seconds is not None and silence_remaining <= 0:
                terminal = {"status": "stalled", "watchdog_events": [record_watchdog_event("stream_stalled", stalled_seconds=stalled_seconds)]}
                break
            try:
                kind, value = await asyncio.wait_for(queue.get(), timeout=min(remaining, silence_remaining))
            except TimeoutError:
                now = time.monotonic()
                if stalled_seconds is not None and now - state["last_update_at"] >= stalled_seconds:
                    terminal = {"status": "stalled", "watchdog_events": [record_watchdog_event("stream_stalled", stalled_seconds=stalled_seconds)]}
                else:
                    terminal = {"status": "timeout", "elapsed_seconds": int(now - start), "watchdog_events": [record_watchdog_event("wall_clock_timeout")]}
                break
            if kind == "done":
                terminal = updates[-1] if updates else {"status": "done"}
                break
            if kind == "error":
                terminal = {"status": "error", "error_type": type(value).__name__, "error": str(value)}
                break

            update = value
            updates.append(update)
            state["last_update_at"] = time.monotonic()
            state["last_node"] = update.get("current_node") or update.get("current_tool")
            state["update_count"] += 1
            if on_update is not None:
                requested_terminal = on_update(update)
                if requested_terminal is not None:
                    terminal = requested_terminal
                    break
    finally:
        stop_heartbeat.set()
        write_heartbeat()
        if not producer.done():
            producer_cancelled_by_runner = True
            producer.cancel()
        try:
            await asyncio.wait_for(producer, timeout=cleanup_timeout_seconds)
        except TimeoutError:
            terminal = {
                "status": "cleanup_timeout",
                "watchdog_events": [record_watchdog_event("producer_cleanup_timeout", cleanup_timeout_seconds=cleanup_timeout_seconds)],
            }
        except asyncio.CancelledError:
            if not producer_cancelled_by_runner:
                raise
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    return updates, terminal


async def _run_live(args: argparse.Namespace, project_path: Path, output_dir: Path) -> dict[str, Any]:
    from sidecar.workflows.w1_import import run_streaming

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    import_run_id = f"live_smoke_{_timestamp()}_{uuid.uuid4().hex[:8]}"
    config = {
        "project_path": str(project_path),
        "source_file_path": str(args.source),
        "import_mode": args.import_mode,
        "prompt_profile": args.prompt_profile,
        "use_supervisor": True,
        "use_orchestrator": True,
        "custom_profile_config": {
            "extract_relationships": args.extract_relationships,
            "extract_world": args.extract_world,
            "extract_timeline": args.extract_timeline,
        },
        "profile_config": {
            "extract_relationships": args.extract_relationships,
            "extract_world": args.extract_world,
            "extract_timeline": args.extract_timeline,
        },
        "budget_policy": {
            "max_cost_usd": args.max_cost_usd,
            "max_input_tokens": args.max_input_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
            "max_calls": args.max_calls,
            "fail_on_unknown_pricing": True,
            "fail_on_missing_usage": True,
        },
        "rerun_cap": 0,
        "max_reruns": 0,
        "context": {
            "api_key": api_key,
            "model": args.model,
            "endpoint": args.endpoint,
            "prompt_profile": args.prompt_profile,
            "use_supervisor": True,
            "use_orchestrator": True,
        },
        "session_id": f"live_smoke_{_timestamp()}",
        "import_run_id": import_run_id,
    }
    safe_config = {**config, "context": {**config["context"], "api_key": "***"}}
    _write_json(output_dir / "run_config.safe.json", safe_config)

    start = time.time()
    updates: list[dict[str, Any]] = []

    def handle_update(update: dict[str, Any]) -> dict[str, Any] | None:
        updates.append(update)
        _write_json(output_dir / "updates.json", updates)
        errors = " ".join(map(str, update.get("errors", [])))
        print(
            "[live-smoke]",
            f"progress={update.get('progress')}",
            f"node={update.get('current_node') or update.get('current_tool') or '?'}",
            f"errors={len(update.get('errors', []) or [])}",
            flush=True,
        )
        if "402" in errors or "budget exhausted" in errors.lower() or "insufficient" in errors.lower():
            return {"status": "budget_exhausted", "update": update}
        if any(marker in errors.lower() for marker in ("401", "403", "unauthorized", "authentication", "invalid api key")):
            return {"status": "auth_failed", "update": update}
        return None

    try:
        _, terminal = await _watch_streaming_updates(
            run_streaming(str(project_path), config),
            output_dir,
            timeout_seconds=args.timeout_seconds,
            heartbeat_seconds=args.heartbeat_seconds,
            stalled_seconds=args.stalled_seconds,
            cleanup_timeout_seconds=args.cleanup_timeout_seconds,
            on_update=handle_update,
        )
    except Exception as exc:
        terminal = {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}

    probe = _quality_probe(project_path, expected_import_run_id=import_run_id)
    secret_leaks = _artifact_secret_leaks(output_dir)
    if secret_leaks:
        terminal = {"status": "error", "error": "secret_leakage_detected"}
    result = {
        "elapsed_seconds": int(time.time() - start),
        "terminal": _redact_terminal_payload(terminal),
        "quality_probe": probe,
        "secret_leak_artifacts": secret_leaks,
    }
    final_result_path = output_dir / "final_result.json"
    _write_json(final_result_path, result)
    if "final_result.json" in _artifact_secret_leaks(final_result_path.parent):
        result = {
            "elapsed_seconds": result["elapsed_seconds"],
            "terminal": {"status": "error", "error": "secret_leakage_detected"},
            "quality_probe": probe,
            "secret_leak_artifacts": ["final_result.json"],
        }
        _write_json(final_result_path, result)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gated W1 10-chapter live smoke runner")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--project-path", type=Path, default=None)
    parser.add_argument("--project-name", default="W1 Live Smoke 10 Chapters")
    parser.add_argument("--prompt-profile", default="deep", choices=["fast", "balanced", "deep", "custom"])
    parser.add_argument("--import-mode", default="import_all")
    parser.add_argument("--model", default="deepseek-v4-flash", choices=["deepseek-v4-flash", "deepseek-v4-pro"])
    parser.add_argument("--endpoint", default=os.environ.get("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/v1"))
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--heartbeat-seconds", type=float, default=15.0)
    parser.add_argument("--stalled-seconds", type=float, default=120.0, help="Stop a stream that produces no update for this long.")
    parser.add_argument("--cleanup-timeout-seconds", type=float, default=15.0, help="Maximum wait for cancelled async work to exit.")
    parser.add_argument("--max-cost-usd", type=float, default=3.0)
    parser.add_argument("--max-input-tokens", type=int, default=1_000_000)
    parser.add_argument("--max-output-tokens", type=int, default=250_000)
    parser.add_argument("--max-total-tokens", type=int, default=1_250_000)
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--extract-relationships", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--extract-world", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--extract-timeline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prepare-only", action="store_true", help="Create scratch project/output dirs and exit without live calls.")
    parser.add_argument("--reuse-project", action="store_true", help="Do not delete an existing scratch project path before running.")
    args = parser.parse_args(argv)
    if args.heartbeat_seconds <= 0 or args.stalled_seconds <= 0 or args.cleanup_timeout_seconds <= 0:
        parser.error("watchdog timeout values must be greater than zero")
    if args.stalled_seconds > args.timeout_seconds:
        parser.error("--stalled-seconds must not exceed --timeout-seconds")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.source.exists():
        print(f"ERROR: source file not found: {args.source}", file=sys.stderr)
        return 2

    run_id = _timestamp()
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    project_path = args.project_path or (output_dir / "project")
    if project_path.exists() and not args.reuse_project:
        shutil.rmtree(project_path)
    _ensure_scratch_project(project_path, args.project_name)

    setup = {
        "source": str(args.source),
        "project_path": str(project_path),
        "output_dir": str(output_dir),
        "prompt_profile": args.prompt_profile,
        "model": args.model,
        "endpoint_host": re.sub(r"//.*", "//***", args.endpoint),
        "budget": {
            "max_cost_usd": args.max_cost_usd,
            "max_input_tokens": args.max_input_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
            "max_calls": args.max_calls,
        },
        "rerun_cap": 0,
        "live_smoke_approved": os.environ.get("LIVE_SMOKE_APPROVED") == "1",
        "deepseek_api_key_set": bool(os.environ.get("DEEPSEEK_API_KEY")),
    }
    _write_json(output_dir / "setup.json", setup)
    print(json.dumps(setup, ensure_ascii=False, indent=2))

    if args.prepare_only:
        print("[w1-live-smoke] prepare-only complete; no model calls made.")
        return 0
    if os.environ.get("LIVE_SMOKE_APPROVED") != "1":
        print("[w1-live-smoke] skipped: set LIVE_SMOKE_APPROVED=1 to allow a 10-chapter live model run.")
        return 2
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("[w1-live-smoke] skipped: DEEPSEEK_API_KEY is not set.")
        return 2

    print(
        "[w1-live-smoke] outer hard-timeout recommendation: "
        "gtimeout --signal=TERM --kill-after=30s 1830s <runner-command> "
        "(exit 124 means the outer timeout fired).",
        flush=True,
    )

    result = asyncio.run(_run_live(args, project_path, output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _smoke_result_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
