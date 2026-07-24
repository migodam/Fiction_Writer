#!/usr/bin/env python3
"""Safely re-review one pending W1 proposal package without provider calls.

This tool exists for W1 packages created before the deterministic organizer and
semantic reviewer were added.  It only changes staging artifacts: the pending
inbox and its compiled proposal graph.  Canonical project files are never read
as write targets, never accepted, and never changed.

Usage::

    python tools/w1_rereview_pending_package_semantics.py /path/to/project
    python tools/w1_rereview_pending_package_semantics.py /path/to/project \\
      --import-run-id lineage_... --apply
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from sidecar.shared.proposal_graph import compile_proposal_graph
from sidecar.supervisor.organizer import organize_project_content
from sidecar.supervisor.pipeline_tools import repair_import_artifacts


TOOL_VERSION = "w1-pending-package-semantic-rereview/v1"
MIGRATION_ROOT = Path("system/migrations/w1-pending-semantic-rereview")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_bytes(path, _canonical_json(value))


def _relative(project: Path, path: Path) -> str:
    return path.relative_to(project).as_posix()


def _finish_prepared_transaction(project: Path, migration_root: Path) -> str:
    receipt_path = migration_root / "receipt.json"
    receipt = _read_json(receipt_path)
    if receipt.get("phase") != "prepared":
        return str(receipt.get("phase") or "unknown")
    planned = receipt.get("plannedWrites")
    if not isinstance(planned, list) or not planned:
        raise ValueError(f"Prepared semantic migration has no planned writes: {receipt_path}")

    try:
        for entry in planned:
            target = project / str(entry["path"])
            expected_hash = str(entry["sha256"])
            if target.is_file() and _sha256(target.read_bytes()) == expected_hash:
                continue
            staged = project / str(entry["stagedPath"])
            if not staged.is_file() or _sha256(staged.read_bytes()) != expected_hash:
                raise ValueError(f"Prepared semantic migration payload is missing or corrupt: {staged}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
    except (OSError, ValueError) as error:
        backed_up = receipt.get("backedUp")
        if not isinstance(backed_up, list):
            raise
        for entry in backed_up:
            target = project / str(entry["path"])
            backup = project / str(entry["backupPath"])
            expected_hash = str(entry["sha256"])
            if not backup.is_file() or _sha256(backup.read_bytes()) != expected_hash:
                raise ValueError(f"Cannot roll back semantic migration; backup is missing or corrupt: {backup}") from error
            _atomic_write_bytes(target, backup.read_bytes())
        _atomic_write_json(receipt_path, {
            **receipt,
            "phase": "rolled_back",
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "error": str(error),
        })
        return "rolled_back"

    written = [
        {"path": str(entry["path"]), "sha256": _sha256((project / str(entry["path"])).read_bytes())}
        for entry in planned
    ]
    _atomic_write_json(receipt_path, {
        **receipt,
        "phase": "completed",
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "written": written,
    })
    return "completed"


def _recover_prepared_transactions(project: Path) -> list[str]:
    recovered: list[str] = []
    root = project / MIGRATION_ROOT
    if not root.is_dir():
        return recovered
    for receipt_path in sorted(root.glob("*/receipt.json")):
        try:
            receipt = _read_json(receipt_path)
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("phase") != "prepared":
            continue
        phase = _finish_prepared_transaction(project, receipt_path.parent)
        recovered.append(f"{_relative(project, receipt_path.parent)}:{phase}")
    return recovered


def _prepare_staging_transaction(
    project: Path,
    migration_root: Path,
    *,
    import_run_id: str,
    writes: list[tuple[Path, Any]],
    report: dict[str, Any],
) -> None:
    backup_root = migration_root / "backup"
    staging_root = migration_root / "staged"
    backed_up: list[dict[str, str]] = []
    planned_writes: list[dict[str, str]] = []
    for source, value in writes:
        relative = _relative(project, source)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        backed_up.append({
            "path": relative,
            "backupPath": _relative(project, backup),
            "sha256": _sha256(source.read_bytes()),
        })

        staged = staging_root / relative
        payload = _canonical_json(value)
        _atomic_write_bytes(staged, payload)
        planned_writes.append({
            "path": relative,
            "stagedPath": _relative(project, staged),
            "sha256": _sha256(payload),
        })

    _atomic_write_json(migration_root / "receipt.json", {
        "toolVersion": TOOL_VERSION,
        "phase": "prepared",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "importRunId": import_run_id,
        "backedUp": backed_up,
        "plannedWrites": planned_writes,
        "report": report,
    })


def _operations(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [operation for operation in proposal.get("operations", []) if isinstance(operation, dict)]


def _proposal_run_ids(proposal: dict[str, Any]) -> set[str]:
    direct = proposal.get("importRunId") or proposal.get("import_run_id")
    values = {str(direct).strip()} if direct else set()
    for operation in _operations(proposal):
        fields = operation.get("fields") if isinstance(operation.get("fields"), dict) else {}
        value = fields.get("importRunId") or fields.get("import_run_id")
        if value:
            values.add(str(value).strip())
    return {value for value in values if value}


def _is_w1_pending(proposal: dict[str, Any]) -> bool:
    status = proposal.get("status")
    return (
        status in (None, "pending")
        and (proposal.get("source_workflow") == "W1_import" or proposal.get("source") == "import")
    )


def _select_run_id(inbox: list[dict[str, Any]], requested: str | None) -> str:
    available = sorted({run_id for proposal in inbox if _is_w1_pending(proposal) for run_id in _proposal_run_ids(proposal)})
    if requested:
        if requested not in available:
            raise ValueError(f"No pending W1 proposal package for import run {requested!r}; available={available!r}")
        return requested
    if len(available) != 1:
        raise ValueError(f"Expected exactly one pending W1 import run; pass --import-run-id. available={available!r}")
    return available[0]


def _belongs_to_run(proposal: dict[str, Any], import_run_id: str) -> bool:
    return _is_w1_pending(proposal) and import_run_id in _proposal_run_ids(proposal)


def _graph_path(project: Path, import_run_id: str) -> Path:
    direct = project / "system" / "imports" / import_run_id / "proposal_graph.json"
    if direct.is_file():
        return direct
    matches: list[Path] = []
    for candidate in sorted((project / "system" / "imports").glob("**/proposal_graph.json")):
        try:
            graph = _read_json(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(graph, dict) and str(graph.get("importRunId") or "") == import_run_id:
            matches.append(candidate)
    if len(matches) != 1:
        raise ValueError(f"Could not resolve a unique proposal graph for {import_run_id!r}: {[str(path) for path in matches]!r}")
    return matches[0]


def _world_and_character_candidates(proposals: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    characters: dict[str, dict[str, Any]] = {}
    worlds: dict[str, dict[str, Any]] = {}
    proposal_by_world: dict[str, str] = {}
    for proposal in proposals:
        proposal_id = str(proposal.get("id") or "")
        for operation in _operations(proposal):
            if operation.get("op") != "create":
                continue
            fields = operation.get("fields")
            if not isinstance(fields, dict):
                continue
            entity_id = str(operation.get("entityId") or fields.get("id") or "")
            if operation.get("entityType") == "character" and entity_id:
                characters[entity_id] = deepcopy(fields)
            if operation.get("entityType") == "world_item" and entity_id:
                name = str(fields.get("name") or "").strip()
                if not name:
                    raise ValueError(f"World proposal {proposal_id!r} has no name")
                if entity_id in proposal_by_world or name in worlds:
                    raise ValueError(f"Duplicate pending World candidate {entity_id!r}/{name!r}; re-review refuses to guess")
                candidate = deepcopy(fields)
                candidate["id"] = entity_id
                worlds[name] = candidate
                proposal_by_world[entity_id] = proposal_id
    return characters, worlds, proposal_by_world


def _replace_world_container_dependency(proposal: dict[str, Any], container_ids: set[str], target_id: str) -> None:
    dependencies = proposal.get("dependsOn") or proposal.get("depends_on") or []
    preserved = [str(value) for value in dependencies if str(value) and str(value) not in container_ids]
    proposal["dependsOn"] = [*preserved, target_id] if target_id not in preserved else preserved
    proposal.pop("depends_on", None)


def _hold_proposal(proposal: dict[str, Any], *, reason: str, review: dict[str, Any]) -> None:
    """Keep the candidate pending, visible, and graph-addressable for review.

    The React Proposal contract deliberately has no ``blocked`` status.  A
    pending proposal with ``lastBlockReason`` remains in its import package,
    disables acceptance, and exposes Workbench's repair path.  The review
    record lives under the existing extensible ``data`` field rather than an
    undocumented top-level key.
    """
    proposal["status"] = "pending"
    previous_reason = proposal.get("lastBlockReason")
    proposal["lastBlockReason"] = reason
    if previous_reason != reason or not proposal.get("lastBlockedAt"):
        proposal["lastBlockedAt"] = datetime.now(timezone.utc).isoformat()
    data = proposal.get("data") if isinstance(proposal.get("data"), dict) else {}
    proposal["data"] = {**data, "semanticReview": review}


def _reconcile_relocations(
    characters: dict[str, dict[str, Any]], worlds: dict[str, dict[str, Any]], relocation_plans: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not relocation_plans:
        return characters
    actions = [{
        "action_type": "relocate",
        "target_entity_ids": [plan["source_candidate_id"]],
        "proposed_operations": [{"op": "relocate_world_item", "relocation_plan": plan}],
    } for plan in relocation_plans]
    state = {
        "entity_registry": {
            "characters": deepcopy(characters),
            "world": {item.get("name"): item.get("category") for item in worlds.values()},
            "world_detailed": {str(item.get("id")): item for item in worlds.values()},
        },
        "minor_repair_log": [], "supervisor_log": [], "quarantine_candidates": [], "applied_relocation_plan_ids": [],
    }
    repaired = asyncio.run(repair_import_artifacts(state, actions))
    return repaired["entity_registry"]["characters"]


def rereview_pending_package(project: Path, *, import_run_id: str | None = None, apply: bool = False) -> dict[str, Any]:
    project = project.expanduser().resolve()
    recovered_transactions = _recover_prepared_transactions(project)
    inbox_path = project / "system" / "inbox.json"
    if not project.is_dir() or not inbox_path.is_file():
        raise ValueError("project must contain system/inbox.json")
    inbox = _read_json(inbox_path)
    if not isinstance(inbox, list) or not all(isinstance(item, dict) for item in inbox):
        raise ValueError("system/inbox.json must be a JSON proposal list")
    selected_run_id = _select_run_id(inbox, import_run_id)
    graph_path = _graph_path(project, selected_run_id)
    package = [deepcopy(proposal) for proposal in inbox if _belongs_to_run(proposal, selected_run_id)]
    if not package:
        raise ValueError(f"No pending proposals selected for {selected_run_id!r}")

    characters, worlds, proposal_by_world = _world_and_character_candidates(package)
    organizer = organize_project_content({
        "characters": characters, "events": [], "relationships": [], "world_candidates": worlds,
        "manuscript_notes": [], "timeline_architecture": {}, "project_digest": {}, "source_language": "zh",
    })
    survivor_by_id = {item["entity_id"]: item for item in organizer["world_items"]}
    assessment_by_id = {item["candidate_id"]: item for item in organizer["candidate_ledger"]}
    decision_by_id = {item["item_id"]: item for item in organizer["review_decisions"]}
    relocation_by_id = {item["source_candidate_id"]: item for item in organizer["relocation_plans"]}
    excluded_by_id = {item["entity_id"]: item for item in organizer["excluded_items"]}
    proposal_by_id = {str(proposal.get("id") or ""): proposal for proposal in package}
    container_ids = {
        str(operation.get("entityId") or "")
        for proposal in package for operation in _operations(proposal)
        if operation.get("entityType") == "world_container" and operation.get("op") == "create"
    }

    updated_characters = _reconcile_relocations(characters, worlds, list(relocation_by_id.values()))
    changed: list[dict[str, Any]] = []
    review_by_id: dict[str, dict[str, Any]] = {}
    held_world_ids: set[str] = set()
    for candidate in worlds.values():
        world_id = str(candidate["id"])
        proposal = proposal_by_id[proposal_by_world[world_id]]
        ledger = assessment_by_id.get(world_id, {})
        decision = decision_by_id.get(world_id, {})
        relocation = relocation_by_id.get(world_id)
        exclusion = excluded_by_id.get(world_id, {})
        review = {
            "ledger": ledger,
            "decision": decision,
            **({"organizerExclusion": exclusion} if exclusion else {}),
            **({"relocationPlan": relocation} if relocation else {}),
        }
        review_by_id[world_id] = review
        survivor = survivor_by_id.get(world_id)
        if survivor is None:
            held_world_ids.add(world_id)
            reason = str(exclusion.get("reason") or (ledger.get("reason_codes") or ["semantic_hold"])[0])
            _hold_proposal(proposal, reason=f"Semantic re-review requires reviewer action: {reason}", review=review)
            changed.append({"proposalId": proposal["id"], "entityId": world_id, "name": candidate.get("name"), "action": "review_hold", "reason": reason})
            continue
        target_container = str(survivor["containerId"])
        if target_container not in container_ids:
            held_world_ids.add(world_id)
            _hold_proposal(proposal, reason=f"Semantic re-review needs missing staged container: {target_container}", review=review)
            changed.append({"proposalId": proposal["id"], "entityId": world_id, "name": candidate.get("name"), "action": "review_hold", "reason": "missing_staged_container"})
            continue
        for operation in _operations(proposal):
            if operation.get("entityType") != "world_item" or str(operation.get("entityId") or "") != world_id:
                continue
            fields = operation.get("fields")
            if not isinstance(fields, dict):
                continue
            before = {key: fields.get(key) for key in ("category", "type", "containerId", "folderId", "parentId", "categoryPath")}
            fields.update({
                "category": survivor["category"], "type": survivor["category"],
                "containerId": target_container, "parentId": target_container,
                "folderId": target_container,
                "categoryPath": survivor["categoryPath"],
            })
            after = {key: fields.get(key) for key in before}
            if before != after:
                data = proposal.get("data") if isinstance(proposal.get("data"), dict) else {}
                proposal["data"] = {**data, "semanticReview": review}
                _replace_world_container_dependency(proposal, container_ids, target_container)
                changed.append({"proposalId": proposal["id"], "entityId": world_id, "name": candidate.get("name"), "action": "rerouted", "before": before, "after": after})

    for proposal in package:
        for operation in _operations(proposal):
            if operation.get("entityType") != "character" or operation.get("op") != "create":
                continue
            fields = operation.get("fields")
            entity_id = str(operation.get("entityId") or "")
            replacement = updated_characters.get(entity_id)
            if isinstance(fields, dict) and replacement and fields != replacement:
                operation["fields"] = replacement
                changed.append({"proposalId": proposal["id"], "entityId": entity_id, "name": replacement.get("name"), "action": "character_enriched_from_relocation"})

    # Held candidates remain in the graph and retain their references.  This
    # makes the package reviewable as a unit and prevents a migration from
    # silently deleting evidence links merely to make a graph look clean.
    compiled_graph = compile_proposal_graph(package, existing_ids={})
    if compiled_graph["blockingErrors"]:
        raise ValueError(f"Re-reviewed active proposal graph is blocked: {compiled_graph['blockingErrors']!r}")

    rewritten_inbox = [
        next((candidate for candidate in package if candidate.get("id") == proposal.get("id")), proposal)
        if _belongs_to_run(proposal, selected_run_id) else proposal
        for proposal in inbox
    ]
    changed_by_entity = {str(item["entityId"]): item for item in changed}
    candidate_decisions: list[dict[str, Any]] = []
    for candidate in worlds.values():
        world_id = str(candidate["id"])
        review = review_by_id[world_id]
        ledger = review.get("ledger") if isinstance(review.get("ledger"), dict) else {}
        decision = review.get("decision") if isinstance(review.get("decision"), dict) else {}
        exclusion = review.get("organizerExclusion") if isinstance(review.get("organizerExclusion"), dict) else {}
        entry = dict(changed_by_entity.get(world_id) or {
            "proposalId": proposal_by_world[world_id], "entityId": world_id,
            "name": candidate.get("name"), "action": "accepted_without_change",
        })
        entry["review"] = {
            "status": ledger.get("status"), "reasonCodes": ledger.get("reason_codes", []),
            "action": decision.get("action") or ("hold" if exclusion else None),
            "proposedType": decision.get("proposed_type") or ("unknown" if exclusion else None),
            "targetFolderId": decision.get("target_folder_id"),
            "organizerExclusion": exclusion or None,
        }
        candidate_decisions.append(entry)

    report = {
        "toolVersion": TOOL_VERSION, "project": str(project), "importRunId": selected_run_id,
        "dryRun": not apply, "packageProposalCount": len(package), "worldCandidateCount": len(worlds),
        "decisions": sorted(changed, key=lambda item: (str(item["action"]), str(item["entityId"]))),
        "candidateDecisions": sorted(candidate_decisions, key=lambda item: str(item["entityId"])),
        "heldWorldIds": sorted(held_world_ids), "prunedWorldReferences": 0,
        "graphProposalCount": len(package), "graphDiagnostics": compiled_graph["diagnostics"],
        "graphDroppedRefs": compiled_graph["droppedRefs"],
        "paths": {"inbox": _relative(project, inbox_path), "proposalGraph": _relative(project, graph_path)},
        "recoveredTransactions": recovered_transactions,
    }
    if not apply or (rewritten_inbox == inbox and _read_json(graph_path) == compiled_graph):
        report["status"] = "dry_run" if not apply else "noop"
        return report

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    migration_root = project / MIGRATION_ROOT / stamp
    _prepare_staging_transaction(
        project,
        migration_root,
        import_run_id=selected_run_id,
        writes=[(inbox_path, rewritten_inbox), (graph_path, compiled_graph)],
        report=report,
    )
    phase = _finish_prepared_transaction(project, migration_root)
    if phase != "completed":
        raise ValueError(f"Semantic re-review transaction did not commit: {phase}")
    _atomic_write_json(migration_root / "review.json", report)
    report.update({"status": "applied", "migrationRoot": _relative(project, migration_root)})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline semantic re-review for a pending W1 proposal package")
    parser.add_argument("project", type=Path)
    parser.add_argument("--import-run-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args(argv)
    try:
        report = rereview_pending_package(args.project, import_run_id=args.import_run_id, apply=args.apply)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"W1 pending-package semantic re-review: {report['status']}")
        print(json.dumps({key: report[key] for key in ("importRunId", "decisions", "blockedWorldIds", "prunedWorldReferences")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
