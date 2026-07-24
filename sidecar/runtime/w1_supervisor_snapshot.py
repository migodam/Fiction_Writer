"""Durable, file-backed snapshots for W1 Supervisor recovery.

This module intentionally has no dependency on ``RuntimeStore`` or the W1
execution graph.  It defines the immutable on-disk contract that a later
adapter can record in checkpoint metadata and safely rehydrate from.

Snapshots only contain an explicit allowlist of Supervisor state.  They never
serialize arbitrary graph state, runtime objects, provider clients, prompts,
or reasoning traces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Callable, Iterable, Mapping, Sequence
from uuid import uuid4


SNAPSHOT_CONTRACT_VERSION = "W1SupervisorSnapshot/v1"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|secret|password|authorization|access[_-]?token|refresh[_-]?token|private[_-]?key)",
    re.I,
)
_UNSAFE_KEY = re.compile(
    r"(?:prompt(?:_body|_text)?|source_(?:body|text|content)|chain_?of_?thought|hidden_?reasoning|reasoning_trace|callback|client|runtime|callable)",
    re.I,
)
# Chunk and extraction implementations historically used these generic keys
# for full source payloads.  Keep this separate from ``_UNSAFE_KEY`` so
# structured summaries, descriptions, and evidence remain durable.
_BODY_CONTENT_KEY = re.compile(
    r"(?:content|text|(?:raw|manuscript|source|chapter|window|input|original|full|body)_?(?:content|text)|(?:content|text)_?(?:raw|manuscript|source|chapter|window|input|original|full|body))"
)
_SECRET_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}\b|\bghp_[A-Za-z0-9]{20,}\b|\bAIza[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._-]{20,}\b)"
)

SUPPORTED_BOUNDARIES = frozenset(
    {
        "validate_file",
        "split_chunks",
        "extract_window",
        "reduce_repair",
        "architect_timeline",
        "qa_review",
        "judge_import",
        "proposal_write",
    }
)

# This is deliberately small.  A resume adapter may expand it only by changing
# this contract and its tests, rather than accidentally persisting a graph
# object or an LLM response object.
STATE_FIELD_ALLOWLIST = frozenset(
    {
        "chunks",
        "prompt_windows",
        "chunk_extractions",
        "entity_registry",
        "relationships",
        "world",
        "timeline",
        "organizer",
        "reducer",
        "cross_validation",
        "reviewer",
        "judge",
        "proposal",
        "operations",
        "import_manifest",
        "project_structure_digest",
    }
)

_SOURCE_FIELDS = frozenset({"source_relative_path", "source_sha256", "source_size", "source_mtime", "project_digest"})
_CONFIG_FIELDS = frozenset(
    {
        "model",
        "prompt_profile",
        "prompt_version",
        "schema_version",
        "tool_registry_version",
        "policy_version",
        "execution_mode",
        "import_mode",
    }
)
_BUDGET_FIELDS = frozenset(
    {
        "budget_limit_usd",
        "spent_usd",
        "reserved_usd",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "call_count",
        "max_steps",
    }
)
_ARTIFACT_REF_FIELDS = frozenset({"relative_path", "sha256", "contract_version", "lineage_id", "attempt_id", "input_hash"})


class W1SupervisorSnapshotError(RuntimeError):
    """Base class for snapshot contract failures."""


class SnapshotValidationError(W1SupervisorSnapshotError):
    """Raised when data cannot safely become a durable snapshot."""


class SnapshotConflictError(W1SupervisorSnapshotError):
    """Raised when a checkpoint ID already represents different content."""


@dataclass(frozen=True)
class SnapshotRef:
    """Compact durable reference suitable for RuntimeStore checkpoint metadata."""

    contract_version: str
    lineage_id: str
    attempt_id: str
    checkpoint_id: str
    relative_path: str
    manifest_sha256: str
    snapshot_sha256: str
    source_identity_sha256: str
    config_identity_sha256: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise SnapshotValidationError(f"{field}_must_be_a_safe_identifier")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SnapshotValidationError(f"{field}_must_be_a_lowercase_sha256")
    return value


def _safe_relative_path(value: Any, field: str = "relative_path") -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SnapshotValidationError(f"{field}_must_be_a_nonempty_relative_path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SnapshotValidationError(f"{field}_must_be_contained")
    normalized = path.as_posix()
    if normalized.startswith("../") or normalized == "..":
        raise SnapshotValidationError(f"{field}_must_be_contained")
    return normalized


def _safe_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or _SECRET_VALUE.search(value):
        raise SnapshotValidationError(f"{field}_must_be_a_safe_nonempty_string")
    return value


def _safe_json(value: Any, field: str) -> Any:
    """Validate JSON-only state while rejecting secret and runtime-like values."""
    if callable(value):
        raise SnapshotValidationError(f"{field}_must_not_contain_callable")
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise SnapshotValidationError(f"{field}_must_not_contain_non_finite_number")
        return value
    if isinstance(value, str):
        if _SECRET_VALUE.search(value):
            raise SnapshotValidationError(f"{field}_must_not_contain_secret")
        if value.startswith("/") or re.match(r"^[A-Za-z]:[\\\\/]", value) or value.startswith("file://"):
            raise SnapshotValidationError(f"{field}_must_not_contain_absolute_path")
        return value
    if isinstance(value, Path):
        raise SnapshotValidationError(f"{field}_must_not_contain_path_object")
    if isinstance(value, list):
        return [_safe_json(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return [_safe_json(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SnapshotValidationError(f"{field}_must_not_contain_non_string_key")
            if _BODY_CONTENT_KEY.fullmatch(key.casefold()):
                raise SnapshotValidationError(f"{field}_must_not_contain_source_body_key")
            if _SECRET_KEY.search(key) or _UNSAFE_KEY.search(key):
                raise SnapshotValidationError(f"{field}_must_not_contain_{key}")
            normalized[key] = _safe_json(item, f"{field}.{key}")
        return normalized
    raise SnapshotValidationError(f"{field}_must_be_json_serializable")


def _normalize_identity(value: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotValidationError(f"{kind}_identity_must_be_an_object")
    allowed = _SOURCE_FIELDS if kind == "source" else _CONFIG_FIELDS
    extra = set(value) - allowed
    if extra:
        raise SnapshotValidationError(f"{kind}_identity_has_unsupported_fields")
    normalized: dict[str, Any] = {}
    if kind == "source":
        if "source_relative_path" not in value or "source_sha256" not in value:
            raise SnapshotValidationError("source_identity_requires_path_and_hash")
        normalized["source_relative_path"] = _safe_relative_path(value["source_relative_path"], "source_relative_path")
        normalized["source_sha256"] = _require_sha256(value["source_sha256"], "source_sha256")
        if "source_size" in value:
            size = value["source_size"]
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise SnapshotValidationError("source_size_must_be_a_nonnegative_integer")
            normalized["source_size"] = size
        if "source_mtime" in value:
            mtime = value["source_mtime"]
            if not isinstance(mtime, (int, float)) or isinstance(mtime, bool) or not math.isfinite(mtime):
                raise SnapshotValidationError("source_mtime_must_be_a_number")
            normalized["source_mtime"] = mtime
        if "project_digest" in value:
            normalized["project_digest"] = _require_sha256(value["project_digest"], "project_digest")
    else:
        required = {"model", "prompt_profile", "prompt_version", "schema_version", "tool_registry_version", "policy_version", "execution_mode", "import_mode"}
        if missing := required - set(value):
            raise SnapshotValidationError(f"config_identity_missing_{'_'.join(sorted(missing))}")
        for key in sorted(required):
            normalized[key] = _safe_string(value[key], key)
    return normalized


def _normalize_artifact_ref(value: Mapping[str, Any] | None, field: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SnapshotValidationError(f"{field}_must_be_an_object")
    extra = set(value) - _ARTIFACT_REF_FIELDS
    if extra:
        raise SnapshotValidationError(f"{field}_has_unsupported_fields")
    required = {"relative_path", "sha256", "contract_version", "lineage_id", "attempt_id"}
    if missing := required - set(value):
        raise SnapshotValidationError(f"{field}_missing_{'_'.join(sorted(missing))}")
    normalized = {
        "relative_path": _safe_relative_path(value["relative_path"], f"{field}.relative_path"),
        "sha256": _require_sha256(value["sha256"], f"{field}.sha256"),
        "contract_version": _safe_string(value["contract_version"], f"{field}.contract_version"),
        "lineage_id": _require_id(value["lineage_id"], f"{field}.lineage_id"),
        "attempt_id": _require_id(value["attempt_id"], f"{field}.attempt_id"),
    }
    if "input_hash" in value:
        normalized["input_hash"] = _require_sha256(value["input_hash"], f"{field}.input_hash")
    return normalized


def _normalize_budget(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) - _BUDGET_FIELDS:
        raise SnapshotValidationError("budget_snapshot_has_unsupported_fields")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item) or item < 0:
            raise SnapshotValidationError(f"budget_snapshot.{key}_must_be_nonnegative_number")
        if key in {"call_count", "max_steps", "input_tokens", "output_tokens", "total_tokens"} and (
            not isinstance(item, int) or isinstance(item, bool)
        ):
            raise SnapshotValidationError(f"budget_snapshot.{key}_must_be_a_nonnegative_integer")
        normalized[key] = item
    if {"spent_usd", "reserved_usd", "budget_limit_usd"}.issubset(normalized) and (
        normalized["spent_usd"] + normalized["reserved_usd"] > normalized["budget_limit_usd"]
    ):
        raise SnapshotValidationError("budget_snapshot_spent_and_reserved_exceed_limit")
    if {"input_tokens", "output_tokens", "total_tokens"}.issubset(normalized) and (
        normalized["input_tokens"] + normalized["output_tokens"] != normalized["total_tokens"]
    ):
        raise SnapshotValidationError("budget_snapshot_token_total_mismatch")
    if {"call_count", "max_steps"}.issubset(normalized) and normalized["call_count"] > normalized["max_steps"]:
        raise SnapshotValidationError("budget_snapshot_call_count_exceeds_max_steps")
    return normalized


def _normalize_state(state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise SnapshotValidationError("state_must_be_an_object")
    unknown = set(state) - STATE_FIELD_ALLOWLIST
    if unknown:
        raise SnapshotValidationError(f"state_has_unsupported_fields:{','.join(sorted(map(str, unknown)))}")
    return {key: _safe_json(state[key], f"state.{key}") for key in sorted(state)}


def _state_refs(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Create immutable references without embedding the state in metadata."""
    return {
        field: {
            "relative_path": f"state/{field}.json",
            "sha256": _sha256(_canonical_bytes(value)),
            "size": len(_canonical_bytes(value)),
            "contract_version": "W1SupervisorSnapshotState/v1",
        }
        for field, value in state.items()
    }


