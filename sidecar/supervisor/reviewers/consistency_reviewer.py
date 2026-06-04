"""Cross-import continuity checks for W1 import proposals against existing project state."""
from __future__ import annotations

from typing import List, Literal

from sidecar.supervisor.reviewers.base import BaseReviewer
import uuid

from sidecar.supervisor.reviewers.schemas import (
    ManifestRevisionDiff,
    OrchestratorRequest,
    RepairAction,
    ReviewFinding,
    ReviewReport,
)


def _normalize(name: str) -> str:
    return str(name).strip().lower()


class ConsistencyReviewer(BaseReviewer):
    @property
    def reviewer_name(self) -> Literal["quality", "fact", "consistency"]:
        return "consistency"

    def review(self, state: dict) -> ReviewReport:
        digest = state.get("project_structure_digest") or {}
        if not digest:
            return self._build_report([], [], [])

        registry = state.get("entity_registry") or {}
        findings: List[ReviewFinding] = []
        repairs: List[RepairAction] = []
        orch_reqs: List[OrchestratorRequest] = []

        self._check_character_duplicates(digest, registry, findings, repairs)
        self._check_branch_continuity(digest, registry, findings)
        self._check_world_item_conflict(digest, registry, findings, repairs)
        self._check_relationship_redundant(digest, registry, findings, repairs)

        diffs = self._produce_manifest_revision_diffs(digest, registry)
        return self._build_report(findings, repairs, orch_reqs, manifest_revision_diffs=diffs)

    def _check_character_duplicates(
        self, digest: dict, registry: dict, findings: list, repairs: list
    ) -> None:
        existing_chars = digest.get("characters") or {}
        existing_names = {
            _normalize(v.get("name", k))
            for k, v in existing_chars.items()
            if isinstance(v, dict)
        }
        if not existing_names:
            existing_names = {_normalize(str(k)) for k in existing_chars}

        new_chars = (registry.get("characters") or {})
        for char_id, char_data in new_chars.items():
            name = ""
            if isinstance(char_data, dict):
                name = char_data.get("name", "") or ""
            if not name:
                name = str(char_id)
            if _normalize(name) in existing_names:
                findings.append(self._finding(
                    "character_duplicate_across_imports",
                    f"Character '{name}' already exists in project — possible duplicate import",
                    "high",
                    entity_refs=[char_id],
                    entity_id=char_id,
                ))
                repairs.append(self._repair(
                    "merge_duplicate",
                    [char_id],
                    f"Merge new character '{name}' with existing project character",
                ))

    def _check_branch_continuity(
        self, digest: dict, registry: dict, findings: list
    ) -> None:
        existing_branches: set[str] = set(digest.get("timeline_branches") or [])
        if not existing_branches:
            return

        new_events = registry.get("events") or {}
        new_branch_ids: set[str] = set()
        for ev in new_events.values():
            if isinstance(ev, dict):
                bid = ev.get("branchId") or ev.get("branch_id") or ""
                if bid:
                    new_branch_ids.add(str(bid))

        if not new_branch_ids:
            return

        orphan_branches = new_branch_ids - existing_branches
        if orphan_branches == new_branch_ids:
            findings.append(self._finding(
                "timeline_branch_continuity",
                f"New import branches {sorted(orphan_branches)} have no overlap with existing branches {sorted(existing_branches)}",
                "medium",
                entity_id="branch_batch",
            ))

    def _check_world_item_conflict(
        self, digest: dict, registry: dict, findings: list, repairs: list
    ) -> None:
        existing_world = digest.get("world_items") or {}
        existing_by_name: dict[str, str] = {}
        for item_id, item in existing_world.items():
            if isinstance(item, dict):
                name = _normalize(item.get("name") or str(item_id))
                cat = str(item.get("category") or "").lower()
                existing_by_name[name] = cat

        new_world = registry.get("world_detailed") or registry.get("world") or {}
        for item_id, item in new_world.items():
            if isinstance(item, dict):
                name = _normalize(item.get("name") or str(item_id))
                new_cat = str(item.get("category") or "").lower()
            else:
                name = _normalize(str(item_id))
                new_cat = ""

            if name in existing_by_name and existing_by_name[name] != new_cat:
                findings.append(self._finding(
                    "world_item_conflict",
                    f"World item '{name}' exists as '{existing_by_name[name]}' but new import classifies it as '{new_cat}'",
                    "high",
                    entity_refs=[str(item_id)],
                    entity_id=str(item_id),
                ))
                repairs.append(self._repair(
                    "reclassify",
                    [str(item_id)],
                    f"Align category of '{name}' with existing project value '{existing_by_name[name]}'",
                ))

    def _check_relationship_redundant(
        self, digest: dict, registry: dict, findings: list, repairs: list
    ) -> None:
        existing_rels = digest.get("relationships") or {}
        existing_pairs: set[tuple[str, str]] = set()
        for rel in existing_rels.values() if isinstance(existing_rels, dict) else existing_rels:
            if isinstance(rel, dict):
                src = str(rel.get("sourceId") or rel.get("source") or "")
                tgt = str(rel.get("targetId") or rel.get("target") or "")
                if src and tgt:
                    existing_pairs.add((src, tgt))

        new_rels = registry.get("relationships") or {}
        items = new_rels.values() if isinstance(new_rels, dict) else new_rels
        for rel in items:
            if not isinstance(rel, dict):
                continue
            src = str(rel.get("sourceId") or rel.get("source") or "")
            tgt = str(rel.get("targetId") or rel.get("target") or "")
            rel_id = rel.get("id") or f"{src}-{tgt}"
            if src and tgt and (src, tgt) in existing_pairs:
                findings.append(self._finding(
                    "relationship_redundant",
                    f"Relationship {src}→{tgt} already exists in project",
                    "high",
                    entity_refs=[str(rel_id)],
                    entity_id=str(rel_id),
                ))
                repairs.append(self._repair(
                    "merge_duplicate",
                    [str(rel_id)],
                    f"Skip or merge duplicate relationship {src}→{tgt}",
                ))

    def _produce_manifest_revision_diffs(
        self, digest: dict, registry: dict
    ) -> list[ManifestRevisionDiff]:
        """Emit protect-diffs when a key character field changes vs. existing project.

        Advisory output only — does not mutate state or proposals.
        """
        existing_chars = digest.get("characters") or {}
        new_chars = registry.get("characters") or {}
        diffs: list[ManifestRevisionDiff] = []
        for char_id, char_data in new_chars.items():
            if not isinstance(char_data, dict):
                continue
            new_name = _normalize(str(char_data.get("name") or char_id))
            existing_entry = next(
                (v for v in existing_chars.values()
                 if isinstance(v, dict) and _normalize(v.get("name", "")) == new_name),
                None,
            )
            if not existing_entry:
                continue
            for field in ("summary", "background", "role"):
                old_val = str(existing_entry.get(field) or "").strip()
                new_val = str(char_data.get(field) or "").strip()
                if not old_val or not new_val or old_val == new_val:
                    continue
                diffs.append(ManifestRevisionDiff(
                    revision_id=f"mrd_{uuid.uuid4().hex[:8]}",
                    entity_type="character",
                    entity_id=char_id,
                    field=field,
                    old_value=old_val[:200],
                    new_value=new_val[:200],
                    action="protect",
                    reason=f"Existing project '{field}' differs from new import; protecting earlier fact.",
                ))
        return diffs
