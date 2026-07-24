"""Deterministic reference-graph compiler for frontend Workbench proposals."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable


# entity type -> field path -> (accepted target types, cardinality, required)
# Reference paths are intentionally explicit; this compiler never guesses that
# arbitrary strings are IDs.
REFERENCE_SCHEMA: dict[str, dict[str, tuple[tuple[str, ...], str, bool]]] = {
    "character": {
        "tagIds": (("character_tag",), "list", False),
        "linkedSceneIds": (("scene",), "list", False),
        "linkedEventIds": (("timeline_event",), "list", False),
        "linkedWorldItemIds": (("world_item",), "list", False),
    },
    "chapter": {"sceneIds": (("scene",), "list", False)},
    "scene": {
        "chapterId": (("chapter",), "scalar", True),
        "povCharacterId": (("character",), "scalar", False),
        "linkedCharacterIds": (("character",), "list", False),
        "linkedEventIds": (("timeline_event",), "list", False),
        "linkedWorldItemIds": (("world_item",), "list", False),
    },
    "relationship": {
        "sourceId": (("character",), "scalar", True),
        "targetId": (("character",), "scalar", True),
    },
    "timeline_branch": {
        "parentBranchId": (("timeline_branch",), "scalar", False),
        "mergeTargetBranchId": (("timeline_branch",), "scalar", False),
        "forkEventId": (("timeline_event",), "scalar", False),
        "mergeEventId": (("timeline_event",), "scalar", False),
        "startAnchor.eventId": (("timeline_event",), "scalar", False),
        "endAnchor.eventId": (("timeline_event",), "scalar", False),
    },
    "timeline_event": {
        "branchId": (("timeline_branch",), "scalar", True),
        "sharedBranchIds": (("timeline_branch",), "list", False),
        "locationIds": (("world_item",), "list", False),
        "participantCharacterIds": (("character",), "list", False),
        "linkedSceneIds": (("scene",), "list", False),
        "linkedWorldItemIds": (("world_item",), "list", False),
        # mergedEventIds is alias metadata, not a dependency edge.
        "mergedEventIds": (("timeline_event",), "alias_list", False),
    },
    "world_item": {
        "containerId": (("world_container",), "scalar", True),
        "parentId": (("world_container", "world_item"), "scalar", False),
    },
}

_TYPE_ALIASES = {"world": "world_item", "world_entity": "world_item"}


def compile_proposal_graph(
    proposals: Iterable[dict[str, Any]],
    existing_ids: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Compile proposal references without reading or writing canonical data.

    ``existing_ids`` is a typed snapshot of canonical entities.  References to
    those IDs resolve without an intra-package edge, while references produced
    by this package gain a producer edge and deterministic ordering.
    """
    normalized = [deepcopy(proposal) for proposal in proposals if isinstance(proposal, dict)]
    normalized.sort(key=_proposal_key)
    existing = _normalize_existing_ids(existing_ids)
    errors: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    producers: dict[tuple[str, str], str] = {}
    proposal_by_id: dict[str, dict[str, Any]] = {}

    for index, proposal in enumerate(normalized):
        proposal_id = _proposal_id(proposal, index)
        proposal["id"] = proposal_id
        if proposal_id in proposal_by_id:
            errors.append(_error("duplicate_proposal_id", proposal_id=proposal_id))
        proposal_by_id[proposal_id] = proposal
        for operation in _operations(proposal):
            if operation.get("op") != "create":
                continue
            key, explicit_ids = _producer_key(proposal, operation)
            if len(explicit_ids) > 1:
                errors.append(_error(
                    "producer_id_mismatch",
                    proposal_id=proposal_id,
                    entity_type=_normalize_type(operation.get("entityType")),
                    ids=explicit_ids,
                ))
            if key is None:
                errors.append(_error("invalid_create_producer", proposal_id=proposal_id))
            elif key in producers:
                errors.append(_error("duplicate_producer", proposal_id=proposal_id, entity_type=key[0], entity_id=key[1], producer_ids=sorted([producers[key], proposal_id])))
            else:
                producers[key] = proposal_id

    remaps = _collect_remaps(normalized, diagnostics)
    _add_merged_event_remaps(normalized, remaps, diagnostics)
    edges: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for proposal in normalized:
        proposal_id = str(proposal["id"])
        _compile_depends_on(proposal, proposal_id, proposal_by_id, producers, existing, edges, diagnostics)
        for operation in _operations(proposal):
            fields = operation.get("fields")
            if not isinstance(fields, dict):
                continue
            entity_type = _normalize_type(operation.get("entityType"))
            for path, (target_types, cardinality, required) in REFERENCE_SCHEMA.get(entity_type, {}).items():
                present, value = _get_path(fields, path)
                if not present:
                    if required:
                        errors.append(_error("missing_required_reference", proposal_id=proposal_id, field=path, entity_type=entity_type))
                    continue
                if cardinality == "alias_list":
                    if not isinstance(value, list):
                        errors.append(_error("invalid_reference_shape", proposal_id=proposal_id, field=path, expected="list"))
                    else:
                        _set_path(fields, path, _unique_sorted(str(item).strip() for item in value))
                    continue
                if cardinality == "scalar" and isinstance(value, list):
                    errors.append(_error("invalid_reference_shape", proposal_id=proposal_id, field=path, expected="scalar"))
                    continue
                if cardinality == "list" and not isinstance(value, list):
                    errors.append(_error("invalid_reference_shape", proposal_id=proposal_id, field=path, expected="list"))
                    continue
                kept: list[str] = []
                for raw in (_as_list(value) if cardinality == "list" else [value]):
                    if raw is None or not str(raw).strip():
                        if required:
                            errors.append(_error(
                                "missing_required_reference",
                                proposal_id=proposal_id,
                                field=path,
                                entity_type=target_types[0],
                            ))
                        continue
                    resolved_id, resolved_type, producer_id = _resolve_reference(target_types, raw, remaps, producers, existing)
                    item = {"proposalId": proposal_id, "entityType": entity_type, "field": path, "targetId": resolved_id}
                    item["targetType" if len(target_types) == 1 else "targetTypes"] = target_types[0] if len(target_types) == 1 else list(target_types)
                    if not resolved_type:
                        if required:
                            errors.append(_error("missing_required_reference", **item))
                        else:
                            dropped.append(item)
                            diagnostics.append({"code": "dropped_optional_reference", **item})
                        continue
                    kept.append(resolved_id)
                    if producer_id and producer_id != proposal_id:
                        edges.append(_edge(proposal_id, producer_id, resolved_type, path, required))
                _set_path(fields, path, _unique_sorted(kept) if cardinality == "list" else (kept[0] if kept else None))

    edges = _unique_edges(edges)
    order, cycle_errors = _ordered_proposal_ids(proposal_by_id, edges)
    errors.extend(cycle_errors)
    compiler_metadata = {
        "contractVersion": "w1-package-graph-v2",
        "order": 0,
        "proposalCount": len(normalized),
        "orderedProposalIds": list(order),
    }
    order_by_id = {proposal_id: index for index, proposal_id in enumerate(order)}
    for proposal in normalized:
        metadata = dict(compiler_metadata)
        metadata["order"] = order_by_id.get(str(proposal["id"]), len(order))
        proposal["packageCompiler"] = metadata
    errors.sort(key=_stable_value)
    diagnostics.sort(key=_stable_value)
    dropped.sort(key=_stable_value)
    result = {
        "contractVersion": "w1-package-graph-v2",
        "normalizedProposals": normalized,
        "orderedProposalIds": order,
        "executionPlan": [{"phase": "apply", "proposalIds": list(order)}],
        "edges": edges,
        "producers": _public_producers(producers),
        "remaps": _public_remaps(remaps),
        "droppedRefs": dropped,
        "diagnostics": diagnostics,
        "blockingErrors": errors,
        "atomic": not errors,
    }
    result.update({"normalized_proposals": result["normalizedProposals"], "ordered_proposal_ids": result["orderedProposalIds"], "dropped_refs": result["droppedRefs"], "blocking_errors": result["blockingErrors"]})
    return result


