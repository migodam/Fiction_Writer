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


class DiagnosticInputError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSource:
    project_path: Path
    import_run_id: str | None = None


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


def _canonical_import_dir(project_path: Path, import_run_id: str | None) -> tuple[str | None, Path | None]:
    imports_dir = project_path / "system" / "imports"
    if import_run_id:
        run_dir = imports_dir / import_run_id
        if not run_dir.exists():
            raise DiagnosticInputError(f"Import run does not exist: {run_dir}")
        return import_run_id, run_dir

    if not imports_dir.exists():
        return None, None

    candidates = [path for path in imports_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None, None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0].name, candidates[0]


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


def _symptom_flags(metrics: dict[str, Any], review_report: dict[str, Any], inbox_count: int) -> dict[str, bool]:
    report_total = sum(int(value) for value in _safe_dict(review_report.get("proposal_counts")).values() if isinstance(value, int))
    summary = _safe_dict(metrics["summary_lengths"])
    traits = _safe_dict(metrics["trait_quality"])
    timeline = _safe_dict(metrics["timeline"])
    branch_density = _safe_dict(timeline.get("branch_density"))
    mainline_density = _safe_dict(timeline.get("mainline_density"))
    scene_beat_counts = _safe_dict(timeline.get("scene_beat_discard_counts"))
    return {
        "review_report_inbox_count_mismatch": bool(report_total and report_total != inbox_count),
        "overlong_character_summaries": int(summary.get("outlier_count") or 0) > 0,
        "trait_duplication_or_noise": float(traits.get("trait_duplication_noise_score") or 0) > TRAIT_NOISE_WARN,
        "mixed_language_trait_sets": int(traits.get("characters_with_multilingual_trait_sets") or 0) > 0,
        "timeline_branch_over_budget": bool(branch_density.get("branches_over_budget")),
        "timeline_mainline_overdense": int(mainline_density.get("event_count") or 0) > MAINLINE_DENSITY_WARN,
        "scene_beats_or_discards_present": int(timeline.get("discard_count") or 0) > 0 or bool(scene_beat_counts),
        "duplicate_event_clusters_present": int(timeline.get("event_duplicate_cluster_count") or 0) > 0,
    }


def analyze_import(source: ImportSource) -> dict[str, Any]:
    project_path = source.project_path.expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise DiagnosticInputError(f"Project path does not exist or is not a directory: {project_path}")

    import_run_id, import_dir = _canonical_import_dir(project_path, source.import_run_id)
    inbox = _read_json(project_path / "system" / "inbox.json", required=True)
    operations = _proposal_operations(inbox)
    operation_counts = Counter(_entity_type(operation) for operation in operations)

    review_report = _read_json(import_dir / "review_report.json", default={}) if import_dir else {}
    timeline = _read_json(import_dir / "timeline_architecture.json", default={}) if import_dir else {}
    manifest = _read_json(import_dir / "manifest.json", default={}) if import_dir else {}
    characters = _character_records(project_path, operations)

    metrics: dict[str, Any] = {
        "project_path": str(project_path),
        "import_run_id": import_run_id,
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
            "status": review_report.get("status"),
            "warning_count": len(_safe_list(review_report.get("warnings"))),
            "error_count": len(_safe_list(review_report.get("errors"))),
            "failed_chunk_count": len(_safe_list(review_report.get("failed_chunks"))),
            "blocked_id_count": len(_safe_list(review_report.get("blocked_ids"))),
            "low_confidence_item_count": len(_safe_list(review_report.get("low_confidence_items"))),
        },
    }
    metrics["import_test6_symptom_flags"] = _symptom_flags(metrics, _safe_dict(review_report), metrics["inbox_proposal_count"])
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
        f"- Import_Test6 symptom flags: `{json.dumps(flags, ensure_ascii=False, sort_keys=True)}`",
    ]
    return "\n".join(lines)


def _threshold_failed(metrics: dict[str, Any]) -> bool:
    return any(bool(value) for value in _safe_dict(metrics.get("import_test6_symptom_flags")).values())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quantify W1 import quality diagnostics for a Narrative IDE project.")
    parser.add_argument("project_path", help="Narrative IDE project directory to inspect.")
    parser.add_argument("--import-run-id", help="Specific system/imports/<import_run_id> to inspect. Defaults to newest import run.")
    parser.add_argument("--compare-project", help="Optional second project directory to compare against.")
    parser.add_argument("--compare-import-run-id", help="Optional import run id for comparison. Uses the primary project if --compare-project is omitted.")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both", help="Output format. Default: both.")
    parser.add_argument("--fail-on-threshold", action="store_true", help="Exit 1 when any diagnostic symptom flag is true.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        primary = analyze_import(ImportSource(Path(args.project_path), args.import_run_id))
        payload: dict[str, Any] = {"diagnostics": primary, "summary_markdown": render_markdown(primary)}
        if args.compare_project or args.compare_import_run_id:
            compare_project = Path(args.compare_project) if args.compare_project else Path(args.project_path)
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
