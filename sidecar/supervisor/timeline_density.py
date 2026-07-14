"""Deterministic post-architect timeline density enforcement for supervisor W1."""
from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

MAX_EVENTS_PER_BRANCH = 10
_CAUSAL_RANK = {"climax": 5, "turning_point": 4, "irreversible_change": 4, "revelation": 3, "decision": 3, "setup": 2, "aftermath": 1}


def _stable_id(event: dict[str, Any], fallback: int) -> str:
    return str(event.get("id") or event.get("eventId") or event.get("event_id") or event.get("title") or f"event_{fallback:04d}")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _chapter_key(event: dict[str, Any]) -> str:
    chapter_range = event.get("chapterRange") or event.get("chapter_range") or {}
    value = chapter_range.get("start") if isinstance(chapter_range, dict) else chapter_range
    value = value or event.get("chapterNumber") or event.get("chapter_number") or event.get("sourceChunkId")
    return str(value) if value not in (None, "") else "unanchored"


def _rank_key(event: dict[str, Any], fallback: int) -> tuple[float, float, int, float, str]:
    causal = str(event.get("causalRole") or event.get("causal_role") or "").lower()
    return (-_number(event.get("importanceScore", event.get("importance", 0))), -_number(event.get("confidence", 0)), -_CAUSAL_RANK.get(causal, 0), _number(event.get("sourceOrder", event.get("orderIndex", fallback)), float(fallback)), _stable_id(event, fallback))


def _unique(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value not in (None, "") and value not in unique:
            unique.append(value)
    return unique


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _chapter_key(left) != _chapter_key(right):
        return False
    if left.get("dedupeKey") and left.get("dedupeKey") == right.get("dedupeKey"):
        return True
    def tokens(event: dict[str, Any]) -> set[str]:
        return {
            token for token in re.findall(r"[\w\u4e00-\u9fff]+", str(event.get("title") or event.get("name") or "").lower())
            if token not in {"chapter", "chap", "第", "章"} and not token.isdigit()
        }
    return bool(tokens(left) & tokens(right))


def _merge_provenance(primary: dict[str, Any], overflow: dict[str, Any], fallback: int) -> None:
    primary["mergedEventIds"] = _unique([*list(primary.get("mergedEventIds") or []), _stable_id(overflow, fallback), *list(overflow.get("mergedEventIds") or [])])
    primary["contributingSourceSpans"] = _unique([*list(primary.get("contributingSourceSpans") or []), primary.get("sourceSpan") or primary.get("source_span"), overflow.get("sourceSpan") or overflow.get("source_span")])
    primary["contributingChapterRanges"] = _unique([*list(primary.get("contributingChapterRanges") or []), primary.get("chapterRange") or primary.get("chapter_range"), overflow.get("chapterRange") or overflow.get("chapter_range")])
    primary["densityReasons"] = _unique([*list(primary.get("densityReasons") or []), f"merged semantically overlapping overflow event {_stable_id(overflow, fallback)}"])


def enforce_timeline_density(state: dict[str, Any], max_events_per_branch: int = MAX_EVENTS_PER_BRANCH) -> dict[str, Any]:
    """Cap canonical events per branch while retaining chapter coverage and provenance."""
    architecture = deepcopy(state.get("timeline_architecture") or {})
    canonical = [dict(event) for event in architecture.get("canonical_events", []) if isinstance(event, dict)]
    if not canonical:
        return state
    by_branch: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, event in enumerate(canonical):
        by_branch[str(event.get("branchId") or event.get("branch_id") or "main")].append((index, event))
    retained, changes = [], []
    scene_beats = [dict(event) for event in architecture.get("scene_beats", []) if isinstance(event, dict)]
    for branch_id, entries in by_branch.items():
        if len(entries) <= max_events_per_branch:
            retained.extend(event for _, event in entries)
            continue
        by_chapter: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for entry in entries:
            by_chapter[_chapter_key(entry[1])].append(entry)
        selected = [min(group, key=lambda item: _rank_key(item[1], item[0])) for _, group in sorted(by_chapter.items())]
        if len(selected) > max_events_per_branch:
            selected = sorted(selected, key=lambda item: _rank_key(item[1], item[0]))[:max_events_per_branch]
        selected_ids = {id(event) for _, event in selected}
        for entry in sorted(entries, key=lambda item: _rank_key(item[1], item[0])):
            if len(selected) >= max_events_per_branch:
                break
            if id(entry[1]) not in selected_ids:
                selected.append(entry)
                selected_ids.add(id(entry[1]))
        selected.sort(key=lambda item: (_number(item[1].get("sourceOrder", item[1].get("orderIndex", item[0])), item[0]), _stable_id(item[1], item[0])))
        selected_events = [event for _, event in selected]
        for order_index, event in enumerate(selected_events):
            event.update({"branchId": branch_id, "orderIndex": order_index})
            event["densityReasons"] = _unique([*list(event.get("densityReasons") or []), "retained by post-architect branch density policy"])
        retained.extend(selected_events)
        for fallback, overflow in entries:
            if id(overflow) in {id(event) for event in selected_events}:
                continue
            primary = next((event for event in selected_events if _overlaps(event, overflow)), None)
            if primary:
                _merge_provenance(primary, overflow, fallback)
                changes.append({"eventId": _stable_id(overflow, fallback), "action": "merged", "intoEventId": _stable_id(primary, fallback), "reason": "semantic_overlap_overflow"})
            else:
                demoted = {**overflow, "timelineClass": "scene_beat", "eventClass": "scene_beat"}
                demoted["densityReasons"] = _unique([*list(demoted.get("densityReasons") or []), "demoted by post-architect branch density policy"])
                demoted["contributingSourceSpans"] = _unique([*list(demoted.get("contributingSourceSpans") or []), demoted.get("sourceSpan") or demoted.get("source_span")])
                demoted["contributingChapterRanges"] = _unique([*list(demoted.get("contributingChapterRanges") or []), demoted.get("chapterRange") or demoted.get("chapter_range")])
                scene_beats.append(demoted)
                changes.append({"eventId": _stable_id(overflow, fallback), "action": "demoted", "reason": "branch_budget_overflow"})
    retained.sort(key=lambda event: (str(event.get("branchId") or "main"), _number(event.get("orderIndex")), _stable_id(event, 0)))
    architecture["canonical_events"], architecture["scene_beats"], architecture["density_adjustments"] = retained, scene_beats, changes
    density_policy = dict(architecture.get("density_policy") or {})
    density_policy.update({"max_events_per_branch": max_events_per_branch, "post_architect_enforced": True})
    architecture["density_policy"] = density_policy
    registry = deepcopy(state.get("entity_registry") or {})
    registry_events = dict(registry.get("events") or {})
    canonical_by_id = {_stable_id(event, index): event for index, event in enumerate(retained)}
    demoted_ids = {change["eventId"] for change in changes if change["action"] == "demoted"}
    for event_id, event in registry_events.items():
        if not isinstance(event, dict):
            continue
        normalized = canonical_by_id.get(str(event_id)) or canonical_by_id.get(_stable_id(event, 0))
        if normalized:
            registry_events[event_id] = {**event, **normalized, "timelineClass": "canonical_event", "eventClass": "canonical_event"}
        elif str(event_id) in demoted_ids or _stable_id(event, 0) in demoted_ids:
            registry_events[event_id] = {**event, "timelineClass": "scene_beat", "eventClass": "scene_beat"}
    registry["events"] = registry_events
    return {**state, "timeline_architecture": architecture, "entity_registry": registry}