def compile_import_run_package(
    project_path: str | Path,
    import_run_id: str,
    existing_ids: dict[str, Iterable[str]] | None = None,
    *,
    remove_invalid_package: bool = False,
) -> dict[str, Any]:
    """Compile one W1 inbox package and atomically rewrite only that package.

    Canonical project data is never touched.  A graph artifact is always
    written to the import run directory; inbox replacement occurs only when
    the compiled package is atomic.
    """
    root = Path(project_path)
    inbox_path = root / "system" / "inbox.json"
    inbox = _read_json_list(inbox_path)
    package = [proposal for proposal in inbox if _belongs_to_import_run(proposal, import_run_id)]
    compilation = compile_proposal_graph(package, existing_ids)
    compilation["importRunId"] = import_run_id
    compilation["inboxUpdated"] = False
    compilation["packageRemoved"] = False
    if compilation["atomic"]:
        for proposal in compilation["normalizedProposals"]:
            for key in ("lastBlockReason", "lastBlockedAt", "blockedReason"):
                proposal.pop(key, None)
        rewritten = {str(proposal["id"]): proposal for proposal in compilation["normalizedProposals"]}
        _atomic_write_json(inbox_path, [rewritten.get(str(proposal.get("id")), proposal) for proposal in inbox])
        compilation["inboxUpdated"] = True
    elif remove_invalid_package:
        _atomic_write_json(inbox_path, [proposal for proposal in inbox if not _belongs_to_import_run(proposal, import_run_id)])
        compilation["inboxUpdated"] = True
        compilation["packageRemoved"] = True
    artifact_path = root / "system" / "imports" / import_run_id / "proposal_graph.json"
    _atomic_write_json(artifact_path, _artifact_metadata(compilation))
    compilation["artifactPath"] = str(artifact_path)
    return compilation


