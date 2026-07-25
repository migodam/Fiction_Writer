#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUMMARY_LENGTH_WARN = 1_200
SUMMARY_LINE_WARN = 8
TRAIT_NOISE_WARN = 0.35
BRANCH_DENSITY_WARN = 24
MAINLINE_DENSITY_WARN = 48

# World-item contamination: meta-documents / UI concepts that should not be world items
_CONTAMINATION_NAME_PATTERNS = [
    re.compile(r"人物关系"),
    re.compile(r"关系图"),
    re.compile(r"关系网"),
    re.compile(r"人物志"),
    re.compile(r"年表"),
    re.compile(r"时间线"),
    re.compile(r"timeline", re.IGNORECASE),
]

# Container keys considered cultivation-related for misclassification detection
_CULTIVATION_CONTAINERS: frozenset[str] = frozenset({
    "systems",
    "cultivation_methods",
    "cultivation_ranks",
    "cultivation_levels",
    "cultivation_stages",
    "techniques",
    "abilities",
})

_ZH_RELATIONSHIP_LABELS = frozenset({
    "亲属关系", "恋爱关系", "竞争关系", "师徒关系", "结拜关系", "政治关系", "敌对关系", "盟友关系",
    "朋友关系", "组织隶属",
})
_RELATIONSHIP_ONTOLOGY_TYPES = frozenset({
    "family", "romantic", "rivalry", "mentor_disciple", "sworn_brothers", "political", "conflict", "alliance",
    "friendship", "organization",
})
_MAJOR_CHARACTER_MARKERS = frozenset({
    "protagonist", "main", "main_character", "main character", "lead", "hero",
    "主角", "主人公", "主要角色", "主要人物",
})
_ORGANIZATION_CATEGORIES = frozenset({"organization", "faction"})
_PERSON_TITLE_PATTERN = re.compile(r"(?:门主|掌门|堂主|护法|长老|大夫|师父|师傅|师兄|师姐|师弟|师妹|父|母|叔|伯|哥|姐|弟|妹)$")
_EVENT_ORGANIZATION_PATTERN = re.compile(r"(?:测试|考核|选拔|比试|决斗|大会|仪式|庆典|行动|战役|事件)$")


class DiagnosticInputError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSource:
    project_path: Path
    import_run_id: str | None = None
    lineage_id: str | None = None
    attempt_id: str | None = None


@dataclass(frozen=True)
class ImportArtifactScope:
    import_run_id: str | None
    lineage_id: str | None
    attempt_id: str | None
    artifact_dir: Path | None
    layout: str


def _read_json(path: Path, *, required: bool = False, default: Any = None) -> Any:
    if not path.exists():
        if required:
            raise DiagnosticInputError(f"Required JSON file is missing: {path}")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DiagnosticInputError(f"Malformed JSON in {path}: {exc}") from exc


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _is_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text))


def _normalize_text(text: str) -> str:
    text = text.casefold().replace("-", " ")
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _attempt_dirs(imports_dir: Path) -> list[tuple[str, str, Path]]:
    attempts: list[tuple[str, str, Path]] = []
    if not imports_dir.is_dir():
        return attempts
    for lineage_dir in imports_dir.iterdir():
        attempts_dir = lineage_dir / "attempts"
        if not lineage_dir.is_dir() or not attempts_dir.is_dir():
            continue
        for attempt_dir in attempts_dir.iterdir():
            if attempt_dir.is_dir():
                attempts.append((lineage_dir.name, attempt_dir.name, attempt_dir))
    return attempts


def _canonical_import_dir(source: ImportSource) -> ImportArtifactScope:
    project_path = source.project_path
    imports_dir = project_path / "system" / "imports"
    lineage_id = source.lineage_id or source.import_run_id
    if source.attempt_id:
        if not lineage_id:
            raise DiagnosticInputError("--attempt-id requires --lineage-id or --import-run-id")
        attempt_dir = imports_dir / lineage_id / "attempts" / source.attempt_id
        if not attempt_dir.is_dir():
            raise DiagnosticInputError(f"Import attempt does not exist: {attempt_dir}")
        return ImportArtifactScope(lineage_id, lineage_id, source.attempt_id, attempt_dir, "attempt")

    if lineage_id:
        run_dir = imports_dir / lineage_id
        if not run_dir.is_dir():
            raise DiagnosticInputError(f"Import run does not exist: {run_dir}")
        attempts = _attempt_dirs(run_dir.parent)
        matching = [entry for entry in attempts if entry[0] == lineage_id]
        if matching:
            _, attempt_id, attempt_dir = max(matching, key=lambda entry: entry[2].stat().st_mtime)
            return ImportArtifactScope(lineage_id, lineage_id, attempt_id, attempt_dir, "attempt")
        return ImportArtifactScope(lineage_id, None, None, run_dir, "legacy_run")

    if not imports_dir.exists():
        return ImportArtifactScope(None, None, None, None, "none")

    candidates: list[tuple[float, ImportArtifactScope]] = []
    for lineage, attempt, attempt_dir in _attempt_dirs(imports_dir):
        candidates.append((attempt_dir.stat().st_mtime, ImportArtifactScope(lineage, lineage, attempt, attempt_dir, "attempt")))
    for path in imports_dir.iterdir():
        if path.is_dir() and not (path / "attempts").is_dir():
            candidates.append((path.stat().st_mtime, ImportArtifactScope(path.name, None, None, path, "legacy_run")))
    if not candidates:
        return ImportArtifactScope(None, None, None, None, "none")
    return max(candidates, key=lambda entry: entry[0])[1]


def _proposal_operations(inbox: Any) -> list[dict[str, Any]]:
    proposals = inbox if isinstance(inbox, list) else _safe_list(_safe_dict(inbox).get("items") or _safe_dict(inbox).get("proposals"))
    operations: list[dict[str, Any]] = []
    for proposal in proposals:
        for operation in _safe_list(_safe_dict(proposal).get("operations")):
            if isinstance(operation, dict):
                operations.append(operation)
    return operations


