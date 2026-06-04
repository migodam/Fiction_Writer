"""Deterministic quality checks for W1 import proposals and artifacts."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Literal

from sidecar.supervisor.reviewers.base import BaseReviewer
from sidecar.supervisor.reviewers.schemas import (
    OrchestratorRequest,
    RepairAction,
    ReviewFinding,
    ReviewReport,
)


_AGE_PHRASE_RE = re.compile(r"(\d{1,3}岁|[零一二三四五六七八九十百]+岁)")


def _ops(proposals: list, entity_type: str) -> list[dict]:
    type_set = (
        {"world", "world_entity", "organization", "faction", "location"}
        if entity_type == "world"
        else {entity_type}
    )
    return [
        op
        for p in proposals
        for op in (p.get("operations") or [])
        if op.get("entityType", "") in type_set
    ]


def _name(op: dict) -> str:
    fields = op.get("fields") or {}
    raw = fields.get("name") or fields.get("canonicalName") or fields.get("title") or op.get("entityId") or ""
    return str(raw).strip().lower()


class QualityReviewer(BaseReviewer):
    @property
    def reviewer_name(self) -> Literal["quality", "fact", "consistency"]:
        return "quality"

    def review(self, state: dict) -> ReviewReport:
        proposals = state.get("inbox_proposals", []) or state.get("proposals", []) or []
        event_ops = _ops(proposals, "timeline_event")
        char_ops = _ops(proposals, "character")
        world_ops = _ops(proposals, "world")
        rel_ops = _ops(proposals, "relationship")

        findings: List[ReviewFinding] = []
        repairs: List[RepairAction] = []
        orch_reqs: List[OrchestratorRequest] = []

        self._check_timeline_stream(event_ops, findings, repairs)
        self._check_mainline_share(event_ops, findings)
        self._check_branch_over_budget(event_ops, findings)
        self._check_world_empty_container(world_ops, findings)
        self._check_world_wrong_classification(world_ops, findings, repairs)
        self._check_world_module_pollution(char_ops, world_ops, findings)
        self._check_character_duplicate_name(char_ops, findings, repairs)
        self._check_character_repeated_phrases(char_ops, findings, repairs)
        self._check_character_age_phrase_repeated(char_ops, findings, repairs)
        self._check_character_missing_major(state, findings, orch_reqs)
        self._check_character_thin_card(char_ops, findings)
        self._check_relationship_no_evidence(rel_ops, findings)
        self._check_manuscript_empty(state, findings)
        self._check_duplicate_manuscript_chapters(state, findings, repairs)

        return self._build_report(findings, repairs, orch_reqs)

    def _check_timeline_stream(
        self, event_ops: list, findings: list, repairs: list
    ) -> None:
        if not event_ops:
            return
        scene_beats = [
            op for op in event_ops
            if (op.get("fields") or {}).get("timelineClass") == "scene_beat"
        ]
        if len(scene_beats) / len(event_ops) > 0.5:
            findings.append(self._finding(
                "timeline_stream_of_consciousness",
                f"{len(scene_beats)}/{len(event_ops)} event proposals are scene_beats — timeline is stream-of-consciousness",
                "high",
                entity_refs=[op.get("entityId", "?") for op in scene_beats],
                entity_id="batch",
            ))
            repairs.append(self._repair(
                "reclassify",
                [op.get("entityId", "?") for op in scene_beats],
                "Reclassify scene_beat proposals; route through manuscript instead of canonical timeline",
            ))

    def _check_mainline_share(self, event_ops: list, findings: list) -> None:
        canonical = [
            op for op in event_ops
            if (op.get("fields") or {}).get("timelineClass") == "canonical_event"
        ]
        if not canonical:
            return
        mainline = [
            op for op in canonical
            if (op.get("fields") or {}).get("branchId") == "main"
        ]
        if len(mainline) / len(canonical) > 0.8:
            findings.append(self._finding(
                "mainline_share_too_high",
                f"{len(mainline)}/{len(canonical)} canonical events on main branch — no branching structure",
                "medium",
                entity_id="batch",
            ))

    def _check_branch_over_budget(self, event_ops: list, findings: list) -> None:
        branch_counts: dict[str, list] = defaultdict(list)
        for op in event_ops:
            fields = op.get("fields") or {}
            if fields.get("timelineClass") != "canonical_event":
                continue
            branch = fields.get("branchId", "")
            if branch and branch != "main":
                branch_counts[branch].append(op.get("entityId", "?"))
        for branch, ids in branch_counts.items():
            if len(ids) > 10:
                findings.append(self._finding(
                    "branch_over_budget",
                    f"Branch '{branch}' has {len(ids)} canonical events (>10 limit)",
                    "medium",
                    entity_refs=ids,
                    entity_id=branch,
                ))

    def _check_world_empty_container(self, world_ops: list, findings: list) -> None:
        for op in world_ops:
            fields = op.get("fields") or {}
            if not fields.get("description", "").strip():
                entity_id = op.get("entityId", "?")
                findings.append(self._finding(
                    "world_empty_container",
                    f"World entity '{fields.get('name', entity_id)}' has no description",
                    "medium",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))

    def _check_world_wrong_classification(
        self, world_ops: list, findings: list, repairs: list
    ) -> None:
        for op in world_ops:
            fields = op.get("fields") or {}
            if fields.get("category", "").lower() == "character":
                entity_id = op.get("entityId", "?")
                findings.append(self._finding(
                    "world_wrong_classification",
                    f"World entity '{fields.get('name', entity_id)}' classified as 'character'",
                    "high",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))
                repairs.append(self._repair(
                    "reclassify",
                    [entity_id],
                    f"Reclassify world entity '{fields.get('name', entity_id)}' from category=character to correct world category",
                ))

    def _check_world_module_pollution(
        self, char_ops: list, world_ops: list, findings: list
    ) -> None:
        char_names = {_name(op) for op in char_ops if _name(op)}
        world_names = {_name(op) for op in world_ops if _name(op)}
        collisions = sorted(char_names & world_names)
        if collisions:
            findings.append(self._finding(
                "world_module_pollution",
                f"{len(collisions)} name(s) appear as both character and world entity: {', '.join(collisions[:5])}",
                "medium",
                entity_id="batch",
            ))

    def _check_character_duplicate_name(
        self, char_ops: list, findings: list, repairs: list
    ) -> None:
        groups: dict[str, list[str]] = defaultdict(list)
        for op in char_ops:
            n = _name(op)
            if n:
                groups[n].append(op.get("entityId", "?"))
        for name, ids in groups.items():
            if len(ids) > 1:
                primary_id = ids[0]
                dup_ids = ids[1:]
                findings.append(self._finding(
                    "character_duplicate_name",
                    f"{len(ids)} character proposals share name '{name}'",
                    "high",
                    entity_refs=ids,
                    entity_id=name,
                ))
                repairs.append(self._repair(
                    "merge_duplicate",
                    ids,
                    f"Delete {len(dup_ids)} duplicate character proposal(s) for '{name}'; keep primary '{primary_id}'",
                    deterministic=False,  # delete may be blocked if dup is referenced by relationships
                    proposed_operations=[
                        {"op": "delete", "entityType": "character", "entityId": dup_id}
                        for dup_id in dup_ids
                    ],
                ))

    def _check_character_repeated_phrases(
        self, char_ops: list, findings: list, repairs: list
    ) -> None:
        for op in char_ops:
            fields = op.get("fields") or {}
            entity_id = op.get("entityId", "?")
            char_name = fields.get("name", entity_id)
            cleaned_fields: dict = {}
            for field in ("summary", "background"):
                text = fields.get(field, "") or ""
                if len(text) < 10:
                    continue
                # Detect any 5–15 char phrase that appears more than once.
                m = re.search(r"(.{5,15}).*\1", text, re.DOTALL)
                if not m:
                    continue
                phrase = m.group(1)
                # Keep first occurrence; remove all subsequent occurrences.
                first_end = text.index(phrase) + len(phrase)
                cleaned = (text[:first_end] + text[first_end:].replace(phrase, "")).strip()
                if cleaned != text:
                    cleaned_fields[field] = cleaned
            if cleaned_fields:
                findings.append(self._finding(
                    "character_repeated_phrase",
                    f"Character '{char_name}' has repeated phrase(s) in {', '.join(cleaned_fields)}",
                    "medium",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))
                repairs.append(self._repair(
                    "clean_repeated_phrase",
                    [entity_id],
                    f"Remove duplicate phrase(s) from character '{char_name}' fields: {', '.join(cleaned_fields)}",
                    deterministic=True,
                    proposed_operations=[
                        {"op": "update", "entityType": "character", "entityId": entity_id, "fields": cleaned_fields}
                    ],
                ))

    def _check_character_age_phrase_repeated(
        self, char_ops: list, findings: list, repairs: list
    ) -> None:
        """Detect short age phrases (e.g. '23岁', '十岁') that appear more than once in a field."""
        for op in char_ops:
            fields = op.get("fields") or {}
            entity_id = op.get("entityId", "?")
            char_name = fields.get("name", entity_id)
            cleaned_fields: dict = {}
            for field_name in ("summary", "background"):
                text = fields.get(field_name, "") or ""
                if not text:
                    continue
                age_phrases = _AGE_PHRASE_RE.findall(text)
                seen: dict[str, int] = {}
                for phrase in age_phrases:
                    seen[phrase] = seen.get(phrase, 0) + 1
                repeated = {phrase for phrase, count in seen.items() if count > 1}
                if not repeated:
                    continue
                cleaned = text
                for phrase in sorted(repeated):
                    first_end = cleaned.index(phrase) + len(phrase)
                    cleaned = cleaned[:first_end] + cleaned[first_end:].replace(phrase, "")
                cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
                if cleaned != text:
                    cleaned_fields[field_name] = cleaned
            if cleaned_fields:
                findings.append(self._finding(
                    "character_repeated_age_phrase",
                    f"Character '{char_name}' has repeated age phrase(s) in {', '.join(cleaned_fields)}",
                    "medium",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))
                repairs.append(self._repair(
                    "clean_age_phrase_duplicate",
                    [entity_id],
                    f"Remove duplicate age phrase(s) from '{char_name}'. "
                    "ADVISORY: repair appears in report only; apply via proposal acceptance.",
                    deterministic=True,
                    proposed_operations=[
                        {"op": "update", "entityType": "character", "entityId": entity_id, "fields": cleaned_fields}
                    ],
                ))

    def _check_character_missing_major(
        self, state: dict, findings: list, orch_reqs: list
    ) -> None:
        converge = state.get("converge_target") or {}
        protagonist_list: list[str] = converge.get("protagonist_list") or []
        if not protagonist_list:
            return
        registry = state.get("entity_registry") or {}
        chars = registry.get("characters") or {}
        present_names = {
            v.get("name", "").lower()
            for v in chars.values()
            if isinstance(v, dict)
        }
        for name in protagonist_list:
            if name.lower() not in present_names:
                findings.append(self._finding(
                    "character_missing_major",
                    f"Protagonist '{name}' not found in entity_registry",
                    "high",
                    entity_id=name,
                ))
                orch_reqs.append(self._orch_req(
                    "rerun_window",
                    "character_undercoverage",
                    [],
                    f"Extract missing protagonist: {name}",
                    priority="high",
                ))

    def _check_character_thin_card(self, char_ops: list, findings: list) -> None:
        for op in char_ops:
            fields = op.get("fields") or {}
            summary = fields.get("summary", "") or ""
            if len(summary) < 20:
                entity_id = op.get("entityId", "?")
                findings.append(self._finding(
                    "character_thin_card",
                    f"Character '{fields.get('name', entity_id)}' has a thin summary (<20 chars)",
                    "low",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))

    def _check_relationship_no_evidence(self, rel_ops: list, findings: list) -> None:
        for op in rel_ops:
            fields = op.get("fields") or {}
            if not fields.get("evidence", ""):
                entity_id = op.get("entityId", "?")
                findings.append(self._finding(
                    "relationship_no_evidence",
                    f"Relationship '{entity_id}' has no evidence field",
                    "medium",
                    entity_refs=[entity_id],
                    entity_id=entity_id,
                ))

    def _check_manuscript_empty(self, state: dict, findings: list) -> None:
        chapters = state.get("manuscript_chapters")
        if chapters is None or chapters == []:
            findings.append(self._finding(
                "manuscript_empty",
                "manuscript_chapters is absent or empty",
                "medium",
                entity_id="manuscript",
            ))

    def _check_duplicate_manuscript_chapters(
        self, state: dict, findings: list, repairs: list
    ) -> None:
        """Detect duplicate chapters by title (primary) or chapter number (fallback)."""
        chapters = state.get("manuscript_chapters") or []
        if not chapters or not isinstance(chapters, list):
            return
        by_title: dict[str, list[str]] = defaultdict(list)
        by_number: dict[int, list[str]] = defaultdict(list)
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            title = str(ch.get("title") or "").strip()
            ch_id = str(ch.get("chapter_id") or title or "?")
            if title:
                by_title[title.lower()].append(ch_id)
            num = ch.get("chapterNumber")
            if isinstance(num, int):
                by_number[num].append(ch_id)
        reported_ids: set[str] = set()
        for title, ids in by_title.items():
            if len(ids) > 1:
                reported_ids.update(ids)
                findings.append(self._finding(
                    "duplicate_manuscript_chapter",
                    f"Chapter '{title}' appears {len(ids)} times",
                    "high",
                    entity_refs=ids,
                    entity_id=f"dup_title_{title[:20]}",
                ))
                repairs.append(self._repair(
                    "dedupe_chapters",
                    ids,
                    f"Keep first '{title}'; delete {len(ids)-1} duplicate(s). "
                    "ADVISORY: apply via proposal acceptance only.",
                    deterministic=True,
                    proposed_operations=[
                        {"op": "delete", "entityType": "manuscript_chapter", "entityId": dup_id}
                        for dup_id in ids[1:]
                    ],
                ))
        for num, ids in by_number.items():
            uncovered = [i for i in ids if i not in reported_ids]
            if len(uncovered) > 1:
                findings.append(self._finding(
                    "duplicate_manuscript_chapter_number",
                    f"Chapter number {num} assigned to {len(uncovered)} chapters (no title overlap)",
                    "high",
                    entity_refs=uncovered,
                    entity_id=f"dup_num_{num}",
                ))
