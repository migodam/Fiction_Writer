"""S2 — Memory Writer

The sole write path for all workflow nodes.
No workflow node may write project files directly — all writes go through propose_write().

Confidence routing (from langgraph.md skill: memory-writer-rules):
  >= 0.85 AND auto_apply=True  → apply directly, status="accepted", append to history
  0.60 – 0.85                  → stage as pending Proposal in system/inbox.json
  < 0.60                       → stage as pending Proposal, title prefixed "[Needs Review]"

Entity Registry updates go through update_registry() — append-only, never overwrite.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timezone

from sidecar.shared import s4_proposal_queue


# ── Public API ────────────────────────────────────────────────────────────────

async def propose_write(op: dict, project_path: str) -> dict:
    """Stage or apply a WriteOperation, returning the resulting Proposal.

    op fields:
      op_type:         "create" | "update" | "delete"
      entity_type:     str   (e.g. "character", "scene", "timeline_event")
      entity_id:       str | None
      data:            dict
      source_workflow: str
      confidence:      float (0–1)
      auto_apply:      bool
      depends_on:      list[str]
    """
    proposal = _build_proposal(op)
    confidence = float(op.get("confidence", 0.5))
    auto_apply = bool(op.get("auto_apply", False))

    if confidence >= 0.85 and auto_apply:
        await _apply_to_file(proposal, project_path)
        proposal["status"] = "accepted"
        proposal["resolvedAt"] = datetime.now(timezone.utc).isoformat()
        await _append_to_history(proposal, project_path)
    elif confidence >= 0.60:
        proposal["status"] = "pending"
        await s4_proposal_queue.push_to_inbox(proposal, project_path)
    else:
        proposal["status"] = "pending"
        proposal["title"] = f"[Needs Review] {proposal['title']}"
        await s4_proposal_queue.push_to_inbox(proposal, project_path)

    return proposal


async def update_registry(
    entry: dict,
    entry_type: str,
    project_path: str,
) -> None:
    """Append-only update to the Entity Registry in project.json.

    entry_type: "characters" | "events" | "worldEntries"
    entry must have a "canonicalId" (or "canonical_id") field.
    Existing entries are extended (aliases/notes appended), never overwritten.
    """
    root = pathlib.Path(project_path)
    project_file = root / "project.json"

    project = _read_json_sync(project_file) or {}
    registry = project.setdefault("entityRegistry", {})
    section = registry.setdefault(entry_type, {})

    canonical_id = entry.get("canonicalId") or entry.get("canonical_id")
    if not canonical_id:
        raise ValueError("entry must have a canonicalId field")

    if canonical_id in section:
        existing = section[canonical_id]
        # Append-only: extend aliases and notes
        for key in ("aliases", "notes"):
            new_items = entry.get(key, [])
            existing.setdefault(key, [])
            for item in new_items:
                if item not in existing[key]:
                    existing[key].append(item)
        # Update confidence only if higher
        if entry.get("confidence", 0) > existing.get("confidence", 0):
            existing["confidence"] = entry["confidence"]
    else:
        section[canonical_id] = entry

    _write_json_sync(project_file, project)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_proposal(op: dict) -> dict:
    """Map a WriteOperation to a Proposal in project.ts frontend format."""
    op_kind_map = {
        "create": "entity_update",
        "update": "entity_update",
        "delete": "entity_update",
    }
    source_workflow = op.get("source_workflow", "unknown")
    entity_type = op.get("entity_type", "unknown")
    op_type = op.get("op_type", "update")
    entity_id = op.get("entity_id")

    title = _build_title(op_type, entity_type, entity_id, op.get("data", {}))

    return {
        "id": f"prop_{uuid.uuid4().hex[:12]}",
        "title": title,
        "source": _map_source(source_workflow),
        "kind": op_kind_map.get(op_type, "entity_update"),
        "operations": [
            {
                "op": op_type,
                "entityType": entity_type,
                "entityId": entity_id,
                "fields": op.get("data", {}),
            }
        ],
        "dependsOn": op.get("depends_on", []),
        "conflictsWith": [],
        "confidence": op.get("confidence", 0.5),
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "reviewPolicy": "manual_workbench",
        "source_workflow": source_workflow,
    }


def _build_title(op_type: str, entity_type: str, entity_id: str | None, data: dict) -> str:
    name = data.get("name") or data.get("title") or entity_id or "unknown"
    verbs = {"create": "Create", "update": "Update", "delete": "Delete"}
    verb = verbs.get(op_type, "Modify")
    return f"{verb} {entity_type}: {name}"


def _map_source(workflow_name: str) -> str:
    """Map internal workflow name to frontend ProposalSource enum."""
    mapping = {
        "W1_import": "import",
        "W2_manuscript_sync": "agent",
        "W3_writing_assistant": "agent",
        "W4_consistency_check": "consistency",
        "W5_simulation": "agent",
        "W6_beta_reader": "agent",
        "W7_metadata_ingestion": "agent",
        "W0_orchestrator": "agent",
    }
    return mapping.get(workflow_name, "agent")


async def _apply_to_file(proposal: dict, project_path: str) -> None:
    """Route the proposal to the correct project file and apply the write."""
    root = pathlib.Path(project_path)

    # Check if any operation is array/singleton-backed first
    for op in proposal.get("operations", []):
        entity_type = op.get("entityType", "")
        if entity_type in _ARRAY_ENTITY_PATHS or entity_type in _SINGLETON_ENTITY_PATHS:
            await _apply_to_array_file(proposal, project_path)
            return

    for op in proposal.get("operations", []):
        entity_type = op.get("entityType", "")
        entity_id = op.get("entityId")
        fields = op.get("fields", {})
        op_type = op.get("op", "update")

        target_path = _resolve_entity_path(root, entity_type, entity_id)
        if target_path is None:
            continue

        if op_type == "delete":
            target_path.unlink(missing_ok=True)
        elif op_type == "create":
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json_sync(target_path, fields)
        else:  # update
            existing = _read_json_sync(target_path) or {}
            existing.update(fields)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json_sync(target_path, existing)


def _resolve_entity_path(
    root: pathlib.Path, entity_type: str, entity_id: str | None
) -> pathlib.Path | None:
    """Map entity_type → actual filesystem path.

    Returns None for array-backed entity types (relationship, character_tag,
    world_container, world_settings, timeline_branch) — those go through
    _apply_to_array_file instead.
    """
    if not entity_id:
        return None
    paths = {
        "character": root / "entities" / "characters" / f"{entity_id}.json",
        "timeline_event": root / "entities" / "timeline" / f"{entity_id}.json",
        "chapter": root / "writing" / "chapters" / f"{entity_id}.json",
        "scene": root / "writing" / "scenes" / f"{entity_id}.meta.json",
        "world_item": root / "entities" / "world" / f"{entity_id}.json",
        "graph_board": root / "entities" / "graph" / f"{entity_id}.json",
    }
    return paths.get(entity_type)


# ── Array-backed entity types ─────────────────────────────────────────────────

# entity_type → path within project root (array-backed JSON files)
_ARRAY_ENTITY_PATHS: dict[str, str] = {
    "relationship": "entities/relationships.json",
    "character_tag": "entities/character-tags.json",
    "world_container": "entities/world/containers.json",
    "timeline_branch": "entities/timeline/branches.json",
}

# Singleton file (not an array, just a single JSON object)
_SINGLETON_ENTITY_PATHS: dict[str, str] = {
    "world_settings": "entities/world/settings.json",
}


async def _apply_to_array_file(proposal: dict, project_path: str) -> None:
    """Apply a proposal whose entity type is array-backed.

    For array types: appends or updates (by id) the entry in the array file.
    For singleton types (world_settings): merges fields into the single object.
    """
    root = pathlib.Path(project_path)
    for op in proposal.get("operations", []):
        entity_type = op.get("entityType", "")
        entity_id = op.get("entityId")
        fields = op.get("fields", {})
        op_type = op.get("op", "create")

        if entity_type in _ARRAY_ENTITY_PATHS:
            file_path = root / _ARRAY_ENTITY_PATHS[entity_type]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            arr: list = _read_json_sync(file_path) or []
            if op_type == "delete":
                arr = [e for e in arr if e.get("id") != entity_id]
            elif op_type == "create":
                # Avoid duplicates by id
                if entity_id and any(e.get("id") == entity_id for e in arr):
                    arr = [
                        {**e, **fields} if e.get("id") == entity_id else e
                        for e in arr
                    ]
                else:
                    arr.append(fields)
            else:  # update
                found = False
                for i, e in enumerate(arr):
                    if e.get("id") == entity_id:
                        arr[i] = {**e, **fields}
                        found = True
                        break
                if not found:
                    arr.append(fields)
            _write_json_sync(file_path, arr)

        elif entity_type in _SINGLETON_ENTITY_PATHS:
            file_path = root / _SINGLETON_ENTITY_PATHS[entity_type]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if op_type == "delete":
                file_path.unlink(missing_ok=True)
            else:
                existing: dict = _read_json_sync(file_path) or {}  # type: ignore[assignment]
                existing.update(fields)
                _write_json_sync(file_path, existing)


async def _append_to_history(proposal: dict, project_path: str) -> None:
    """Append an accepted/rejected proposal to system/history.json."""
    history_path = pathlib.Path(project_path) / "system" / "history.json"
    history = _read_json_sync(history_path) or []
    history.append(proposal)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_sync(history_path, history)


def _read_json_sync(path: pathlib.Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json_sync(path: pathlib.Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
