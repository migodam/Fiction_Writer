"""Durable attempt and checkpoint contracts for W1 imports."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any

from sidecar.workflows import w1_truth


_CHECKPOINT_CONTRACT = "W1Checkpoint/v2"
_LEGACY_BUDGET_DEFAULT = {
    "max_cost_usd": 3.0,
    "fail_on_unknown_pricing": True,
    "fail_on_missing_usage": True,
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{_hash(canonical)[:24]}"


def build_run_identity(
    *, source_text: str, model: str, profile: str, prompt_version: str,
    schema_version: str, tool_version: str, project_digest_hash: str,
) -> dict[str, str]:
    source_hash = _hash(source_text)
    config = {
        "source_hash": source_hash,
        "model": model,
        "profile": profile,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "tool_version": tool_version,
        "project_digest_hash": project_digest_hash,
    }
    return {"lineage_id": _stable_id("lineage", config), "source_hash": source_hash, **config}


def allocate_attempt(project_path: str | Path, identity: dict[str, str], attempt_id: str | None = None) -> dict[str, str]:
    lineage_id = identity["lineage_id"]
    resolved_attempt_id = attempt_id or str(uuid.uuid4())
    if not resolved_attempt_id or any(part in {"", ".", ".."} for part in Path(resolved_attempt_id).parts):
        raise ValueError("Invalid W1 attempt id")
    attempt_dir = Path(project_path) / "system" / "imports" / lineage_id / "attempts" / resolved_attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    return {
        "lineage_id": lineage_id,
        "attempt_id": resolved_attempt_id,
        "attempt_dir": str(attempt_dir),
        "checkpoint_path": str(attempt_dir / "checkpoint.json"),
        "cache_dir": str(Path(project_path) / "system" / "imports" / "cache"),
    }


def cache_key(identity: dict[str, str], source_span: dict[str, Any]) -> str:
    return _stable_id("cache", {
        "source_hash": identity["source_hash"],
        "span_hash": str(source_span.get("substring_hash") or ""),
        "span_start": int(source_span.get("absolute_start", source_span.get("start", 0)) or 0),
        "span_end": int(source_span.get("absolute_end", source_span.get("end", 0)) or 0),
        "model": identity["model"],
        "profile": identity["profile"],
        "prompt_version": identity["prompt_version"],
        "schema_version": identity["schema_version"],
        "tool_version": identity["tool_version"],
        "project_digest_hash": identity["project_digest_hash"],
    })


def build_checkpoint(
    *, identity: dict[str, str], attempt: dict[str, str], total_chunks: int,
    entity_registry: dict, chunk_extractions: list[dict], raw_relationships: list[dict],
    committed_chunk_ids: list[int] | None = None, cross_validation: dict | None = None,
) -> dict[str, Any]:
    truth_receipts = [w1_truth.truth_receipt(item) for item in chunk_extractions]
    committed = w1_truth.committed_chunk_ids(chunk_extractions)
    if committed_chunk_ids is not None and sorted(set(int(chunk_id) for chunk_id in committed_chunk_ids)) != committed:
        raise ValueError("Committed chunk ids must be derived from semantic_complete chunk truth")
    extraction_by_id = {int(item["chunk_id"]): item for item in chunk_extractions}
    committed_extractions = [extraction_by_id[chunk_id] for chunk_id in committed]
    receipts = []
    for chunk_id in committed:
        extraction = extraction_by_id.get(chunk_id, {})
        receipts.append(_chunk_receipt(chunk_id, extraction))
    return {
        "contract": _CHECKPOINT_CONTRACT,
        "source_hash": identity["source_hash"],
        "lineage_id": attempt["lineage_id"],
        "attempt_id": attempt["attempt_id"],
        "config": {key: identity[key] for key in ("model", "profile", "prompt_version", "schema_version", "tool_version", "project_digest_hash")},
        "total_chunks": total_chunks,
        "committed_chunk_ids": committed,
        "committed_chunk_receipts": receipts,
        "chunk_truth_receipts": truth_receipts,
        "failed_chunk_ids": [
            receipt["chunk_id"]
            for receipt in truth_receipts
            if receipt["truth"] in {"failed", "unknown_outcome"}
        ],
        "entity_registry": entity_registry,
        "chunk_extractions": committed_extractions,
        "raw_relationships": raw_relationships,
        "cross_validation": cross_validation or {},
    }


def write_checkpoint_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _recoverable_error(message: str) -> dict[str, Any]:
    return {"status": "recoverable_error", "resume": False, "errors": [message]}


def _chunk_receipt(chunk_id: int, extraction: dict[str, Any]) -> dict[str, Any]:
    source = str(extraction.get("manuscript_content") or extraction.get("source_hash") or "")
    return {
        "chunk_id": chunk_id,
        "chunk_hash": _hash(source),
        "receipt_hash": _hash(json.dumps(extraction, sort_keys=True, ensure_ascii=False, default=str)),
    }


def load_checkpoint(path: str | Path, identity: dict[str, str], attempt: dict[str, str]) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {"status": "missing", "resume": False}
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _recoverable_error(f"Checkpoint is corrupt and was not resumed: {exc}")
    if not isinstance(payload, dict) or payload.get("contract") != _CHECKPOINT_CONTRACT:
        return _recoverable_error("Checkpoint contract is invalid and was not resumed")
    if payload.get("source_hash") != identity["source_hash"]:
        return _recoverable_error("Checkpoint source hash does not match the submitted source")
    if payload.get("lineage_id") != attempt["lineage_id"] or payload.get("attempt_id") != attempt["attempt_id"]:
        return _recoverable_error("Checkpoint lineage or attempt does not match this import")
    expected_config = {key: identity[key] for key in ("model", "profile", "prompt_version", "schema_version", "tool_version", "project_digest_hash")}
    if payload.get("config") != expected_config:
        return _recoverable_error("Checkpoint configuration does not match this import")
    committed = payload.get("committed_chunk_ids")
    receipts = payload.get("committed_chunk_receipts")
    truth_receipts = payload.get("chunk_truth_receipts")
    if not isinstance(committed, list) or committed != list(range(len(committed))) or not isinstance(receipts, list):
        return _recoverable_error("Checkpoint is not committed at a contiguous chunk boundary")
    if not isinstance(truth_receipts, list):
        return _recoverable_error("Checkpoint is missing durable chunk truth receipts")
    try:
        normalized_truth = [
            w1_truth.truth_receipt({
                "chunk_id": receipt.get("chunk_id"),
                "chunk_truth": receipt.get("truth"),
                "domain_receipts": receipt.get("domain_receipts"),
                "failure_codes": receipt.get("failure_codes", []),
            })
            for receipt in truth_receipts
            if isinstance(receipt, dict)
        ]
        truth_by_id = {int(receipt["chunk_id"]): receipt for receipt in normalized_truth}
        if len(truth_by_id) != len(truth_receipts):
            raise ValueError("duplicate or invalid chunk truth receipts")
        expected_committed = []
        while True:
            receipt = truth_by_id.get(len(expected_committed))
            if receipt is None or receipt.get("truth") != "semantic_complete":
                break
            domains = receipt.get("domain_receipts")
            if not isinstance(domains, dict) or any(value not in {"complete", "not_applicable"} for value in domains.values()):
                raise ValueError("semantic-complete receipt has incomplete domains")
            expected_committed.append(len(expected_committed))
    except (TypeError, ValueError) as exc:
        return _recoverable_error(f"Checkpoint chunk truth receipts are invalid: {exc}")
    if committed != expected_committed:
        return _recoverable_error("Checkpoint committed chunks are not the semantic-complete prefix")
    extractions = payload.get("chunk_extractions")
    if not isinstance(extractions, list) or any(not isinstance(item, dict) for item in extractions):
        return _recoverable_error("Checkpoint chunk extractions are invalid")
    extraction_ids = [item.get("chunk_id") for item in extractions]
    if extraction_ids != committed:
        return _recoverable_error("Checkpoint extractions do not match the committed chunk boundary")
    try:
        if any(w1_truth.truth_receipt(item) != truth_by_id.get(int(item["chunk_id"])) for item in extractions):
            return _recoverable_error("Checkpoint committed extractions do not match durable chunk truth")
    except (KeyError, TypeError, ValueError) as exc:
        return _recoverable_error(f"Checkpoint committed extraction truth is invalid: {exc}")
    expected_receipts = [_chunk_receipt(chunk_id, extraction) for chunk_id, extraction in zip(committed, extractions)]
    if receipts != expected_receipts:
        return _recoverable_error("Checkpoint chunk receipt hashes do not match the committed extractions")
    return {
        "status": "ok",
        "resume": True,
        "failed_chunk_ids": payload.get("failed_chunk_ids", []),
        **payload,
    }


def _reconstruct_registry(extractions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {
        "characters": {},
        "events": {},
        "world": {},
        "world_detailed": {},
    }
    for extraction in extractions:
        for character in extraction.get("new_characters", []):
            if not isinstance(character, dict):
                continue
            name = str(character.get("canonical_name") or character.get("name") or "").strip()
            character_id = str(character.get("canonical_id") or character.get("id") or "").strip()
            if name and not character_id:
                character_id = f"legacy_char_{_hash(name)[:12]}"
            if character_id and name:
                registry["characters"][character_id] = dict(character)
        for event in extraction.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or event.get("id") or "").strip()
            if not event_id:
                event_id = f"legacy_event_{_hash(json.dumps(event, sort_keys=True, ensure_ascii=False, default=str))[:12]}"
            registry["events"][event_id] = dict(event)
        for name in extraction.get("world_mentions", []):
            if isinstance(name, str) and name.strip():
                registry["world"][name.strip()] = registry["world"].get(name.strip(), "")
        for world_item in extraction.get("world_mentions_detailed", []):
            if not isinstance(world_item, dict):
                continue
            name = str(world_item.get("name") or "").strip()
            if name:
                registry["world"][name] = str(world_item.get("description") or "")
                registry["world_detailed"][name] = dict(world_item)
    return registry


def _verified_chunk_text(chunk: dict[str, Any], source_text: str, identity: dict[str, str], cursor: int) -> tuple[str, int] | None:
    content = str(chunk.get("manuscript_content") or chunk.get("raw_content") or chunk.get("content") or "")
    span = chunk.get("source_span")
    if isinstance(span, dict) and {"absolute_start", "absolute_end"}.issubset(span):
        start = int(span["absolute_start"])
        end = int(span["absolute_end"])
        if start < 0 or end < start or end > len(source_text):
            return None
        if span.get("raw_source_hash") not in {None, "", identity["source_hash"]}:
            return None
        if source_text[start:end] != content:
            return None
        if span.get("substring_hash") not in {None, "", _hash(content)}:
            return None
        return content, end
    start = source_text.find(content, cursor)
    if not content or start < 0:
        return None
    return content, start + len(content)


def read_legacy_progress(
    path: str | Path,
    identity: dict[str, str],
    *,
    current_source_path: str | Path,
    current_source_text: str,
    current_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read a legacy root checkpoint without consulting scattered artifacts."""
    legacy_path = Path(path)
    if not legacy_path.exists():
        return {"status": "missing"}
    try:
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "ignored", "reason": "legacy checkpoint is corrupt"}
    if not isinstance(payload, dict):
        return {"status": "ignored", "reason": "legacy checkpoint is not an object"}
    try:
        legacy_source = Path(str(payload.get("source_file_path") or "")).resolve(strict=True)
        current_source = Path(current_source_path).resolve(strict=True)
        source_bytes = current_source.read_bytes()
    except (OSError, RuntimeError):
        return {"status": "ignored", "reason": "legacy source path is not readable"}
    if legacy_source != current_source:
        return {"status": "ignored", "reason": "legacy source path does not match the submitted source"}
    if _hash(current_source_text) != identity["source_hash"]:
        return {"status": "ignored", "reason": "submitted source hash does not match the recovery lineage"}
    decoded_file_matches = False
    for encoding in ("utf-8", "gb18030", "gbk", "big5", "shift_jis"):
        try:
            decoded = source_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded == current_source_text and _hash(decoded) == identity["source_hash"]:
            decoded_file_matches = True
            break
    if not decoded_file_matches:
        return {"status": "ignored", "reason": "current source file content does not match the submitted source hash"}
    legacy_hash = payload.get("source_hash")
    if legacy_hash not in {None, "", identity["source_hash"]}:
        return {"status": "ignored", "reason": "legacy source hash does not match the submitted source"}

    raw_extractions = payload.get("chunk_extractions", [])
    if not isinstance(raw_extractions, list):
        return _recoverable_error("Legacy checkpoint extractions are invalid")
    extractions = [item for item in raw_extractions if isinstance(item, dict) and isinstance(item.get("chunk_id"), int)]
    extraction_counts: dict[int, int] = {}
    extraction_by_id: dict[int, dict[str, Any]] = {}
    for extraction in extractions:
        chunk_id = int(extraction["chunk_id"])
        extraction_counts[chunk_id] = extraction_counts.get(chunk_id, 0) + 1
        extraction_by_id[chunk_id] = extraction
    chunk_by_id = {
        int(chunk["chunk_id"]): chunk
        for chunk in current_chunks
        if isinstance(chunk, dict) and isinstance(chunk.get("chunk_id"), int)
    }
    completed = [int(chunk_id) for chunk_id in payload.get("completed_chunk_ids", []) if isinstance(chunk_id, int)]
    completed_set = set(completed)
    trusted: list[int] = []
    trusted_extractions: list[dict[str, Any]] = []
    cursor = 0
    expected_id = 0
    while expected_id in completed_set:
        extraction = extraction_by_id.get(expected_id)
        chunk = chunk_by_id.get(expected_id)
        if extraction is None or chunk is None or extraction_counts.get(expected_id) != 1:
            break
        verified = _verified_chunk_text(chunk, current_source_text, identity, cursor)
        if verified is None:
            break
        current_content, cursor = verified
        extraction_content = str(extraction.get("manuscript_content") or "")
        if extraction_content != current_content or _hash(extraction_content) != _hash(current_content):
            break
        trusted.append(expected_id)
        trusted_extractions.append(extraction)
        expected_id += 1

    ignored = sorted(chunk_id for chunk_id in completed_set if chunk_id not in trusted)
    if completed and not trusted:
        return _recoverable_error("Legacy checkpoint has no verifiable committed chunk boundary")
    extraction_ids = [int(item["chunk_id"]) for item in extractions]
    checkpoint_exact = completed == trusted and extraction_ids == trusted
    registry = payload.get("entity_registry") if checkpoint_exact else None
    if not isinstance(registry, dict):
        registry = _reconstruct_registry(trusted_extractions)
    raw_relationships = payload.get("raw_relationships", []) if checkpoint_exact else None
    if not isinstance(raw_relationships, list):
        raw_relationships = [
            relationship
            for extraction in trusted_extractions
            for relationship in extraction.get("raw_relationships", [])
            if isinstance(relationship, dict)
        ]
    return {
        "status": "ok",
        "committed_chunk_ids": trusted,
        "ignored_chunk_ids": ignored,
        "entity_registry": registry,
        "chunk_extractions": trusted_extractions,
        "raw_relationships": raw_relationships,
        "cross_validation": payload.get("cross_validation", {}) if checkpoint_exact else {},
    }