def _operation_fields(operation: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(operation.get("fields") or operation.get("data"))


def _entity_type(operation: dict[str, Any]) -> str:
    return str(operation.get("entityType") or operation.get("entity_type") or operation.get("type") or "unknown")


def _character_files(project_path: Path) -> list[dict[str, Any]]:
    chars_dir = project_path / "entities" / "characters"
    if not chars_dir.exists():
        return []
    characters: list[dict[str, Any]] = []
    for path in sorted(chars_dir.glob("*.json")):
        data = _read_json(path, default={})
        if isinstance(data, dict):
            characters.append(data)
    return characters


def _character_records(project_path: Path, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for operation in operations:
        if _entity_type(operation) == "character":
            records.append(_operation_fields(operation))
    records.extend(_character_files(project_path))
    return [record for record in records if isinstance(record, dict)]


def _character_traits(character: dict[str, Any]) -> list[str]:
    traits: list[str] = []
    for key in ("traits", "personality_traits"):
        for trait in _safe_list(character.get(key)):
            if isinstance(trait, str) and trait.strip():
                traits.append(trait.strip())
    return traits


def _summary_stats(characters: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for character in characters:
        summary = str(character.get("summary") or "")
        rows.append(
            {
                "id": character.get("id") or character.get("entityId"),
                "name": character.get("name") or character.get("canonical_name") or character.get("title"),
                "length": len(summary),
                "line_count": len([line for line in summary.splitlines() if line.strip()]),
            }
        )
    lengths = [row["length"] for row in rows]
    outliers = [
        row
        for row in rows
        if row["length"] > SUMMARY_LENGTH_WARN or row["line_count"] > SUMMARY_LINE_WARN
    ]
    outliers.sort(key=lambda row: (row["length"], row["line_count"]), reverse=True)
    return {
        "count": len(rows),
        "min": min(lengths) if lengths else 0,
        "max": max(lengths) if lengths else 0,
        "mean": round(statistics.fmean(lengths), 2) if lengths else 0,
        "median": round(statistics.median(lengths), 2) if lengths else 0,
        "outlier_count": len(outliers),
        "outliers": outliers[:10],
    }


def _trait_metrics(characters: list[dict[str, Any]]) -> dict[str, Any]:
    total_traits = 0
    duplicate_traits = 0
    noisy_traits = 0
    mixed_language_traits = 0
    multilingual_trait_sets = 0
    by_character = []

    for character in characters:
        traits = _character_traits(character)
        normalized = [_normalize_text(trait) for trait in traits if _normalize_text(trait)]
        counts = Counter(normalized)
        duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
        noisy_count = sum(
            1
            for trait in traits
            if len(trait) > 32
            or len(re.findall(r"[，,.;；。]", trait)) > 0
            or len(trait.split()) > 4
        )
        mixed_count = sum(1 for trait in traits if _is_cjk(trait) and _is_latin(trait))
        has_cjk = any(_is_cjk(trait) for trait in traits)
        has_latin = any(_is_latin(trait) for trait in traits)

        total_traits += len(traits)
        duplicate_traits += duplicate_count
        noisy_traits += noisy_count
        mixed_language_traits += mixed_count
        if has_cjk and has_latin:
            multilingual_trait_sets += 1

        if traits:
            by_character.append(
                {
                    "id": character.get("id") or character.get("entityId"),
                    "name": character.get("name") or character.get("canonical_name") or character.get("title"),
                    "trait_count": len(traits),
                    "duplicate_count": duplicate_count,
                    "noisy_count": noisy_count,
                    "mixed_language_trait_count": mixed_count,
                }
            )

    by_character.sort(
        key=lambda row: (
            row["duplicate_count"] + row["noisy_count"] + row["mixed_language_trait_count"],
            row["trait_count"],
        ),
        reverse=True,
    )
    score = (duplicate_traits + noisy_traits + mixed_language_traits) / total_traits if total_traits else 0
    return {
        "total_traits": total_traits,
        "duplicate_traits": duplicate_traits,
        "noisy_traits": noisy_traits,
        "mixed_language_trait_count": mixed_language_traits,
        "characters_with_multilingual_trait_sets": multilingual_trait_sets,
        "trait_duplication_noise_score": round(score, 4),
        "worst_characters": by_character[:10],
    }


def _group_distribution(project_path: Path, operations: list[dict[str, Any]], characters: list[dict[str, Any]]) -> dict[str, Any]:
    tags = _read_json(project_path / "entities" / "character-tags.json", default=[])
    tag_names: dict[str, str] = {}
    existing_distribution: Counter[str] = Counter()
    for tag in _safe_list(tags):
        tag_dict = _safe_dict(tag)
        tag_id = str(tag_dict.get("id") or "unknown")
        tag_name = str(tag_dict.get("name") or tag_id)
        tag_names[tag_id] = tag_name
        existing_distribution[tag_name] += len(_safe_list(tag_dict.get("characterIds")))

    proposal_distribution: Counter[str] = Counter()
    for character in characters:
        for tag_id in _safe_list(character.get("tagIds") or character.get("tag_ids")):
            tag_name = tag_names.get(str(tag_id), str(tag_id))
            proposal_distribution[tag_name] += 1

    proposed_tags: Counter[str] = Counter()
    for operation in operations:
        if _entity_type(operation) == "character_tag":
            fields = _operation_fields(operation)
            proposed_tags[str(fields.get("name") or fields.get("id") or "unknown")] += len(
                _safe_list(fields.get("characterIds"))
            )

    return {
        "existing_character_tags": dict(sorted(existing_distribution.items())),
        "character_record_tag_refs": dict(sorted(proposal_distribution.items())),
        "proposed_character_tags": dict(sorted(proposed_tags.items())),
    }


def _event_fingerprint(event: dict[str, Any]) -> str:
    title = str(event.get("title") or event.get("summary") or event.get("description") or "")
    return _normalize_text(title)


def _duplicate_event_clusters(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        fingerprint = _event_fingerprint(event)
        if fingerprint:
            exact[fingerprint].append(event)

    clusters = []
    for group in exact.values():
        if len(group) > 1:
            clusters.append(
                {
                    "size": len(group),
                    "titles": [str(event.get("title") or "") for event in group[:8]],
                    "event_ids": [event.get("event_id") or event.get("id") or event.get("entityId") for event in group[:8]],
                }
            )
    clusters.sort(key=lambda row: row["size"], reverse=True)
    return clusters


def _timeline_metrics(timeline: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    canonical_events = _safe_list(timeline.get("canonical_events"))
    if not canonical_events:
        canonical_events = [
            _operation_fields(operation)
            for operation in operations
            if _entity_type(operation) == "timeline_event"
        ]
    discarded = _safe_list(timeline.get("discarded_duplicates"))
    branches = _safe_list(timeline.get("branches"))
    branch_ids = {str(branch.get("id")) for branch in branches if isinstance(branch, dict) and branch.get("id")}
    for event in canonical_events:
        branch_id = event.get("branchId") or event.get("branch_id")
        if branch_id:
            branch_ids.add(str(branch_id))

    branch_counts: Counter[str] = Counter()
    order_indexes: dict[str, list[int]] = defaultdict(list)
    for event in canonical_events:
        branch_id = str(event.get("branchId") or event.get("branch_id") or "unknown")
        branch_counts[branch_id] += 1
        order_index = event.get("orderIndex") or event.get("order_index")
        if isinstance(order_index, int):
            order_indexes[branch_id].append(order_index)

    root_branch_id = str(timeline.get("root_branch_id") or "branch_main")
    mainline_count = branch_counts.get(root_branch_id, 0)
    if not mainline_count and "branch_main" in branch_counts:
        root_branch_id = "branch_main"
        mainline_count = branch_counts[root_branch_id]

    order_anomalies = []
    for branch_id, indexes in order_indexes.items():
        duplicates = len(indexes) - len(set(indexes))
        sorted_indexes = sorted(indexes)
        gaps = 0
        if sorted_indexes:
            gaps = max(sorted_indexes) - min(sorted_indexes) + 1 - len(set(sorted_indexes))
        if duplicates or gaps:
            order_anomalies.append({"branch_id": branch_id, "duplicate_order_indexes": duplicates, "order_gaps": gaps})

    max_branch_density = max(branch_counts.values()) if branch_counts else 0
    branch_count = len(branch_ids) if branch_ids else len(branch_counts)
    canonical_count = len(canonical_events)
    return {
        "branch_count": branch_count,
        "canonical_event_count": canonical_count,
        "event_duplicate_cluster_count": len(_duplicate_event_clusters(canonical_events)),
        "event_duplicate_clusters": _duplicate_event_clusters(canonical_events)[:10],
        "branch_distribution": dict(sorted(branch_counts.items())),
        "branch_density": {
            "max_events_per_branch": max_branch_density,
            "mean_events_per_branch": round(canonical_count / branch_count, 2) if branch_count else 0,
            "branches_over_budget": {
                branch_id: count for branch_id, count in sorted(branch_counts.items()) if count > BRANCH_DENSITY_WARN
            },
        },
        "mainline_density": {
            "root_branch_id": root_branch_id,
            "event_count": mainline_count,
            "share": round(mainline_count / canonical_count, 4) if canonical_count else 0,
        },
        "scene_beat_discard_counts": dict(Counter(str(item.get("timelineClass") or item.get("reason") or "discarded") for item in discarded if isinstance(item, dict))),
        "discard_count": len(discarded),
        "timeline_readability": {
            "events_per_branch_ratio": round(canonical_count / branch_count, 2) if branch_count else 0,
            "max_branch_density": max_branch_density,
            "mainline_share": round(mainline_count / canonical_count, 4) if canonical_count else 0,
            "order_anomaly_count": len(order_anomalies),
            "order_anomalies": order_anomalies[:10],
        },
    }


def _canonical_manuscript_projection_metrics(project_path: Path) -> dict[str, Any]:
    nodes_payload = _read_json(project_path / "writing" / "manuscript" / "nodes.json", default=[])
    nodes = _safe_list(nodes_payload)
    if isinstance(nodes_payload, dict):
        nodes = _safe_list(nodes_payload.get("nodes") or nodes_payload.get("items"))

    project_root = project_path.resolve()

    def safe_content_path(raw_path: Any) -> Path | None:
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None
        resolved = (project_root / candidate).resolve()
        try:
            resolved.relative_to(project_root)
        except ValueError:
            return None
        return resolved if resolved.is_file() else None

    def scene_content_path(node: dict[str, Any]) -> Path | None:
        # Prefer an explicit project-relative content path, then support both
        # the current split layout and the legacy manuscript-node layout.
        explicit = safe_content_path(
            node.get("contentPath") or node.get("content_path") or node.get("filePath")
        )
        if explicit:
            return explicit
        node_id = str(node.get("id") or "")
        scene_id = str(node.get("linkedSceneId") or "")
        candidates = []
        if scene_id:
            candidates.append(project_root / "writing" / "scenes" / f"{scene_id}.md")
        if node_id:
            candidates.append(project_root / "writing" / "manuscript" / f"{node_id}.md")
        for candidate in candidates:
            path = safe_content_path(str(candidate.relative_to(project_root)))
            if path:
                return path
        return None

    chapter_node_count = sum(
        1 for n in nodes if isinstance(n, dict) and n.get("type") == "chapter_outline"
    )
    scene_nodes_with_content = 0
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "scene_outline":
            continue
        md_path = scene_content_path(node)
        if md_path and md_path.read_text(encoding="utf-8").strip():
            scene_nodes_with_content += 1
    return {
        "node_count": len(nodes),
        "chapter_node_count": chapter_node_count,
        "scene_nodes_with_content": scene_nodes_with_content,
    }


def _staged_manuscript_projection_metrics(staged: dict[str, Any]) -> dict[str, Any]:
    nodes = _safe_list(staged.get("nodes"))
    scene_documents = _safe_list(staged.get("scene_documents"))
    return {
        "chapter_count": len(_safe_list(staged.get("chapters"))),
        "node_count": len(nodes),
        "chapter_node_count": sum(1 for node in nodes if _safe_dict(node).get("type") == "chapter_outline"),
        "scene_nodes_with_content": sum(
            1
            for document in scene_documents
            if str(_safe_dict(document).get("content") or _safe_dict(document).get("markdown") or "").strip()
        ),
        "scene_document_count": len(scene_documents),
    }


def _manuscript_projection_metrics(project_path: Path, staged: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonical_manuscript_projection_metrics(project_path)
    canonical["chapter_count"] = int(_chapter_quality_metrics(project_path).get("total_chapter_count") or 0)
    acceptance_required = staged.get("acceptance_required") is True
    staged_metrics = _staged_manuscript_projection_metrics(staged) if acceptance_required else {}
    effective = staged_metrics if acceptance_required else canonical
    return {
        "acceptance_required": acceptance_required,
        "source": "staged" if acceptance_required else "canonical",
        "chapter_count": int(effective.get("chapter_count") or 0),
        "node_count": int(effective.get("node_count") or 0),
        "chapter_node_count": int(effective.get("chapter_node_count") or 0),
        "scene_nodes_with_content": int(effective.get("scene_nodes_with_content") or 0),
        "scene_document_count": int(effective.get("scene_document_count") or 0),
        "canonical": canonical,
        "staged": staged_metrics,
    }


def _chapter_quality_metrics(project_path: Path) -> dict[str, Any]:
    chapter_dir = project_path / "writing" / "chapters"
    chapters = [
        record
        for path in sorted(chapter_dir.glob("*.json"))
        for record in [_read_json(path, default={})]
        if isinstance(record, dict) and record.get("id")
    ]
    source = "split_layout"
    if not chapters:
        manuscript = _safe_dict(_read_json(project_path / "manuscript.json", default={}))
        chapters = _safe_list(manuscript.get("chapters"))
        source = "legacy_manuscript"
    chapter_numbers: list[int] = []
    for ch in chapters:
        if isinstance(ch, dict):
            num = ch.get("chapterNumber", ch.get("orderIndex"))
            if isinstance(num, int):
                chapter_numbers.append(num)
    counts = Counter(chapter_numbers)
    duplicate_count = sum(1 for c in counts.values() if c > 1)
    return {
        "source": source,
        "total_chapter_count": len(chapters),
        "duplicate_chapter_number_count": duplicate_count,
    }


def _canonical_split_layout_metrics(project_path: Path) -> dict[str, Any]:
    chapters = _chapter_quality_metrics(project_path)
    scenes_dir = project_path / "writing" / "scenes"
    scene_meta = [
        record
        for path in sorted(scenes_dir.glob("*.meta.json"))
        for record in [_read_json(path, default={})]
        if isinstance(record, dict) and record.get("id")
    ]
    scene_content_count = sum(
        1 for scene in scene_meta if (scenes_dir / f"{scene['id']}.md").is_file()
    )
    nodes = _safe_list(_read_json(project_path / "writing" / "manuscript" / "nodes.json", default=[]))
    return {
        "chapter_count": chapters["total_chapter_count"],
        "scene_metadata_count": len(scene_meta),
        "scene_content_count": scene_content_count,
        "manuscript_node_count": len(nodes),
        "chapter_node_count": sum(1 for node in nodes if _safe_dict(node).get("type") == "chapter_outline"),
        "scene_node_count": sum(1 for node in nodes if _safe_dict(node).get("type") == "scene_outline"),
    }


def _durable_failure_metrics(import_dir: Path | None, total_chunks: int | None) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    by_chunk: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_domain: Counter[str] = Counter()
    if import_dir is not None:
        for path in sorted((import_dir / "chunks").glob("chunk_*_failures.json")):
            payload = _safe_dict(_read_json(path, default={}))
            chunk_id = payload.get("chunk_id")
            if not isinstance(chunk_id, int):
                match = re.search(r"chunk_(\d+)_failures\.json$", path.name)
                chunk_id = int(match.group(1)) if match else None
            for item in _safe_list(payload.get("failures")):
                item = _safe_dict(item)
                domain = str(item.get("label") or "unknown")
                record = {
                    "chunk_id": chunk_id,
                    "domain": domain,
                    "error": str(item.get("error") or "unknown failure"),
                    "path": str(path),
                }
                failures.append(record)
                if isinstance(chunk_id, int):
                    by_chunk[chunk_id].append(record)
                by_domain[domain] += 1
    expected = max(0, int(total_chunks or 0))
    domains = ("character", "event", "world", "relationship", "scene")
    return {
        "failure_artifact_count": len({record["path"] for record in failures}),
        "failure_count": len(failures),
        "failed_chunk_ids": sorted(by_chunk),
        "failed_chunk_count": len(by_chunk),
        "failures": failures[:100],
        "domain_coverage": {
            domain: {
                "expected_chunks": expected,
                "failed_chunks": sorted({chunk_id for chunk_id, items in by_chunk.items() if any(item["domain"] == domain for item in items)}),
                "failure_count": by_domain[domain],
                "status": "failed" if by_domain[domain] else "not_proven_by_failure_artifacts",
            }
            for domain in domains
        },
    }


def _timeline_branch_quality(timeline: dict[str, Any]) -> dict[str, Any]:
    branches = _safe_list(timeline.get("branches"))
    canonical_events = _safe_list(timeline.get("canonical_events"))
    active_branch_ids: set[str] = set()
    for event in canonical_events:
        if isinstance(event, dict):
            branch_id = event.get("branchId") or event.get("branch_id")
            if branch_id:
                active_branch_ids.add(str(branch_id))
            active_branch_ids.update(
                str(item) for item in _safe_list(event.get("sharedBranchIds")) if item
            )
    empty_count = sum(
        1 for branch in branches
        if isinstance(branch, dict) and branch.get("id") and str(branch["id"]) not in active_branch_ids
    )
    return {
        "total_branch_count": len(branches),
        "empty_branch_count": empty_count,
    }


def _world_quality_metrics(operations: list[dict[str, Any]]) -> dict[str, Any]:
    contamination_count = 0
    misclassification_count = 0
    container_ids = {
        str(_operation_fields(op).get("id") or op.get("entityId") or op.get("entity_id"))
        for op in operations
        if _entity_type(op) == "world_container"
    }
    dangling_container_references: list[dict[str, str]] = []
    for op in operations:
        if _entity_type(op) not in ("world_item", "world"):
            continue
        fields = _operation_fields(op)
        name = str(fields.get("name") or "")
        container_key = str(fields.get("container_key") or "")
        is_contamination = any(p.search(name) for p in _CONTAMINATION_NAME_PATTERNS)
        if is_contamination:
            contamination_count += 1
            if container_key in _CULTIVATION_CONTAINERS:
                misclassification_count += 1
        for field_name in ("containerId", "parentId"):
            referenced_id = str(fields.get(field_name) or "").strip()
            if referenced_id and referenced_id not in container_ids:
                dangling_container_references.append({
                    "item_id": str(fields.get("id") or op.get("entityId") or op.get("entity_id") or ""),
                    "name": name,
                    "field": field_name,
                    "referenced_id": referenced_id,
                })
    return {
        "contamination_count": contamination_count,
        "cultivation_misclassification_count": misclassification_count,
        "dangling_container_reference_count": len(dangling_container_references),
        "dangling_container_references": dangling_container_references[:20],
    }


_PROPOSAL_REFERENCE_FIELDS = {
    "character": (("linkedEventIds", "event"), ("eventIds", "event"), ("tagIds", "tag"), ("linkedSceneIds", "scene"), ("linkedWorldItemIds", "world_item")),
    "timeline_event": (("participantCharacterIds", "character"), ("character_ids", "character"), ("branchId", "branch"), ("linkedSceneIds", "scene"), ("linkedWorldItemIds", "world_item"), ("locationIds", "world_item"), ("sharedBranchIds", "branch")),
    "timeline_branch": (("parentBranchId", "branch"), ("forkEventId", "event"), ("mergeEventId", "event"), ("mergeTargetBranchId", "branch")),
    "relationship": (("sourceId", "character"), ("targetId", "character"), ("sourceCharacterId", "character"), ("targetCharacterId", "character")),
    "scene": (("chapterId", "chapter"), ("linkedCharacterIds", "character"), ("povCharacterId", "character"), ("linkedEventIds", "event"), ("linkedWorldItemIds", "world_item")),
    "chapter": (("sceneIds", "scene"),),
    "world_item": (("containerId", "world_container"), ("parentId", "world_parent"), ("linkedCharacterIds", "character"), ("linkedEventIds", "event"), ("linkedSceneIds", "scene")),
    "character_tag": (("characterIds", "character"),),
}


def _proposal_reference_closure_metrics(project_path: Path, inbox: Any, timeline: dict[str, Any] | None = None) -> dict[str, Any]:
    canonical: dict[str, set[str]] = defaultdict(set)
    for path in project_path.glob("**/*.json"):
        if "/system/imports/" in str(path):
            continue
        payload = _read_json(path, default=None)
        relative = path.relative_to(project_path).as_posix()
        file_type = None
        if relative in {"entities/character-tags.json", "entities/character_tags.json"}:
            file_type = "tag"
        elif relative.startswith("entities/characters/"):
            file_type = "character"
        elif relative == "entities/timeline/branches.json":
            file_type = "branch"
        elif relative.startswith("entities/timeline/"):
            file_type = "event"
        elif relative.startswith("writing/chapters/"):
            file_type = "chapter"
        elif relative.startswith("writing/scenes/") and relative.endswith(".meta.json"):
            file_type = "scene"
        elif relative == "entities/world/containers.json":
            file_type = "world_container"
        elif relative.startswith("entities/world/") and Path(relative).name not in {
            "categories.json", "containers.json", "maps.json", "settings.json",
        }:
            file_type = "world_item"
        if file_type:
            for record in payload if isinstance(payload, list) else [payload]:
                if isinstance(record, dict) and record.get("id"):
                    canonical[file_type].add(str(record["id"]))
        for record in (payload if isinstance(payload, list) else [payload]):
            if isinstance(record, dict) and record.get("id") and record.get("entityType"):
                canonical[str(record["entityType"])].add(str(record["id"]))
    # Import artifacts describe intended output, not accepted canonical state.
    # Treating their IDs as canonical would hide precisely the case where an
    # artifact entity was omitted from the proposal package.
    proposals = inbox if isinstance(inbox, list) else _safe_list(_safe_dict(inbox).get("items") or _safe_dict(inbox).get("proposals"))
    creates: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    references = []
    for proposal in proposals:
        proposal_dict = _safe_dict(proposal)
        for operation in _safe_list(_safe_dict(proposal).get("operations")):
            if not isinstance(operation, dict):
                continue
            entity_type = _entity_type(operation)
            fields = _operation_fields(operation)
            package_id = str(
                proposal_dict.get("importRunId")
                or proposal_dict.get("packageId")
                or fields.get("importRunId")
                or fields.get("import_run_id")
                or "__inbox__"
            )
            entity_id = fields.get("id") or operation.get("entityId") or operation.get("entity_id")
            if str(operation.get("op") or "create").lower() == "create" and entity_id:
                creates[package_id][entity_type].add(str(entity_id))
            for field_name, target_type in _PROPOSAL_REFERENCE_FIELDS.get(entity_type, ()):
                values = fields.get(field_name)
                values = values if isinstance(values, list) else [values]
                for target_id in values:
                    if target_id:
                        references.append({"source_type": entity_type, "source_id": str(entity_id or ""), "field": field_name, "target_type": target_type, "target_id": str(target_id), "package_id": package_id})
            if entity_type == "timeline_branch":
                for anchor_name in ("startAnchor", "endAnchor"):
                    anchor = fields.get(anchor_name)
                    target_id = anchor.get("eventId") if isinstance(anchor, dict) else None
                    if target_id:
                        references.append({"source_type": entity_type, "source_id": str(entity_id or ""), "field": f"{anchor_name}.eventId", "target_type": "event", "target_id": str(target_id), "package_id": package_id})
    def target_ids(ref: dict[str, str]) -> set[str]:
        aliases = {
            "event": {"event", "timeline_event"},
            "branch": {"branch", "timeline_branch"},
            "tag": {"tag", "character_tag"},
            "world_parent": {"world_container", "world_item"},
        }
        types = aliases.get(ref["target_type"], {ref["target_type"]})
        return set().union(*(canonical.get(entity_type, set()) | creates[ref["package_id"]].get(entity_type, set()) for entity_type in types))

    dangling = [ref for ref in references if ref["target_id"] not in target_ids(ref)]
    return {"reference_count": len(references), "dangling_reference_count": len(dangling), "reference_counts_by_target_type": dict(sorted(Counter(ref["target_type"] for ref in references).items())), "dangling_references": dangling[:50]}


def _reviewer_repair_metrics(import_dir: Path | None, inbox: Any) -> dict[str, Any]:
    repair_present = bool(import_dir and (import_dir / "reviewer_repair_proposals.json").exists())
    proposals = inbox if isinstance(inbox, list) else _safe_list(
        _safe_dict(inbox).get("items") or _safe_dict(inbox).get("proposals")
    )
    blocked_count = sum(
        1 for p in proposals if isinstance(p, dict) and p.get("status") == "blocked"
    )
    stale_block_marker_count = sum(
        1
        for p in proposals
        if isinstance(p, dict)
        and p.get("status") in (None, "pending")
        and bool(p.get("lastBlockReason"))
    )
    return {
        "reviewer_repair_artifacts_present": repair_present,
        "blocked_proposal_count": blocked_count,
        "stale_block_marker_count": stale_block_marker_count,
    }


def _review_findings(review_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for report in _safe_dict(review_report.get("reviewer_reports")).values():
        findings.extend(item for item in _safe_list(_safe_dict(report).get("findings")) if isinstance(item, dict))
    return findings


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
    markers = (
        character.get("role"),
        character.get("storyFunction"),
        character.get("story_function"),
        character.get("importance"),
        character.get("importanceTier"),
    )
    character_id = character.get("id") or character.get("entityId")
    return str(character_id) in recurring_character_ids or any(
        _normalize_text(str(marker)) in {_normalize_text(value) for value in _MAJOR_CHARACTER_MARKERS}
        for marker in markers if marker
    )


def _major_character_profile_gaps(characters: list[dict[str, Any]], timeline: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    canonical_events = _safe_list(timeline.get("canonical_events"))
    participation_counts: Counter[str] = Counter()
    for event in canonical_events:
        fields = _safe_dict(event)
        participant_ids = fields.get("participantCharacterIds") or fields.get("character_ids") or fields.get("characterIds")
        participation_counts.update(str(entity_id) for entity_id in _safe_list(participant_ids) if entity_id)
    recurring_character_ids = {
        character_id
        for character_id, count in participation_counts.items()
        if count >= max(2, (len(canonical_events) + 1) // 2)
    }
    supporting_note_keys = ("notes", "evidence_notes", "evidenceNotes", "source_notes", "sourceNotes")
    for character in characters:
        if not _is_major_character(character, recurring_character_ids) or not any(_has_content(character.get(key)) for key in supporting_note_keys):
            continue
        missing_fields = [field for field in ("background", "experience") if not _has_content(character.get(field))]
        if missing_fields:
            gaps.append({
                "id": character.get("id") or character.get("entityId"),
                "name": character.get("name") or character.get("canonical_name"),
                "missing_fields": missing_fields,
            })
    return gaps


def _world_organization_misplacements(
    operations: list[dict[str, Any]], characters_by_id: dict[str, dict[str, Any]], timeline: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    character_names = {
        _normalize_text(str(character.get("name") or character.get("canonical_name") or ""))
        for character in characters_by_id.values()
    }
    event_titles = {
        _normalize_text(str(_safe_dict(event).get("title") or _safe_dict(event).get("summary") or ""))
        for event in _safe_list(timeline.get("canonical_events"))
    }
    people: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for operation in operations:
        if _entity_type(operation) not in ("world_item", "world"):
            continue
        fields = _operation_fields(operation)
        category = str(fields.get("category") or fields.get("world_category") or "").casefold()
        container_id = str(fields.get("containerId") or fields.get("container_id") or "").casefold()
        if category not in _ORGANIZATION_CATEGORIES and "organization" not in container_id and "faction" not in container_id:
            continue
        name = str(fields.get("name") or "").strip()
        normalized_name = _normalize_text(name)
        item = {"id": fields.get("id") or operation.get("entityId"), "name": name}
        if normalized_name and (normalized_name in character_names or bool(_PERSON_TITLE_PATTERN.search(name))):
            people.append(item)
        if normalized_name and (normalized_name in event_titles or bool(_EVENT_ORGANIZATION_PATTERN.search(name))):
            events.append(item)
    return {"person_as_world_organization": people, "event_as_world_organization": events}


def _semantic_quality_metrics(
    operations: list[dict[str, Any]], review_report: dict[str, Any], source_language: str, timeline: dict[str, Any],
) -> dict[str, Any]:
    characters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    characters_by_id: dict[str, dict[str, Any]] = {}
    illegal_tags: list[str] = []
    invalid_relationships: list[dict[str, Any]] = []
    for operation in operations:
        fields = _operation_fields(operation)
        entity_type = _entity_type(operation)
        if entity_type == "character":
            fields = {**fields}
            entity_id = fields.get("id") or fields.get("entityId") or operation.get("entityId") or operation.get("entity_id")
            if entity_id:
                fields.setdefault("id", entity_id)
                characters_by_id[str(entity_id)] = fields
            name = str(fields.get("name") or fields.get("canonical_name") or "").strip()
            if name:
                characters[_normalize_text(name)].append(fields)
        elif entity_type == "character_tag" and source_language == "zh":
            name = str(fields.get("name") or "").strip()
            if name and _is_latin(name):
                illegal_tags.append(name)
        elif entity_type == "relationship":
            label = str(fields.get("type") or "").strip()
            ontology_type = str(fields.get("ontologyType") or fields.get("ontology_type") or fields.get("category") or "").strip().lower()
            invalid = bool(ontology_type and ontology_type not in _RELATIONSHIP_ONTOLOGY_TYPES)
            if source_language == "zh" and label and label not in _ZH_RELATIONSHIP_LABELS:
                invalid = True
            if invalid:
                invalid_relationships.append({"id": fields.get("id") or operation.get("entityId"), "type": label, "ontology_type": ontology_type})

    duplicate_names = []
    for records in characters.values():
        if len(records) > 1 and not all(_has_identity_disambiguation(record) for record in records):
            duplicate_names.append({
                "name": str(records[0].get("name") or records[0].get("canonical_name") or ""),
                "entity_ids": [record.get("id") or record.get("entityId") for record in records],
            })

    findings = _review_findings(review_report)
    finding_counts = Counter(str(finding.get("check_name") or "") for finding in findings)
    high_evidence_entity_mismatch_count = sum(
        1
        for finding in findings
        if finding.get("check_name") == "evidence_entity_mismatch" and str(finding.get("severity") or "").casefold() == "high"
    )
    reviewer_duplicate_names = []
    for finding in findings:
        if finding.get("check_name") != "character_duplicate_name":
            continue
        entity_refs = [str(entity_id) for entity_id in _safe_list(finding.get("entity_refs")) if entity_id]
        records = [characters_by_id[entity_id] for entity_id in entity_refs if entity_id in characters_by_id]
        if not records or not all(_has_identity_disambiguation(record) for record in records):
            reviewer_duplicate_names.append({
                "finding_id": finding.get("finding_id"),
                "entity_ids": entity_refs,
                "description": finding.get("description"),
            })
    organization_misplacements = _world_organization_misplacements(operations, characters_by_id, timeline)
    return {
        "duplicate_character_names": duplicate_names + reviewer_duplicate_names,
        "unresolved_evidence_missing_count": finding_counts["evidence_missing"],
        "high_evidence_entity_mismatch_count": high_evidence_entity_mismatch_count,
        "evidence_unusable_count": finding_counts["evidence_unusable"],
        "major_character_supported_profile_gaps": _major_character_profile_gaps(list(characters_by_id.values()), timeline),
        **organization_misplacements,
        "reviewer_branch_over_budget_count": finding_counts["branch_over_budget"],
        "illegal_or_english_tags": sorted(set(illegal_tags)),
        "invalid_relationships": invalid_relationships,
        "reviewer_finding_counts": dict(sorted(finding_counts.items())),
    }


def _usage_ledger_metrics(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict) or not ledger:
        return {"present": False, "exhausted": False, "over_cap": False}
    status = _safe_dict(ledger.get("budget_status"))
    remaining = _safe_dict(status.get("remaining"))
    return {
        "present": True,
        "exhausted": status.get("exhausted") is True,
        # Only compare against limits the artifact itself declares; diagnostics never invents a competing budget.
        "over_cap": any(isinstance(value, (int, float)) and value < 0 for value in remaining.values()),
        "remaining": remaining,
    }


def _proposal_receipt_metrics(receipts: Any) -> dict[str, Any]:
    counts = _safe_dict(_safe_dict(receipts).get("proposal_counts"))
    return {
        "present": isinstance(receipts, dict) and bool(receipts),
        "chapter_count": int(counts.get("chapter") or 0),
        "scene_count": int(counts.get("scene") or 0),
    }


def _symptom_flags(metrics: dict[str, Any], review_report: dict[str, Any], inbox_count: int, artifact_quality: dict[str, Any] | None = None) -> dict[str, bool]:
    report_total = sum(int(value) for value in _safe_dict(review_report.get("proposal_counts")).values() if isinstance(value, int))
    summary = _safe_dict(metrics["summary_lengths"])
    traits = _safe_dict(metrics["trait_quality"])
    timeline = _safe_dict(metrics["timeline"])
    branch_density = _safe_dict(timeline.get("branch_density"))
    mainline_density = _safe_dict(timeline.get("mainline_density"))
    flags: dict[str, bool] = {
        "review_report_inbox_count_mismatch": bool(report_total and report_total != inbox_count),
        "overlong_character_summaries": int(summary.get("outlier_count") or 0) > 0,
        "trait_duplication_or_noise": float(traits.get("trait_duplication_noise_score") or 0) > TRAIT_NOISE_WARN,
        "mixed_language_trait_sets": int(traits.get("characters_with_multilingual_trait_sets") or 0) > 0,
        "timeline_branch_over_budget": bool(branch_density.get("branches_over_budget")),
        "timeline_mainline_overdense": int(mainline_density.get("event_count") or 0) > MAINLINE_DENSITY_WARN,
        "duplicate_event_clusters_present": int(timeline.get("event_duplicate_cluster_count") or 0) > 0,
    }
    if artifact_quality is not None:
        ms = _safe_dict(artifact_quality.get("manuscript_projection"))
        ch = _safe_dict(artifact_quality.get("chapters"))
        tb = _safe_dict(artifact_quality.get("timeline_branches"))
        wq = _safe_dict(artifact_quality.get("world_quality"))
        semantic = _safe_dict(artifact_quality.get("semantic_quality"))
        usage = _safe_dict(artifact_quality.get("usage_ledger"))
        receipts = _safe_dict(artifact_quality.get("proposal_receipts"))
        reviewer_repair = _safe_dict(artifact_quality.get("reviewer_repair"))
        durable_failures = _safe_dict(artifact_quality.get("durable_failures"))
        chapter_node_count = int(ms.get("chapter_node_count") or 0)
        node_count = int(ms.get("node_count") or 0)
        scene_with_content = int(ms.get("scene_nodes_with_content") or 0)
        flags["smoke_chapter_count_not_10"] = int(ms.get("chapter_count") or 0) != 10
        flags["manuscript_projection_missing_or_empty"] = (
            chapter_node_count == 0 or node_count == 0 or scene_with_content < chapter_node_count
        )
        flags["smoke_manuscript_node_count_not_20"] = node_count != 20
        canonical = _safe_dict(ms.get("canonical"))
        flags["canonical_manuscript_written_before_acceptance"] = bool(ms.get("acceptance_required")) and (
            int(canonical.get("chapter_count") or 0) > 0 or int(canonical.get("chapter_node_count") or 0) > 0
        )
        flags["staged_projection_receipt_mismatch"] = bool(ms.get("acceptance_required")) and (
            not bool(receipts.get("present"))
            or int(receipts.get("chapter_count") or 0) != int(ms.get("chapter_count") or 0)
            or int(receipts.get("scene_count") or 0) != int(ms.get("scene_document_count") or 0)
        )
        flags["duplicate_chapter_numbers_present"] = int(ch.get("duplicate_chapter_number_count") or 0) > 0
        flags["empty_timeline_branches_present"] = int(tb.get("empty_branch_count") or 0) > 0
        flags["world_module_contamination_present"] = int(wq.get("contamination_count") or 0) > 0
        flags["world_cultivation_misclassification_present"] = int(wq.get("cultivation_misclassification_count") or 0) > 0
        flags["world_container_references_missing"] = int(wq.get("dangling_container_reference_count") or 0) > 0
        flags["dangling_proposal_references"] = int(_safe_dict(artifact_quality.get("proposal_reference_closure")).get("dangling_reference_count") or 0) > 0
        flags["pending_proposals_have_block_markers"] = int(reviewer_repair.get("stale_block_marker_count") or 0) > 0
        flags["duplicate_canonical_character_names"] = bool(semantic.get("duplicate_character_names"))
        flags["unresolved_evidence_missing"] = int(semantic.get("unresolved_evidence_missing_count") or 0) > 0
        flags["high_evidence_entity_mismatch"] = int(semantic.get("high_evidence_entity_mismatch_count") or 0) > 0
        flags["evidence_unusable"] = int(semantic.get("evidence_unusable_count") or 0) > 0
        flags["major_character_supported_profile_gaps"] = bool(semantic.get("major_character_supported_profile_gaps"))
        flags["person_as_world_organization"] = bool(semantic.get("person_as_world_organization"))
        flags["event_as_world_organization"] = bool(semantic.get("event_as_world_organization"))
        flags["illegal_or_english_tags_present"] = bool(semantic.get("illegal_or_english_tags"))
        flags["invalid_relationship_types_present"] = bool(semantic.get("invalid_relationships"))
        flags["branch_density_over_budget"] = int(semantic.get("reviewer_branch_over_budget_count") or 0) > 0
        flags["usage_ledger_missing"] = not bool(usage.get("present"))
        flags["usage_ledger_exhausted"] = bool(usage.get("exhausted"))
        flags["usage_ledger_over_cap"] = bool(usage.get("over_cap"))
        flags["durable_failure_artifacts_present"] = int(durable_failures.get("failure_count") or 0) > 0
        flags["review_pass_conflicts_durable_failures"] = bool(artifact_quality.get("review_pass_durable_failure_conflict"))
    return flags


def analyze_import(source: ImportSource) -> dict[str, Any]:
    project_path = source.project_path.expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise DiagnosticInputError(f"Project path does not exist or is not a directory: {project_path}")

    artifact_scope = _canonical_import_dir(source)
    import_run_id = artifact_scope.import_run_id
    import_dir = artifact_scope.artifact_dir
    inbox = _read_json(project_path / "system" / "inbox.json", required=True)
    operations = _proposal_operations(inbox)
    operation_counts = Counter(_entity_type(operation) for operation in operations)

    review_report = _read_json(import_dir / "review_report.json", default={}) if import_dir else {}
    timeline = _read_json(import_dir / "timeline_architecture.json", default={}) if import_dir else {}
    manifest = _read_json(import_dir / "manifest.json", default={}) if import_dir else {}
    staged_projection = _read_json(import_dir / "staged_manuscript_projection.json", default={}) if import_dir else {}
    proposal_receipts = _read_json(import_dir / "proposal_write_receipts.json", default={}) if import_dir else {}
    usage_ledger = _read_json(import_dir / "usage_ledger.json", default=None) if import_dir else None
    characters = _character_records(project_path, operations)
    source_language = str(manifest.get("source_language") or _safe_dict(_read_json(project_path / "project.json", default={})).get("metadata", {}).get("locale", "")).lower()
    source_language = "zh" if source_language.startswith("zh") else source_language

    total_chunks = len(_safe_list(manifest.get("segments")))
    checkpoint = _safe_dict(_read_json(import_dir / "checkpoint.json", default={})) if import_dir else {}
    if isinstance(checkpoint.get("total_chunks"), int):
        total_chunks = checkpoint["total_chunks"]
    durable_failures = _durable_failure_metrics(import_dir, total_chunks)
    review_status = review_report.get("status") if isinstance(review_report, dict) else None
    metrics: dict[str, Any] = {
        "project_path": str(project_path),
        "import_run_id": import_run_id,
        "artifact_scope": {
            "layout": artifact_scope.layout,
            "lineage_id": artifact_scope.lineage_id,
            "attempt_id": artifact_scope.attempt_id,
            "artifact_dir": str(import_dir) if import_dir else None,
        },
        "manifest": {
            "source_file_path": manifest.get("source_file_path"),
            "prompt_profile": manifest.get("prompt_profile"),
            "model": manifest.get("model"),
            "segment_count": manifest.get("segment_count"),
            "total_segment_chars": sum(
                int(segment.get("char_count") or 0)
                for segment in _safe_list(manifest.get("segments"))
                if isinstance(segment, dict)
            ),
        },
        "proposal_counts_by_entity_type": dict(sorted(operation_counts.items())),
        "review_report_proposal_counts": dict(sorted(_safe_dict(review_report.get("proposal_counts")).items())),
        "inbox_proposal_count": len(inbox) if isinstance(inbox, list) else len(_safe_list(_safe_dict(inbox).get("items"))),
        "character_count": {
            "character_records_analyzed": len(characters),
            "pending_character_proposals": operation_counts.get("character", 0),
            "review_report_character_proposals": _safe_dict(review_report.get("proposal_counts")).get("character", 0),
        },
        "group_distribution": _group_distribution(project_path, operations, characters),
        "summary_lengths": _summary_stats(characters),
        "trait_quality": _trait_metrics(characters),
        "timeline": _timeline_metrics(_safe_dict(timeline), operations),
        "review_status": {
            "status": review_status,
            "warning_count": len(_safe_list(review_report.get("warnings"))),
            "error_count": len(_safe_list(review_report.get("errors"))),
            "failed_chunk_count": len(_safe_list(review_report.get("failed_chunks"))),
            "blocked_id_count": len(_safe_list(review_report.get("blocked_ids"))),
            "low_confidence_item_count": len(_safe_list(review_report.get("low_confidence_items"))),
        },
    }
    artifact_quality: dict[str, Any] = {
        "manuscript_projection": _manuscript_projection_metrics(project_path, _safe_dict(staged_projection)),
        "chapters": _chapter_quality_metrics(project_path),
        "timeline_branches": _timeline_branch_quality(_safe_dict(timeline)),
        "world_quality": _world_quality_metrics(operations),
        "proposal_reference_closure": _proposal_reference_closure_metrics(project_path, inbox, _safe_dict(timeline)),
        "reviewer_repair": _reviewer_repair_metrics(import_dir, inbox),
        "semantic_quality": _semantic_quality_metrics(operations, _safe_dict(review_report), source_language, _safe_dict(timeline)),
        "usage_ledger": _usage_ledger_metrics(usage_ledger),
        "proposal_receipts": _proposal_receipt_metrics(proposal_receipts),
        "canonical_split_layout": _canonical_split_layout_metrics(project_path),
        "durable_failures": durable_failures,
    }
    artifact_quality["review_pass_durable_failure_conflict"] = (
        review_status == "pass" and durable_failures["failure_count"] > 0
    )
    metrics["artifact_quality"] = artifact_quality
    metrics["import_test6_symptom_flags"] = _symptom_flags(
        metrics, _safe_dict(review_report), metrics["inbox_proposal_count"], artifact_quality
    )
    metrics["informational_flags"] = {
        "scene_beats_or_discards_present": int(_safe_dict(metrics.get("timeline")).get("discard_count") or 0) > 0,
    }
    return metrics


def compare_metrics(primary: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    def at(metrics: dict[str, Any], path: list[str], default: Any = 0) -> Any:
        current: Any = metrics
        for key in path:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
        return current

    tracked = {
        "inbox_proposal_count": ["inbox_proposal_count"],
        "character_summary_outliers": ["summary_lengths", "outlier_count"],
        "trait_duplication_noise_score": ["trait_quality", "trait_duplication_noise_score"],
        "mixed_language_trait_count": ["trait_quality", "mixed_language_trait_count"],
        "canonical_event_count": ["timeline", "canonical_event_count"],
        "max_branch_density": ["timeline", "branch_density", "max_events_per_branch"],
        "mainline_event_count": ["timeline", "mainline_density", "event_count"],
        "discard_count": ["timeline", "discard_count"],
        "event_duplicate_cluster_count": ["timeline", "event_duplicate_cluster_count"],
    }
    deltas = {}
    for name, path in tracked.items():
        left = at(primary, path)
        right = at(comparison, path)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            deltas[name] = {"primary": left, "comparison": right, "delta": left - right}
    return deltas


def render_markdown(metrics: dict[str, Any]) -> str:
    flags = _safe_dict(metrics.get("import_test6_symptom_flags"))
    timeline = _safe_dict(metrics.get("timeline"))
    branch_density = _safe_dict(timeline.get("branch_density"))
    mainline_density = _safe_dict(timeline.get("mainline_density"))
    summary = _safe_dict(metrics.get("summary_lengths"))
    traits = _safe_dict(metrics.get("trait_quality"))
    lines = [
        f"## W1 Import Diagnostics: {metrics.get('import_run_id') or 'no import run'}",
        "",
        f"- Project: `{metrics.get('project_path')}`",
        f"- Inbox proposals: {metrics.get('inbox_proposal_count')}",
        f"- Proposal counts by entity type: `{json.dumps(metrics.get('proposal_counts_by_entity_type'), ensure_ascii=False)}`",
        f"- Review report counts: `{json.dumps(metrics.get('review_report_proposal_counts'), ensure_ascii=False)}`",
        f"- Character records analyzed: {_safe_dict(metrics.get('character_count')).get('character_records_analyzed')}",
        f"- Summary outliers: {summary.get('outlier_count')} (max length {summary.get('max')})",
        f"- Trait duplication/noise score: {traits.get('trait_duplication_noise_score')} with {traits.get('mixed_language_trait_count')} mixed-language trait items",
        f"- Timeline branches/events: {timeline.get('branch_count')} branches, {timeline.get('canonical_event_count')} canonical events",
        f"- Branch density: max {branch_density.get('max_events_per_branch')}, over budget `{json.dumps(branch_density.get('branches_over_budget'), ensure_ascii=False)}`",
        f"- Mainline density: {mainline_density.get('event_count')} events ({mainline_density.get('share')} share)",
        f"- Scene-beat/discard count: {timeline.get('discard_count')} `{json.dumps(timeline.get('scene_beat_discard_counts'), ensure_ascii=False)}`",
        f"- Duplicate event clusters: {timeline.get('event_duplicate_cluster_count')}",
        f"- Artifact scope: `{json.dumps(metrics.get('artifact_scope'), ensure_ascii=False)}`",
        f"- Durable failures: {int(_safe_dict(_safe_dict(metrics.get('artifact_quality')).get('durable_failures')).get('failure_count') or 0)}",
        f"- Import_Test6 symptom flags: `{json.dumps(flags, ensure_ascii=False, sort_keys=True)}`",
    ]
    return "\n".join(lines)


def _threshold_failed(metrics: dict[str, Any]) -> bool:
    return any(bool(value) for value in _safe_dict(metrics.get("import_test6_symptom_flags")).values())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quantify W1 import quality diagnostics for a Narrative IDE project.")
    parser.add_argument("project_path", nargs="?", help="Narrative IDE project directory to inspect.")
    parser.add_argument("--project-path", dest="project_path_flag", help="Alias for the positional project path.")
    parser.add_argument("--import-run-id", help="Specific system/imports/<import_run_id> to inspect. Defaults to newest import run.")
    parser.add_argument("--lineage-id", help="Specific durable lineage to inspect. Defaults to newest lineage/attempt when no run is provided.")
    parser.add_argument("--attempt-id", help="Specific attempt under --lineage-id (or --import-run-id when it identifies a lineage).")
    parser.add_argument("--compare-project", help="Optional second project directory to compare against.")
    parser.add_argument("--compare-import-run-id", help="Optional import run id for comparison. Uses the primary project if --compare-project is omitted.")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both", help="Output format. Default: both.")
    parser.add_argument("--fail-on-threshold", action="store_true", help="Exit 1 when any diagnostic symptom flag is true.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.project_path and args.project_path_flag and Path(args.project_path) != Path(args.project_path_flag):
            raise DiagnosticInputError("Positional project_path and --project-path must match when both are supplied")
        project_path = args.project_path_flag or args.project_path
        if not project_path:
            raise DiagnosticInputError("A project path is required (positional or --project-path)")
        primary = analyze_import(ImportSource(Path(project_path), args.import_run_id, args.lineage_id, args.attempt_id))
        payload: dict[str, Any] = {"diagnostics": primary, "summary_markdown": render_markdown(primary)}
        if args.compare_project or args.compare_import_run_id:
            compare_project = Path(args.compare_project) if args.compare_project else Path(project_path)
            comparison = analyze_import(ImportSource(compare_project, args.compare_import_run_id))
            payload["comparison"] = comparison
            payload["comparison_summary_markdown"] = render_markdown(comparison)
            payload["comparison_deltas"] = compare_metrics(primary, comparison)

        if args.format in {"json", "both"}:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if args.format in {"markdown", "both"}:
            if args.format == "both":
                print()
            print(payload["summary_markdown"])

        if args.fail_on_threshold and _threshold_failed(primary):
            return 1
        return 0
    except DiagnosticInputError as exc:
        print(f"w1_import_diagnostics: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