def _compile_depends_on(proposal: dict[str, Any], proposal_id: str, proposal_by_id: dict[str, dict[str, Any]], producers: dict[tuple[str, str], str], existing: dict[str, set[str]], edges: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> None:
    for dependency in _as_list(proposal.get("dependsOn", proposal.get("depends_on", []))):
        dependency_id = str(dependency or "").strip()
        if not dependency_id:
            continue
        if dependency_id in proposal_by_id:
            if dependency_id != proposal_id:
                edges.append(_edge(proposal_id, dependency_id, "proposal", "dependsOn", True))
            continue
        matches = sorted({producer_id for (entity_type, entity_id), producer_id in producers.items() if entity_id == dependency_id})
        if len(matches) == 1 and matches[0] != proposal_id:
            edges.append(_edge(proposal_id, matches[0], "entity", "dependsOn", True))
        elif len(matches) > 1:
            diagnostics.append({"code": "ambiguous_depends_on_ignored", "proposalId": proposal_id, "dependencyId": dependency_id})
        elif any(dependency_id in ids for ids in existing.values()):
            diagnostics.append({"code": "canonical_depends_on_ignored", "proposalId": proposal_id, "dependencyId": dependency_id})
        else:
            # W1 uses entity IDs here and explicit typed references already
            # enforce correctness.  An untyped dependency cannot be blocked.
            diagnostics.append({"code": "unresolved_depends_on_ignored", "proposalId": proposal_id, "dependencyId": dependency_id})


def _collect_remaps(proposals: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    remaps: dict[tuple[str, str], str] = {}
    for proposal in proposals:
        for source in (proposal.get("remap"), proposal.get("remaps"), proposal.get("entityRemap"), proposal.get("entityRemaps"), proposal.get("aliasRemaps"), proposal.get("aliases")):
            for entity_type, old_id, new_id in _remap_entries(source):
                _add_remap(remaps, _normalize_type(entity_type), old_id, new_id, diagnostics)
    return remaps


def _add_merged_event_remaps(proposals: list[dict[str, Any]], remaps: dict[tuple[str, str], str], diagnostics: list[dict[str, Any]]) -> None:
    for proposal in proposals:
        for operation in _operations(proposal):
            if operation.get("op") != "create" or _normalize_type(operation.get("entityType")) != "timeline_event":
                continue
            survivor = str(operation.get("entityId") or "").strip()
            fields = operation.get("fields")
            if not survivor or not isinstance(fields, dict):
                continue
            for loser in _as_list(fields.get("mergedEventIds")):
                _add_remap(remaps, "timeline_event", str(loser).strip(), survivor, diagnostics)


def _add_remap(remaps: dict[tuple[str, str], str], entity_type: str, old_id: str, new_id: str, diagnostics: list[dict[str, Any]]) -> None:
    key, target = (entity_type, old_id.strip()), new_id.strip()
    if not key[0] or not key[1] or not target or key[1] == target:
        return
    if key in remaps and remaps[key] != target:
        diagnostics.append({"code": "conflicting_remap_ignored", "entityType": key[0], "from": key[1], "to": target})
    else:
        remaps[key] = target


def _remap_entries(value: Any) -> Iterable[tuple[str, str, str]]:
    if isinstance(value, dict):
        if {"entityType", "from", "to"} <= value.keys() or {"type", "from", "to"} <= value.keys():
            yield str(value.get("entityType", value.get("type"))), str(value["from"]), str(value["to"])
        elif {"entityType", "fromEntityId", "toEntityId"} <= value.keys():
            yield str(value["entityType"]), str(value["fromEntityId"]), str(value["toEntityId"])
        else:
            for entity_type, mapping in value.items():
                if isinstance(mapping, dict):
                    for old_id, new_id in mapping.items():
                        yield str(entity_type), str(old_id), str(new_id)
    elif isinstance(value, list):
        for item in value:
            yield from _remap_entries(item)


def _resolve_reference(target_types: tuple[str, ...], raw: Any, remaps: dict[tuple[str, str], str], producers: dict[tuple[str, str], str], existing: dict[str, set[str]]) -> tuple[str, str | None, str | None]:
    raw_id = str(raw or "").strip()
    for target_type in target_types:
        target_id = _remap_id(target_type, raw_id, remaps)
        producer_id = producers.get((target_type, target_id))
        if producer_id:
            return target_id, target_type, producer_id
        if target_id in existing.get(target_type, set()):
            return target_id, target_type, None
    return _remap_id(target_types[0], raw_id, remaps), None, None


def _ordered_proposal_ids(proposals: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    adjacency = {proposal_id: set() for proposal_id in proposals}
    for edge in edges:
        adjacency[edge["fromProposalId"]].add(edge["toProposalId"])
    components = _tarjan(adjacency)
    component_by_node = {node: index for index, component in enumerate(components) for node in component}
    errors: list[dict[str, Any]] = []
    required_graph = {proposal_id: set() for proposal_id in proposals}
    for edge in edges:
        if edge["required"]:
            required_graph[edge["fromProposalId"]].add(edge["toProposalId"])
    for component in _tarjan(required_graph):
        cyclic = len(component) > 1 or any(node in required_graph[node] for node in component)
        if cyclic:
            errors.append(_error("required_structural_cycle", proposal_ids=sorted(component)))
    dependencies = {index: set() for index in range(len(components))}
    for source, targets in adjacency.items():
        for target in targets:
            left, right = component_by_node[source], component_by_node[target]
            if left != right:
                dependencies[left].add(right)
    remaining, component_order = set(dependencies), []
    while remaining:
        ready = sorted((index for index in remaining if not (dependencies[index] & remaining)), key=lambda index: tuple(components[index]))
        index = ready[0]
        remaining.remove(index)
        component_order.append(index)
    return [node for index in component_order for node in sorted(components[index])], errors


def _tarjan(graph: dict[str, set[str]]) -> list[list[str]]:
    index, indexes, lowlinks, stack, on_stack, components = 0, {}, {}, [], set(), []
    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = lowlinks[node] = index
        index += 1
        stack.append(node); on_stack.add(node)
        for target in sorted(graph[node]):
            if target not in indexes:
                visit(target); lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] == indexes[node]:
            component = []
            while True:
                target = stack.pop(); on_stack.remove(target); component.append(target)
                if target == node:
                    break
            components.append(sorted(component))
    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return components


def _belongs_to_import_run(proposal: dict[str, Any], import_run_id: str) -> bool:
    source_workflow = str(proposal.get("source_workflow") or proposal.get("sourceWorkflow") or "")
    if source_workflow != "W1_import" and proposal.get("source") != "import":
        return False
    explicit_run_id = str(
        proposal.get("importRunId")
        or proposal.get("import_run_id")
        or proposal.get("packageId")
        or ""
    )
    if explicit_run_id:
        return explicit_run_id == import_run_id
    operation_run_ids = {
        str((operation.get("fields") or {}).get("importRunId") or (operation.get("fields") or {}).get("import_run_id") or "")
        for operation in _operations(proposal)
    }
    operation_run_ids.discard("")
    return operation_run_ids == {import_run_id}


def _artifact_metadata(compilation: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        key: compilation[key]
        for key in (
            "importRunId", "atomic", "inboxUpdated", "packageRemoved",
            "orderedProposalIds", "executionPlan", "edges", "producers", "remaps",
            "droppedRefs", "diagnostics", "blockingErrors",
        )
    }
    metadata["contractVersion"] = compilation["contractVersion"]
    return metadata


def _producer_key(proposal: dict[str, Any], operation: dict[str, Any]) -> tuple[tuple[str, str] | None, list[str]]:
    """Use the same producer-ID precedence as the frontend acceptance path."""
    fields = operation.get("fields") if isinstance(operation.get("fields"), dict) else {}
    candidates = [operation.get("entityId"), fields.get("id"), proposal.get("targetEntityId")]
    explicit_ids: list[str] = []
    for value in candidates:
        value = str(value or "").strip()
        if value and value not in explicit_ids:
            explicit_ids.append(value)
    selected = next((value for value in candidates if str(value or "").strip()), "")
    return _entity_key(operation.get("entityType"), selected), explicit_ids


def _normalize_existing_ids(existing_ids: dict[str, Iterable[str]] | None) -> dict[str, set[str]]:
    return {_normalize_type(entity_type): {str(entity_id).strip() for entity_id in ids if str(entity_id).strip()} for entity_type, ids in (existing_ids or {}).items()}


def _get_path(fields: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = fields
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_path(fields: dict[str, Any], path: str, value: Any) -> None:
    current = fields
    parts = path.split(".")
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def _operations(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [operation for operation in proposal.get("operations", []) if isinstance(operation, dict)]


def _proposal_id(proposal: dict[str, Any], index: int) -> str:
    return str(proposal.get("id") or f"proposal_{index:06d}")


def _proposal_key(proposal: dict[str, Any]) -> tuple[str, str]:
    return str(proposal.get("id") or ""), _stable_value(proposal)


def _entity_key(entity_type: Any, entity_id: Any) -> tuple[str, str] | None:
    normalized_type, normalized_id = _normalize_type(entity_type), str(entity_id or "").strip()
    return (normalized_type, normalized_id) if normalized_type and normalized_id else None


def _normalize_type(value: Any) -> str:
    entity_type = str(value or "").strip()
    return _TYPE_ALIASES.get(entity_type, entity_type)


def _remap_id(entity_type: str, value: Any, remaps: dict[tuple[str, str], str]) -> str:
    current, seen = str(value or "").strip(), set()
    while current and current not in seen and (entity_type, current) in remaps:
        seen.add(current); current = remaps[(entity_type, current)]
    return current


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def _unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def _edge(source: str, target: str, target_type: str, field: str, required: bool) -> dict[str, Any]:
    return {"fromProposalId": source, "toProposalId": target, "targetType": target_type, "field": field, "required": required}


def _unique_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {_stable_value(edge): edge for edge in edges}
    return [unique[key] for key in sorted(unique)]


def _error(code: str, **details: Any) -> dict[str, Any]:
    return {"code": code, **details}


def _public_remaps(remaps: dict[tuple[str, str], str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = defaultdict(dict)
    for (entity_type, old_id), new_id in sorted(remaps.items()):
        result[entity_type][old_id] = new_id
    return dict(result)


def _public_producers(producers: dict[tuple[str, str], str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = defaultdict(dict)
    for (entity_type, entity_id), proposal_id in sorted(producers.items()):
        result[entity_type][entity_id] = proposal_id
    return dict(result)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary_path, path)
    except BaseException:
        Path(temporary_path).unlink(missing_ok=True)
        raise


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