def discover_legacy_progress(project_path: str | Path) -> dict[str, Any]:
    """Validate enough of a root legacy checkpoint to advertise a single recovery."""
    checkpoint_path = Path(project_path) / "import_progress.json"
    if not checkpoint_path.exists():
        return {"status": "missing"}
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        source_path = Path(str(payload.get("source_file_path") or "")).resolve(strict=True)
        source_text = source_path.read_text(encoding="utf-8")
    except (OSError, RuntimeError, json.JSONDecodeError, UnicodeDecodeError):
        return {"status": "ignored", "reason": "legacy checkpoint or source is unreadable"}
    source_hash = _hash(source_text)
    if payload.get("source_hash") not in {None, "", source_hash}:
        return {"status": "ignored", "reason": "legacy source hash does not match the source file"}
    completed = sorted({item for item in payload.get("completed_chunk_ids", []) if isinstance(item, int) and item >= 0})
    total = int(payload.get("total_chunks", 0) or 0)
    model = str(payload.get("model") or "deepseek-chat")
    profile = str(payload.get("prompt_profile") or payload.get("profile") or "balanced")
    requested_budget = payload.get("budget_config") if isinstance(payload.get("budget_config"), dict) else {}
    budget_config = {**_LEGACY_BUDGET_DEFAULT, **requested_budget}
    requested_max = requested_budget.get("max_cost_usd")
    if isinstance(requested_max, (int, float)) and not isinstance(requested_max, bool):
        budget_config["max_cost_usd"] = min(float(requested_max), _LEGACY_BUDGET_DEFAULT["max_cost_usd"])
    budget_config["fail_on_unknown_pricing"] = True
    budget_config["fail_on_missing_usage"] = True
    identity = build_run_identity(
        source_text=source_text, model=model, profile=profile,
        prompt_version="w1-prompts-v1", schema_version="w1-schema-v1",
        tool_version="w1-tools-v1", project_digest_hash="legacy-root-checkpoint",
    )
    return {
        "status": "ok",
        "lineage_id": identity["lineage_id"],
        "attempt_id": _stable_id("legacy_attempt", {"checkpoint": str(checkpoint_path.resolve()), "lineage_id": identity["lineage_id"]}),
        "config": {
            "project_path": str(Path(project_path).resolve()), "source_file_path": str(source_path),
            "source_hash": source_hash, "model": model, "profile": profile,
            "budget_config": budget_config,
            "legacy_checkpoint_path": str(checkpoint_path), "source_compatible": True,
            "completed_chunks": len(completed), "total_chunks": total,
            "progress": len(completed) / max(total, 1),
            "remaining_cost": {"max_cost_usd": budget_config["max_cost_usd"], "spent_cost_usd": None, "remaining_cost_usd": None, "unknown_spend": True, "remaining_chunks": max(total - len(completed), 0)},
        },
    }