def _normalize_ids(values: Iterable[Any], field: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise SnapshotValidationError(f"{field}_must_be_a_sequence")
    normalized = [_require_id(value, field) for value in values]
    if len(set(normalized)) != len(normalized):
        raise SnapshotValidationError(f"{field}_must_not_contain_duplicates")
    return normalized


def _normalize_repeat_counts(value: Mapping[str, Any] | None) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SnapshotValidationError("repeatable_node_counts_must_be_an_object")
    normalized: dict[str, int] = {}
    for key, item in value.items():
        node = _require_id(key, "repeatable_node_counts.node")
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise SnapshotValidationError("repeatable_node_counts_values_must_be_nonnegative_integers")
        normalized[node] = item
    return normalized


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise SnapshotValidationError("snapshot_directory_is_not_safe")
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            # A competing writer may have published the parent while this
            # worker was traversing it.  Re-validate rather than trusting it.
            if directory.is_symlink() or not directory.is_dir():
                raise SnapshotValidationError("snapshot_directory_is_not_safe")
        _fsync_directory(directory)
        _fsync_directory(directory.parent)
    if path.is_symlink() or not path.is_dir():
        raise SnapshotValidationError("snapshot_directory_is_not_safe")
    _fsync_directory(path)


def _assert_no_symlink(project_root: Path, target: Path) -> None:
    root = project_root.resolve(strict=True)
    if project_root.is_symlink():
        raise SnapshotValidationError("project_root_must_not_be_a_symlink")
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise SnapshotValidationError("snapshot_path_outside_project") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.exists() and current.is_symlink():
            raise SnapshotValidationError("snapshot_path_must_not_contain_symlink")


def _read_regular_file_no_follow(project_root: Path, target: Path, *, error_prefix: str) -> bytes:
    """Read a project-contained regular file while narrowing symlink TOCTOU windows.

    ``O_NOFOLLOW`` is available on supported macOS/Linux deployments.  The
    pre-open lstat/fstat inode comparison catches a final-path substitution
    between validation and open; parent components are still re-checked before
    every open because portable Python has no complete openat traversal API.
    """
    _assert_no_symlink(project_root, target)
    try:
        before = os.lstat(target)
    except OSError as exc:
        raise SnapshotValidationError(f"{error_prefix}_missing") from exc
    if not os.path.isfile(target) or os.path.islink(target):
        raise SnapshotValidationError(f"{error_prefix}_must_be_a_regular_file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise SnapshotValidationError(f"{error_prefix}_cannot_be_opened_safely") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise SnapshotValidationError(f"{error_prefix}_changed_during_open")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_artifact_ref_for_resume(
    project_root: Path,
    snapshot_directory: Path,
    reference: Mapping[str, str] | None,
    field: str,
    receipt_validator: Callable[[Mapping[str, str], Mapping[str, Any]], bool] | None,
    snapshot: Mapping[str, Any],
) -> None:
    if reference is None:
        return
    relative_path = _safe_relative_path(reference["relative_path"], f"{field}.relative_path")
    target = project_root / relative_path
    try:
        target.relative_to(snapshot_directory)
    except ValueError:
        pass
    else:
        raise SnapshotValidationError(f"{field}_must_not_reference_snapshot_contents")
    data = _read_regular_file_no_follow(project_root, target, error_prefix=field)
    if _sha256(data) != reference["sha256"]:
        raise SnapshotValidationError(f"{field}_hash_mismatch")
    if receipt_validator is not None:
        try:
            accepted = receipt_validator(reference, snapshot)
        except Exception as exc:
            raise SnapshotValidationError(f"{field}_receipt_validation_failed") from exc
        if accepted is not True:
            raise SnapshotValidationError(f"{field}_receipt_validation_rejected")


def _validate_resume_source(project_root: Path, expected_source_identity: Mapping[str, Any]) -> dict[str, Any]:
    expected = _normalize_identity(expected_source_identity, kind="source")
    source_path = project_root / expected["source_relative_path"]
    data = _read_regular_file_no_follow(project_root, source_path, error_prefix="resume_source")
    if _sha256(data) != expected["source_sha256"]:
        raise SnapshotValidationError("resume_source_hash_mismatch")
    if "source_size" in expected and len(data) != expected["source_size"]:
        raise SnapshotValidationError("resume_source_size_mismatch")
    if "source_mtime" in expected:
        try:
            current_mtime = source_path.stat().st_mtime
        except OSError as exc:
            raise SnapshotValidationError("resume_source_missing") from exc
        if not math.isclose(current_mtime, expected["source_mtime"], rel_tol=0.0, abs_tol=1e-6):
            raise SnapshotValidationError("resume_source_mtime_mismatch")
    return expected


def _write_json(path: Path, value: Any) -> tuple[str, int]:
    data = _canonical_bytes(value)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return _sha256(data), len(data)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError("snapshot_json_is_invalid") from exc


def _decode_json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError("snapshot_json_is_invalid") from exc


def _invoke_failpoint(failpoint: Callable[[str], None] | None, name: str) -> None:
    if failpoint is not None:
        failpoint(name)


def _snapshot_relative_path(lineage_id: str, attempt_id: str, checkpoint_id: str) -> str:
    return f"system/imports/{lineage_id}/attempts/{attempt_id}/snapshots/{checkpoint_id}"


def _build_snapshot(
    *, lineage_id: str, attempt_id: str, checkpoint_id: str, node: str, next_node: str | None,
    parent_checkpoint_id: str | None, completed_nodes: Sequence[str], completed_window_ids: Sequence[str],
    repeatable_node_counts: Mapping[str, Any] | None, source_identity: Mapping[str, Any],
    config_identity: Mapping[str, Any], state: Mapping[str, Any], budget_snapshot: Mapping[str, Any] | None,
    usage_ledger_ref: Mapping[str, Any] | None, unknown_tool_call_ids: Sequence[str],
    semantic_coverage_ref: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lineage_id = _require_id(lineage_id, "lineage_id")
    attempt_id = _require_id(attempt_id, "attempt_id")
    checkpoint_id = _require_id(checkpoint_id, "checkpoint_id")
    node = _require_id(node, "node")
    if node not in SUPPORTED_BOUNDARIES:
        raise SnapshotValidationError("node_is_not_a_supported_supervisor_boundary")
    if next_node is not None:
        next_node = _require_id(next_node, "next_node")
        if next_node not in SUPPORTED_BOUNDARIES:
            raise SnapshotValidationError("next_node_is_not_a_supported_supervisor_boundary")
    if parent_checkpoint_id is not None:
        parent_checkpoint_id = _require_id(parent_checkpoint_id, "parent_checkpoint_id")

    normalized_source = _normalize_identity(source_identity, kind="source")
    normalized_config = _normalize_identity(config_identity, kind="config")
    normalized_state = _normalize_state(state)
    normalized_usage = _normalize_artifact_ref(usage_ledger_ref, "usage_ledger_ref")
    normalized_semantic = _normalize_artifact_ref(semantic_coverage_ref, "semantic_coverage_ref")
    for field, ref in (("usage_ledger_ref", normalized_usage), ("semantic_coverage_ref", normalized_semantic)):
        if ref is not None and (ref["lineage_id"] != lineage_id or ref["attempt_id"] != attempt_id):
            raise SnapshotValidationError(f"{field}_does_not_belong_to_snapshot_attempt")

    source_hash = _sha256(_canonical_bytes(normalized_source))
    config_hash = _sha256(_canonical_bytes(normalized_config))
    snapshot: dict[str, Any] = {
        "contract_version": SNAPSHOT_CONTRACT_VERSION,
        "lineage_id": lineage_id,
        "attempt_id": attempt_id,
        "checkpoint_id": checkpoint_id,
        "parent_checkpoint_id": parent_checkpoint_id,
        "node": node,
        "next_node": next_node,
        "completed_nodes": _normalize_ids(completed_nodes, "completed_nodes"),
        "completed_window_ids": _normalize_ids(completed_window_ids, "completed_window_ids"),
        "repeatable_node_counts": _normalize_repeat_counts(repeatable_node_counts),
        "source_identity": normalized_source,
        "source_identity_sha256": source_hash,
        "config_identity": normalized_config,
        "config_identity_sha256": config_hash,
        "budget_snapshot": _normalize_budget(budget_snapshot),
        "usage_ledger_ref": normalized_usage,
        "unknown_tool_call_ids": _normalize_ids(unknown_tool_call_ids, "unknown_tool_call_ids"),
        "semantic_coverage_ref": normalized_semantic,
        "state_refs": _state_refs(normalized_state),
    }
    return snapshot, normalized_state


def _expected_manifest(snapshot: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    files: dict[str, bytes] = {"snapshot.json": _canonical_bytes(snapshot)}
    for field, value in state.items():
        files[f"state/{field}.json"] = _canonical_bytes(value)
    entries = [
        {"relative_path": relative_path, "sha256": _sha256(data), "size": len(data)}
        for relative_path, data in sorted(files.items())
    ]
    manifest = {
        "contract_version": SNAPSHOT_CONTRACT_VERSION,
        "lineage_id": snapshot["lineage_id"],
        "attempt_id": snapshot["attempt_id"],
        "checkpoint_id": snapshot["checkpoint_id"],
        "source_identity_sha256": snapshot["source_identity_sha256"],
        "config_identity_sha256": snapshot["config_identity_sha256"],
        "files": entries,
    }
    return manifest, files


def _read_and_validate_snapshot(project_root: Path, relative_path: str) -> tuple[dict[str, Any], dict[str, Any], SnapshotRef]:
    root = project_root.resolve(strict=True)
    final = root / _safe_relative_path(relative_path)
    _assert_no_symlink(root, final)
    if not final.is_dir():
        raise SnapshotValidationError("snapshot_directory_does_not_exist")
    manifest_path = final / "manifest.json"
    _assert_no_symlink(root, manifest_path)
    manifest_bytes = _read_regular_file_no_follow(root, manifest_path, error_prefix="snapshot_manifest")
    manifest = _decode_json(manifest_bytes)
    if not isinstance(manifest, Mapping) or manifest.get("contract_version") != SNAPSHOT_CONTRACT_VERSION:
        raise SnapshotValidationError("snapshot_manifest_contract_is_invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SnapshotValidationError("snapshot_manifest_files_are_invalid")
    expected_entries: dict[str, Mapping[str, Any]] = {}
    for entry in files:
        if not isinstance(entry, Mapping):
            raise SnapshotValidationError("snapshot_manifest_entry_is_invalid")
        relative_file = _safe_relative_path(entry.get("relative_path"), "manifest.relative_path")
        if relative_file in expected_entries or relative_file == "manifest.json":
            raise SnapshotValidationError("snapshot_manifest_has_duplicate_or_recursive_file")
        expected_entries[relative_file] = entry
    for relative_file, entry in expected_entries.items():
        file_path = final / relative_file
        _assert_no_symlink(root, file_path)
        data = _read_regular_file_no_follow(root, file_path, error_prefix="snapshot_manifest_file")
        if len(data) != entry.get("size") or _sha256(data) != entry.get("sha256"):
            raise SnapshotValidationError("snapshot_manifest_file_hash_mismatch")
    expected_state_paths = {f"state/{field}.json" for field in STATE_FIELD_ALLOWLIST}
    if not set(expected_entries).issubset({"snapshot.json", *expected_state_paths}):
        raise SnapshotValidationError("snapshot_manifest_contains_unsupported_path")
    snapshot_bytes = _read_regular_file_no_follow(root, final / "snapshot.json", error_prefix="snapshot_payload")
    snapshot = _decode_json(snapshot_bytes)
    if not isinstance(snapshot, Mapping):
        raise SnapshotValidationError("snapshot_payload_is_invalid")
    try:
        rebuilt, state = _build_snapshot(
            lineage_id=snapshot["lineage_id"], attempt_id=snapshot["attempt_id"], checkpoint_id=snapshot["checkpoint_id"],
            node=snapshot["node"], next_node=snapshot.get("next_node"), parent_checkpoint_id=snapshot.get("parent_checkpoint_id"),
            completed_nodes=snapshot.get("completed_nodes", []), completed_window_ids=snapshot.get("completed_window_ids", []),
            repeatable_node_counts=snapshot.get("repeatable_node_counts"), source_identity=snapshot["source_identity"],
            config_identity=snapshot["config_identity"], state={
                path.removeprefix("state/").removesuffix(".json"): _decode_json(
                    _read_regular_file_no_follow(root, final / path, error_prefix="snapshot_state")
                )
                for path in expected_entries if path.startswith("state/")
            }, budget_snapshot=snapshot.get("budget_snapshot"), usage_ledger_ref=snapshot.get("usage_ledger_ref"),
            unknown_tool_call_ids=snapshot.get("unknown_tool_call_ids", []), semantic_coverage_ref=snapshot.get("semantic_coverage_ref"),
        )
    except (KeyError, TypeError) as exc:
        raise SnapshotValidationError("snapshot_payload_missing_required_field") from exc
    if rebuilt != snapshot:
        raise SnapshotValidationError("snapshot_payload_is_not_canonical")
    state_refs = snapshot.get("state_refs")
    if not isinstance(state_refs, Mapping) or set(state_refs) != set(state):
        raise SnapshotValidationError("snapshot_state_refs_are_invalid")
    for field, value in state_refs.items():
        if value != {
            "relative_path": f"state/{field}.json",
            "sha256": _sha256(_canonical_bytes(state[field])),
            "size": len(_canonical_bytes(state[field])),
            "contract_version": "W1SupervisorSnapshotState/v1",
        }:
            raise SnapshotValidationError("snapshot_state_ref_mismatch")
    expected_manifest, _ = _expected_manifest(rebuilt, state)
    if expected_manifest != manifest:
        raise SnapshotValidationError("snapshot_manifest_identity_mismatch")
    manifest_sha = _sha256(manifest_bytes)
    ref = SnapshotRef(
        contract_version=SNAPSHOT_CONTRACT_VERSION,
        lineage_id=rebuilt["lineage_id"],
        attempt_id=rebuilt["attempt_id"],
        checkpoint_id=rebuilt["checkpoint_id"],
        relative_path=_safe_relative_path(relative_path),
        manifest_sha256=manifest_sha,
        snapshot_sha256=_sha256(snapshot_bytes),
        source_identity_sha256=rebuilt["source_identity_sha256"],
        config_identity_sha256=rebuilt["config_identity_sha256"],
    )
    return rebuilt, state, ref


def write_w1_supervisor_snapshot(
    project_root: str | Path,
    *,
    lineage_id: str,
    attempt_id: str,
    checkpoint_id: str,
    node: str,
    next_node: str | None,
    source_identity: Mapping[str, Any],
    config_identity: Mapping[str, Any],
    state: Mapping[str, Any],
    parent_checkpoint_id: str | None = None,
    completed_nodes: Sequence[str] = (),
    completed_window_ids: Sequence[str] = (),
    repeatable_node_counts: Mapping[str, Any] | None = None,
    budget_snapshot: Mapping[str, Any] | None = None,
    usage_ledger_ref: Mapping[str, Any] | None = None,
    unknown_tool_call_ids: Sequence[str] = (),
    semantic_coverage_ref: Mapping[str, Any] | None = None,
    failpoint: Callable[[str], None] | None = None,
) -> SnapshotRef:
    """Write one immutable W1 supervisor snapshot using a durable directory swap.

    ``failpoint`` is test-only.  It receives bounded lifecycle names such as
    ``after_state:chunks``, ``before_manifest``, ``after_manifest``,
    ``before_rename``, and ``after_rename``.
    """
    root_input = Path(project_root)
    if root_input.is_symlink() or not root_input.exists() or not root_input.is_dir():
        raise SnapshotValidationError("project_root_must_be_an_existing_directory")
    root = root_input.resolve(strict=True)
    snapshot, normalized_state = _build_snapshot(
        lineage_id=lineage_id, attempt_id=attempt_id, checkpoint_id=checkpoint_id, node=node, next_node=next_node,
        parent_checkpoint_id=parent_checkpoint_id, completed_nodes=completed_nodes, completed_window_ids=completed_window_ids,
        repeatable_node_counts=repeatable_node_counts, source_identity=source_identity, config_identity=config_identity,
        state=state, budget_snapshot=budget_snapshot, usage_ledger_ref=usage_ledger_ref,
        unknown_tool_call_ids=unknown_tool_call_ids, semantic_coverage_ref=semantic_coverage_ref,
    )
    relative_path = _snapshot_relative_path(snapshot["lineage_id"], snapshot["attempt_id"], snapshot["checkpoint_id"])
    final = root / relative_path
    snapshots_root = final.parent
    _assert_no_symlink(root, final)
    _ensure_directory(snapshots_root)
    manifest, files = _expected_manifest(snapshot, normalized_state)

    if final.exists():
        _, _, existing_ref = _read_and_validate_snapshot(root, relative_path)
        expected_manifest_sha = _sha256(_canonical_bytes(manifest))
        expected_snapshot_sha = _sha256(files["snapshot.json"])
        if existing_ref.manifest_sha256 == expected_manifest_sha and existing_ref.snapshot_sha256 == expected_snapshot_sha:
            return existing_ref
        raise SnapshotConflictError("checkpoint_id_already_has_different_snapshot_content")

    temporary = snapshots_root / f".{snapshot['checkpoint_id']}.tmp-{uuid4().hex}"
    _assert_no_symlink(root, temporary)
    try:
        temporary.mkdir(mode=0o700)
        _ensure_directory(temporary / "state")
        for relative_file, data in sorted(files.items()):
            if relative_file == "snapshot.json":
                continue
            destination = temporary / relative_file
            _write_json(destination, json.loads(data.decode("utf-8")))
            _invoke_failpoint(failpoint, f"after_state:{Path(relative_file).stem}")
        _write_json(temporary / "snapshot.json", snapshot)
        _invoke_failpoint(failpoint, "after_snapshot")
        _fsync_directory(temporary / "state")
        _fsync_directory(temporary)
        _invoke_failpoint(failpoint, "before_manifest")
        _write_json(temporary / "manifest.json", manifest)
        _fsync_directory(temporary)
        _invoke_failpoint(failpoint, "after_manifest")
        _invoke_failpoint(failpoint, "before_rename")
        try:
            os.rename(temporary, final)
        except OSError:
            # macOS reports a non-empty target directory as errno 66 rather
            # than FileExistsError.  Treat only a now-visible final snapshot
            # as a competing publisher; all other rename failures propagate.
            if not final.exists():
                raise
            _, _, existing_ref = _read_and_validate_snapshot(root, relative_path)
            expected_manifest_sha = _sha256(_canonical_bytes(manifest))
            expected_snapshot_sha = _sha256(files["snapshot.json"])
            if existing_ref.manifest_sha256 != expected_manifest_sha or existing_ref.snapshot_sha256 != expected_snapshot_sha:
                raise SnapshotConflictError("checkpoint_id_already_has_different_snapshot_content")
        _fsync_directory(snapshots_root)
        _invoke_failpoint(failpoint, "after_rename")
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    _, _, ref = _read_and_validate_snapshot(root, relative_path)
    return ref


def load_w1_supervisor_snapshot(
    project_root: str | Path,
    reference: SnapshotRef | Mapping[str, Any],
    *,
    expected_source_identity: Mapping[str, Any] | None = None,
    expected_config_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate a snapshot, including optional resume compatibility."""
    if isinstance(reference, SnapshotRef):
        reference_dict = reference.to_dict()
    elif isinstance(reference, Mapping):
        reference_dict = dict(reference)
    else:
        raise SnapshotValidationError("snapshot_reference_must_be_an_object")
    required = set(SnapshotRef.__dataclass_fields__)
    if set(reference_dict) != required:
        raise SnapshotValidationError("snapshot_reference_has_invalid_fields")
    if reference_dict.get("contract_version") != SNAPSHOT_CONTRACT_VERSION:
        raise SnapshotValidationError("snapshot_reference_contract_is_invalid")
    root_input = Path(project_root)
    if root_input.is_symlink():
        raise SnapshotValidationError("project_root_must_not_be_a_symlink")
    root = root_input.resolve(strict=True)
    snapshot, state, calculated_ref = _read_and_validate_snapshot(root, _safe_relative_path(reference_dict["relative_path"]))
    if calculated_ref.to_dict() != reference_dict:
        raise SnapshotValidationError("snapshot_reference_hash_or_identity_mismatch")
    if expected_source_identity is not None:
        expected = _normalize_identity(expected_source_identity, kind="source")
        if expected != snapshot["source_identity"]:
            raise SnapshotValidationError("snapshot_source_identity_mismatch")
    if expected_config_identity is not None:
        expected = _normalize_identity(expected_config_identity, kind="config")
        if expected != snapshot["config_identity"]:
            raise SnapshotValidationError("snapshot_config_identity_mismatch")
    return {"snapshot": snapshot, "state": state, "reference": calculated_ref.to_dict()}


def load_w1_supervisor_snapshot_for_resume(
    project_root: str | Path,
    reference: SnapshotRef | Mapping[str, Any],
    *,
    expected_source_identity: Mapping[str, Any],
    expected_config_identity: Mapping[str, Any],
    artifact_receipt_validator: Callable[[Mapping[str, str], Mapping[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Load only a snapshot that is safe to resume.

    Unlike :func:`load_w1_supervisor_snapshot`, this API intentionally has no
    optional identity arguments.  It validates the current source file and all
    referenced external artifacts before an adapter can schedule another tool
    call.  RuntimeStore ownership of unknown provider outcomes remains an
    integration-layer responsibility; callers must still block resume while
    ``unknown_tool_call_ids`` is non-empty unless the runtime resolves them.
    """
    root_input = Path(project_root)
    if root_input.is_symlink() or not root_input.exists() or not root_input.is_dir():
        raise SnapshotValidationError("project_root_must_be_an_existing_directory")
    root = root_input.resolve(strict=True)
    expected_source = _validate_resume_source(root, expected_source_identity)
    expected_config = _normalize_identity(expected_config_identity, kind="config")
    loaded = load_w1_supervisor_snapshot(
        root,
        reference,
        expected_source_identity=expected_source,
        expected_config_identity=expected_config,
    )
    snapshot = loaded["snapshot"]
    snapshot_directory = root / loaded["reference"]["relative_path"]
    _assert_no_symlink(root, snapshot_directory)
    _validate_artifact_ref_for_resume(
        root,
        snapshot_directory,
        snapshot.get("usage_ledger_ref"),
        "usage_ledger_ref",
        artifact_receipt_validator,
        snapshot,
    )
    _validate_artifact_ref_for_resume(
        root,
        snapshot_directory,
        snapshot.get("semantic_coverage_ref"),
        "semantic_coverage_ref",
        artifact_receipt_validator,
        snapshot,
    )
    return loaded
