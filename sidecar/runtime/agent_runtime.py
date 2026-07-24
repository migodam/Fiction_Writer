"""SQLite-backed durable state for resumable sidecar agent runs.

The store deliberately owns orchestration metadata only. Workflow state remains
with the graph checkpointer; attempts reference it through ``checkpoint_id``.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Any, Iterator
from uuid import uuid4


class RuntimeStoreError(RuntimeError):
    """Base class for durable runtime errors."""


class LeaseLostError(RuntimeStoreError):
    """Raised when an operation is attempted with an expired/stale lease."""


class SecretValueError(RuntimeStoreError):
    """Raised when a secret is supplied as durable identity metadata."""


_SECRET_KEY = re.compile(r"(?:api[_-]?key|secret|password|authorization|access[_-]?token|refresh[_-]?token|private[_-]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?:\bsk-[A-Za-z0-9_-]{8,}\b|\bghp_[A-Za-z0-9]{20,}\b|\bAIza[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._-]{20,}\b)")
_UNSAFE_MEMORY_KEY = re.compile(r"(?:prompt(?:_body|_text)?|source_(?:body|text|content)|chain_?of_?thought|hidden_?reasoning|reasoning_trace)", re.I)


def _now(value: float | None = None) -> float:
    return time.time() if value is None else value


def _snapshot_artifact_refs_are_valid(project_root: Path, snapshot: dict[str, Any]) -> bool:
    """Fail closed for optional snapshot artifact references until v1 has a resolver.

    Current Supervisor snapshots do not emit these references.  When a future
    producer does, a fork must verify containment, symlink safety, bytes hash,
    and source-attempt provenance before it can become resumable.
    """
    root = project_root.resolve(strict=True)
    expected_attempt_id = str(snapshot.get("attempt_id") or "")
    for key in ("usage_ledger_ref", "semantic_coverage_ref"):
        reference = snapshot.get(key)
        if reference is None:
            continue
        if not isinstance(reference, dict) or reference.get("attempt_id") != expected_attempt_id:
            return False
        relative_path = reference.get("relative_path")
        checksum = reference.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(checksum, str) or len(checksum) != 64:
            return False
        candidate = root / relative_path
        try:
            candidate.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            return False
        cursor = root
        for part in Path(relative_path).parts:
            if part in {"", ".", ".."}:
                return False
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != checksum:
            return False
    return True


def _identifier(value: str | None, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if _SECRET_VALUE.search(value):
        raise SecretValueError(f"{field} must not contain a secret")
    return value


def redact_secrets(value: Any) -> Any:
    """Return a JSON-safe value with credential-like fields and values removed."""
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        return "[REDACTED]"
    return value


def _contains_unsafe_memory(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_UNSAFE_MEMORY_KEY.search(str(key)) or _contains_unsafe_memory(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_unsafe_memory(item) for item in value)
    return False


def _dump(value: Any) -> str:
    return json.dumps(redact_secrets(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe_unknown_reason(reason: Any) -> str:
    normalized = str(reason or "").strip().lower().replace(" ", "_")
    if normalized == "ambiguous_transport":
        return normalized
    if normalized in {"restart", "sidecar_restarted", "runtime_interrupted"}:
        return "runtime_interrupted"
    return "transport_outcome_unknown"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key in tuple(item):
        if key.endswith("_json") and item[key] is not None:
            item[key.removesuffix("_json")] = json.loads(item.pop(key))
    return item


def _event_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Normalize both pre-v6 and v6 rows without changing legacy event shape."""
    item = _row(row)
    if item is None:
        return None
    item["contract_version"] = item.get("contract_version") or "legacy/v0"
    if item.get("actor") is None:
        item["actor"] = {"kind": "system", "id": "legacy"}
    return item


class RuntimeStore:
    """Per-project SQLite WAL store for durable agent execution metadata."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.database_path = self.project_root / "system" / "runtime" / "agent_runtime.db"
        self._initialize_lock = threading.Lock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        last_error: sqlite3.OperationalError | None = None
        for _ in range(20):
            connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=5000")
                return connection
            except sqlite3.OperationalError as exc:
                connection.close()
                last_error = exc
                if "locked" not in str(exc).lower():
                    raise
                time.sleep(0.05)
        assert last_error is not None
        raise last_error

    def initialize(self) -> None:
        with self._initialize_lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)")
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 1").fetchone() is None:
                    statements = (
                        """CREATE TABLE IF NOT EXISTS agent_runs (
                          run_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, lineage_id TEXT NOT NULL,
                          thread_id TEXT, cache_key TEXT, status TEXT NOT NULL DEFAULT 'running',
                          created_at REAL NOT NULL, updated_at REAL NOT NULL
                        )""",
                        """CREATE TABLE IF NOT EXISTS agent_attempts (
                          attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
                          attempt_number INTEGER NOT NULL, checkpoint_id TEXT, status TEXT NOT NULL DEFAULT 'running',
                          created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(run_id, attempt_number)
                        )""",
                        """CREATE TABLE IF NOT EXISTS run_leases (
                          attempt_id TEXT PRIMARY KEY REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          owner_id TEXT NOT NULL, fence_token INTEGER NOT NULL, heartbeat_at REAL NOT NULL, expires_at REAL NOT NULL
                        )""",
                        """CREATE TABLE IF NOT EXISTS run_events (
                          event_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          sequence INTEGER NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL,
                          UNIQUE(attempt_id, sequence)
                        )""",
                        """CREATE TABLE IF NOT EXISTS tool_calls (
                          tool_call_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          tool_name TEXT NOT NULL, intent_payload_json TEXT NOT NULL, result_payload_json TEXT,
                          status TEXT NOT NULL, unknown_reason TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
                        )""",
                        """CREATE TABLE IF NOT EXISTS artifact_receipts (
                          receipt_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          artifact_type TEXT NOT NULL, artifact_uri TEXT NOT NULL, checksum TEXT, metadata_json TEXT NOT NULL,
                          created_at REAL NOT NULL
                        )""",
                        """CREATE TABLE IF NOT EXISTS human_decisions (
                          decision_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          decision_key TEXT NOT NULL, decision TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL,
                          UNIQUE(attempt_id, decision_key)
                        )""",
                        """CREATE TABLE IF NOT EXISTS outbox (
                          outbox_id TEXT PRIMARY KEY, attempt_id TEXT REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE,
                          topic TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL, delivered_at REAL
                        )""",
                        "CREATE INDEX IF NOT EXISTS run_events_after_sequence ON run_events(attempt_id, sequence)",
                        "CREATE INDEX IF NOT EXISTS recoverable_attempts ON agent_attempts(status, updated_at)",
                    )
                    for statement in statements:
                        connection.execute(statement)
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (1, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 2").fetchone() is None:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")}
                    if "config_json" not in columns:
                        connection.execute("ALTER TABLE agent_runs ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}'")
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (2, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone() is None:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS checkpoint_metadata ("
                        "checkpoint_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE, "
                        "parent_checkpoint_id TEXT, node TEXT NOT NULL, sequence INTEGER NOT NULL, metadata_json TEXT NOT NULL, created_at REAL NOT NULL, "
                        "UNIQUE(attempt_id, sequence))"
                    )
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS resource_leases ("
                        "resource_key TEXT PRIMARY KEY, owner_id TEXT NOT NULL, fence_token INTEGER NOT NULL, "
                        "heartbeat_at REAL NOT NULL, expires_at REAL NOT NULL)"
                    )
                    connection.execute("CREATE INDEX IF NOT EXISTS checkpoint_metadata_by_attempt ON checkpoint_metadata(attempt_id, sequence)")
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (3, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 4").fetchone() is None:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_attempts)")}
                    if "parent_attempt_id" not in columns:
                        connection.execute("ALTER TABLE agent_attempts ADD COLUMN parent_attempt_id TEXT REFERENCES agent_attempts(attempt_id)")
                    if "fork_checkpoint_id" not in columns:
                        connection.execute("ALTER TABLE agent_attempts ADD COLUMN fork_checkpoint_id TEXT")
                    connection.execute("CREATE INDEX IF NOT EXISTS forked_attempts_by_parent ON agent_attempts(parent_attempt_id)")
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (4, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 5").fetchone() is None:
                    statements = (
                        "CREATE TABLE IF NOT EXISTS agent_task_plans (run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id) ON DELETE CASCADE, plan_id TEXT NOT NULL, policy_version TEXT NOT NULL, submitted_at REAL NOT NULL, updated_at REAL NOT NULL)",
                        "CREATE UNIQUE INDEX IF NOT EXISTS agent_task_plans_plan_id ON agent_task_plans(plan_id)",
                        "CREATE TABLE IF NOT EXISTS agent_tasks (run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE, task_id TEXT NOT NULL, title TEXT NOT NULL, dependencies_json TEXT NOT NULL, read_set_json TEXT NOT NULL, write_set_json TEXT NOT NULL, status TEXT NOT NULL, assigned_agent TEXT, claim_owner TEXT, claim_expires_at REAL, fence_map_json TEXT NOT NULL DEFAULT '{}', attempts INTEGER NOT NULL DEFAULT 0, failure_signature TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, completed_at REAL, PRIMARY KEY(run_id, task_id))",
                        "CREATE TABLE IF NOT EXISTS dead_letters (dead_letter_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE, task_id TEXT NOT NULL, reason TEXT NOT NULL, failure_signature TEXT, created_at REAL NOT NULL, recovered_at REAL, UNIQUE(run_id, task_id, reason))",
                        "CREATE TABLE IF NOT EXISTS memory_records (memory_id TEXT PRIMARY KEY, run_id TEXT REFERENCES agent_runs(run_id) ON DELETE SET NULL, layer TEXT NOT NULL, record_type TEXT NOT NULL, content TEXT NOT NULL, reference_json TEXT NOT NULL, provenance TEXT NOT NULL, confidence REAL NOT NULL, policy_version TEXT NOT NULL, expires_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL)",
                        "CREATE INDEX IF NOT EXISTS agent_tasks_claimable ON agent_tasks(run_id, status, updated_at)",
                        "CREATE INDEX IF NOT EXISTS dead_letters_by_run ON dead_letters(run_id, created_at)",
                        "CREATE INDEX IF NOT EXISTS memory_records_expiry ON memory_records(expires_at)",
                    )
                    for statement in statements:
                        connection.execute(statement)
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (5, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 6").fetchone() is None:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(run_events)")}
                    additions = (
                        ("contract_version", "TEXT NOT NULL DEFAULT 'legacy/v0'"),
                        ("actor_json", "TEXT"),
                        ("idempotency_key", "TEXT"),
                        ("causation_id", "TEXT"),
                        ("correlation_id", "TEXT"),
                    )
                    for name, definition in additions:
                        if name not in columns:
                            connection.execute(f"ALTER TABLE run_events ADD COLUMN {name} {definition}")
                    connection.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS run_events_idempotency_key "
                        "ON run_events(attempt_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
                    )
                    connection.execute("CREATE INDEX IF NOT EXISTS run_events_correlation_id ON run_events(attempt_id, correlation_id)")
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (6, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 7").fetchone() is None:
                    # Forks point at an immutable external checkpoint reference.  The
                    # metadata snapshot and copied receipt provenance make the
                    # reference durable without copying or mutating the graph store.
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS attempt_fork_snapshots ("
                        "snapshot_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES agent_attempts(attempt_id) ON DELETE CASCADE, "
                        "parent_attempt_id TEXT NOT NULL REFERENCES agent_attempts(attempt_id) ON DELETE RESTRICT, "
                        "source_checkpoint_id TEXT NOT NULL, checkpoint_sequence INTEGER NOT NULL, "
                        "checkpoint_node TEXT NOT NULL, checkpoint_parent_id TEXT, checkpoint_metadata_json TEXT NOT NULL, "
                        "state_reference_json TEXT NOT NULL, created_at REAL NOT NULL)"
                    )
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS attempt_fork_snapshots_parent "
                        "ON attempt_fork_snapshots(parent_attempt_id, source_checkpoint_id)"
                    )
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (7, ?)", (_now(),))
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = 8").fetchone() is None:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(attempt_fork_snapshots)")}
                    if "resumable" not in columns:
                        connection.execute("ALTER TABLE attempt_fork_snapshots ADD COLUMN resumable INTEGER NOT NULL DEFAULT 0")
                    if "non_resumable_reason" not in columns:
                        connection.execute("ALTER TABLE attempt_fork_snapshots ADD COLUMN non_resumable_reason TEXT")
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (8, ?)", (_now(),))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def pragma(self, name: str) -> Any:
        if name not in {"foreign_keys", "journal_mode", "busy_timeout"}:
            raise ValueError("unsupported pragma")
        with self._connect() as connection:
            return connection.execute(f"PRAGMA {name}").fetchone()[0]

    def create_run(self, *, workflow_id: str, lineage_id: str | None = None, thread_id: str | None = None, cache_key: str | None = None, run_id: str | None = None, config: Any | None = None) -> dict[str, Any]:
        workflow_id = _identifier(workflow_id, "workflow_id", required=True)
        run_id = _identifier(run_id or str(uuid4()), "run_id", required=True)
        lineage_id = _identifier(lineage_id or run_id, "lineage_id", required=True)
        thread_id = _identifier(thread_id, "thread_id")
        cache_key = _identifier(cache_key, "cache_key")
        created_at = _now()
        with self.transaction() as connection:
            connection.execute("INSERT INTO agent_runs(run_id, workflow_id, lineage_id, thread_id, cache_key, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_id, workflow_id, lineage_id, thread_id, cache_key, _dump(config or {}), created_at, created_at))
            return _row(connection.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone())  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _row(connection.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone())

    def get_run_by_lineage(self, lineage_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _row(connection.execute("SELECT * FROM agent_runs WHERE lineage_id = ? ORDER BY created_at LIMIT 1", (lineage_id,)).fetchone())

    def update_run_config(self, run_id: str, config: Any) -> dict[str, Any]:
        with self.transaction() as connection:
            result = connection.execute("UPDATE agent_runs SET config_json = ?, updated_at = ? WHERE run_id = ?", (_dump(config), _now(), run_id))
            if result.rowcount != 1:
                raise KeyError(run_id)
            return _row(connection.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone())  # type: ignore[return-value]

    def create_attempt(self, run_id: str, *, attempt_id: str | None = None, checkpoint_id: str | None = None, parent_attempt_id: str | None = None, fork_checkpoint_id: str | None = None) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id or str(uuid4()), "attempt_id", required=True)
        checkpoint_id = _identifier(checkpoint_id, "checkpoint_id")
        now = _now()
        with self.transaction() as connection:
            number = connection.execute("SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM agent_attempts WHERE run_id = ?", (run_id,)).fetchone()[0]
            connection.execute("INSERT INTO agent_attempts(attempt_id, run_id, attempt_number, checkpoint_id, parent_attempt_id, fork_checkpoint_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (attempt_id, run_id, number, checkpoint_id, parent_attempt_id, fork_checkpoint_id, now, now))
            return _row(connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone())  # type: ignore[return-value]

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _row(connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone())

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM agent_attempts WHERE run_id = ? ORDER BY attempt_number", (run_id,))]  # type: ignore[misc]

    def set_attempt_status(
        self, attempt_id: str, status: str, *, owner_id: str | None = None,
        fence_token: int | None = None,
    ) -> dict[str, Any]:
        if status not in {"running", "interrupted", "waiting_human", "paused", "cancelled", "completed", "failed", "needs_credentials"}:
            raise ValueError("unsupported attempt status")
        with self.transaction() as connection:
            self._assert_optional_lease(connection, attempt_id, owner_id, fence_token)
            result = connection.execute("UPDATE agent_attempts SET status = ?, updated_at = ? WHERE attempt_id = ?", (status, _now(), attempt_id))
            if result.rowcount != 1:
                raise KeyError(attempt_id)
            return _row(connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone())  # type: ignore[return-value]

    def fork_attempt(self, attempt_id: str, *, checkpoint_id: str, decision_id: str) -> dict[str, Any]:
        """Create an idempotent, isolated child snapshot from a parent checkpoint.

        Graph-state blobs remain in the configured checkpointer.  A fork therefore
        records an immutable reference to that checkpoint and freezes the sanitized
        metadata plus explicitly checkpoint-scoped artifact receipts in this store.
        It never treats the parent's unscoped receipts, tool calls, or outbox as work
        the child may resume.
        """
        checkpoint_id = _identifier(checkpoint_id, "checkpoint_id", required=True)
        decision_id = _identifier(decision_id, "decision_id", required=True)
        with self.transaction() as connection:
            parent = connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if parent is None:
                raise KeyError(attempt_id)
            existing = connection.execute("SELECT * FROM human_decisions WHERE attempt_id = ? AND decision_key = ?", (attempt_id, decision_id)).fetchone()
            if existing is not None:
                payload = json.loads(existing["payload_json"])
                child_id = payload.get("child_attempt_id")
                if existing["decision"] != "fork" or payload.get("checkpoint_id") != checkpoint_id:
                    raise ValueError("fork_decision_conflict")
                child = _row(connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (child_id,)).fetchone())
                if child is None:
                    raise RuntimeStoreError("fork decision references a missing child attempt")
                return {"attempt": child, "idempotent": True}
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint_metadata WHERE checkpoint_id = ? AND attempt_id = ?",
                (checkpoint_id, attempt_id),
            ).fetchone()
            if checkpoint is None:
                raise ValueError("checkpoint_does_not_belong_to_parent_attempt")
            child_id = str(uuid4())
            snapshot_id = str(uuid4())
            now = _now()
            number = connection.execute("SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM agent_attempts WHERE run_id = ?", (parent["run_id"],)).fetchone()[0]
            connection.execute(
                "INSERT INTO agent_attempts(attempt_id, run_id, attempt_number, checkpoint_id, parent_attempt_id, fork_checkpoint_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'paused', ?, ?)",
                (child_id, parent["run_id"], number, checkpoint_id, attempt_id, checkpoint_id, now, now),
            )
            checkpoint_metadata = json.loads(checkpoint["metadata_json"])
            run = connection.execute("SELECT workflow_id, lineage_id, thread_id FROM agent_runs WHERE run_id = ?", (parent["run_id"],)).fetchone()
            assert run is not None
            snapshot_ref = checkpoint_metadata.get("snapshot_ref") if isinstance(checkpoint_metadata, dict) else None
            resumable = False
            non_resumable_reason = "fork_snapshot_not_resumable"
            state_reference: dict[str, Any]
            if run["workflow_id"] == "W1" and checkpoint_metadata.get("recovery_mode") == "resumable" and isinstance(snapshot_ref, dict):
                try:
                    from sidecar.runtime.w1_supervisor_snapshot import load_w1_supervisor_snapshot

                    loaded = load_w1_supervisor_snapshot(self.project_root, snapshot_ref)
                    snapshot = loaded["snapshot"]
                    actual_unknown = [
                        row[0]
                        for row in connection.execute(
                            "SELECT tool_call_id FROM tool_calls WHERE attempt_id = ? AND status = 'unknown_outcome' ORDER BY tool_call_id",
                            (attempt_id,),
                        )
                    ]
                    declared_unknown = sorted(str(item) for item in snapshot.get("unknown_tool_call_ids", []))
                    if (
                        snapshot.get("lineage_id") != run["lineage_id"]
                        or snapshot.get("attempt_id") != attempt_id
                        or snapshot.get("checkpoint_id") != checkpoint_id
                    ):
                        non_resumable_reason = "fork_snapshot_provenance_mismatch"
                    elif actual_unknown != declared_unknown:
                        non_resumable_reason = "fork_snapshot_unknown_tool_calls_mismatch"
                    elif actual_unknown:
                        non_resumable_reason = "fork_snapshot_unknown_tool_calls_present"
                    elif not _snapshot_artifact_refs_are_valid(self.project_root, snapshot):
                        non_resumable_reason = "fork_snapshot_artifact_reference_invalid"
                    else:
                        resumable = True
                        non_resumable_reason = ""
                    state_reference = {
                        "kind": "w1_supervisor_snapshot/v1",
                        "workflow_id": run["workflow_id"],
                        "lineage_id": run["lineage_id"],
                        "source_attempt_id": attempt_id,
                        "checkpoint_id": checkpoint_id,
                        "snapshot_ref": loaded["reference"],
                        "immutable": True,
                        "mode": "resumable" if resumable else "preview_only",
                        "resumable": resumable,
                    }
                except Exception:
                    non_resumable_reason = "fork_snapshot_validation_failed"
                    state_reference = {
                        "kind": "external_checkpoint_reference/v1",
                        "workflow_id": run["workflow_id"],
                        "lineage_id": run["lineage_id"],
                        "thread_id": run["thread_id"],
                        "checkpoint_id": checkpoint_id,
                        "immutable": True,
                        "mode": "preview_only",
                        "resumable": False,
                    }
            else:
                state_reference = {
                    "kind": "external_checkpoint_reference/v1",
                    "workflow_id": run["workflow_id"],
                    "lineage_id": run["lineage_id"],
                    "thread_id": run["thread_id"],
                    "checkpoint_id": checkpoint_id,
                    "immutable": True,
                    "mode": "preview_only",
                    "resumable": False,
                }

            connection.execute(
                "INSERT INTO attempt_fork_snapshots("
                "snapshot_id, attempt_id, parent_attempt_id, source_checkpoint_id, checkpoint_sequence, "
                "checkpoint_node, checkpoint_parent_id, checkpoint_metadata_json, state_reference_json, resumable, non_resumable_reason, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id, child_id, attempt_id, checkpoint_id, checkpoint["sequence"],
                    checkpoint["node"], checkpoint["parent_checkpoint_id"], _dump(checkpoint_metadata),
                    _dump(state_reference), 1 if resumable else 0, non_resumable_reason or None, now,
                ),
            )
            self._copy_checkpoint_scoped_receipts(
                connection, parent_attempt_id=attempt_id, child_attempt_id=child_id,
                checkpoint_id=checkpoint_id, checkpoint_sequence=int(checkpoint["sequence"]),
                snapshot_id=snapshot_id, timestamp=now,
            )
            payload = {
                "checkpoint_id": checkpoint_id,
                "child_attempt_id": child_id,
                "snapshot_id": snapshot_id,
            }
            connection.execute(
                "INSERT INTO human_decisions(decision_id, attempt_id, decision_key, decision, payload_json, created_at) VALUES (?, ?, ?, 'fork', ?, ?)",
                (str(uuid4()), attempt_id, decision_id, _dump(payload), now),
            )
            self._append_event_in_transaction(
                connection, attempt_id, "fork", payload, timestamp=now,
                contract_version="AgentEvent/v1", actor={"kind": "human", "id": "time_travel"},
                idempotency_key=f"fork:{decision_id}", causation_id=None, correlation_id=snapshot_id,
                event_id=None,
            )
            self._append_event_in_transaction(
                connection, child_id, "fork_snapshot", {
                "snapshot_id": snapshot_id, "parent_attempt_id": attempt_id,
                "checkpoint_id": checkpoint_id,
                "resumable": resumable,
                }, timestamp=now, contract_version="AgentEvent/v1",
                actor={"kind": "system", "id": "runtime_store"},
                idempotency_key="fork_snapshot", causation_id=None, correlation_id=snapshot_id,
                event_id=None,
            )
            child = _row(connection.execute("SELECT * FROM agent_attempts WHERE attempt_id = ?", (child_id,)).fetchone())
            return {"attempt": child, "idempotent": False}  # type: ignore[return-value]

    @staticmethod
    def _receipt_is_checkpoint_scoped(metadata: Any, checkpoint_id: str, checkpoint_sequence: int) -> bool:
        """Receipts without explicit checkpoint scope are deliberately not inherited."""
        if not isinstance(metadata, dict):
            return False
        if metadata.get("checkpoint_id") == checkpoint_id:
            return True
        if metadata.get("source_checkpoint_id") == checkpoint_id:
            return True
        sequence = metadata.get("checkpoint_sequence")
        return isinstance(sequence, int) and not isinstance(sequence, bool) and sequence <= checkpoint_sequence

    def _copy_checkpoint_scoped_receipts(
        self, connection: sqlite3.Connection, *, parent_attempt_id: str, child_attempt_id: str,
        checkpoint_id: str, checkpoint_sequence: int, snapshot_id: str, timestamp: float,
    ) -> None:
        rows = connection.execute(
            "SELECT * FROM artifact_receipts WHERE attempt_id = ? ORDER BY created_at, receipt_id",
            (parent_attempt_id,),
        ).fetchall()
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            if not self._receipt_is_checkpoint_scoped(metadata, checkpoint_id, checkpoint_sequence):
                continue
            child_metadata = {
                "fork_provenance": {
                    "snapshot_id": snapshot_id,
                    "source_attempt_id": parent_attempt_id,
                    "source_receipt_id": row["receipt_id"],
                    "source_checkpoint_id": checkpoint_id,
                },
                "source_metadata": metadata,
            }
            connection.execute(
                "INSERT INTO artifact_receipts(receipt_id, attempt_id, artifact_type, artifact_uri, checksum, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()), child_attempt_id, row["artifact_type"], row["artifact_uri"],
                    row["checksum"], _dump(child_metadata), timestamp,
                ),
            )

    def get_fork_snapshot(self, attempt_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            snapshot = _row(connection.execute(
                "SELECT * FROM attempt_fork_snapshots WHERE attempt_id = ?", (attempt_id,)
            ).fetchone())
            if snapshot is not None:
                snapshot["resumable"] = bool(snapshot.get("resumable"))
                if not snapshot["resumable"]:
                    snapshot["non_resumable_reason"] = snapshot.get("non_resumable_reason") or "fork_snapshot_not_resumable"
            return snapshot

    def acquire_lease(self, attempt_id: str, owner_id: str, *, ttl_seconds: float, now: float | None = None) -> dict[str, Any]:
        owner_id = _identifier(owner_id, "owner_id", required=True)
        timestamp = _now(now)
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self.transaction() as connection:
            lease = connection.execute("SELECT * FROM run_leases WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if lease is not None and lease["expires_at"] > timestamp and lease["owner_id"] != owner_id:
                raise LeaseLostError("attempt is leased by another worker")
            token = 1 if lease is None else lease["fence_token"] + (1 if lease["owner_id"] != owner_id or lease["expires_at"] <= timestamp else 0)
            connection.execute("INSERT INTO run_leases(attempt_id, owner_id, fence_token, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(attempt_id) DO UPDATE SET owner_id=excluded.owner_id, fence_token=excluded.fence_token, heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at", (attempt_id, owner_id, token, timestamp, timestamp + ttl_seconds))
            return _row(connection.execute("SELECT * FROM run_leases WHERE attempt_id = ?", (attempt_id,)).fetchone())  # type: ignore[return-value]

    def heartbeat_lease(self, attempt_id: str, owner_id: str, fence_token: int, *, ttl_seconds: float, now: float | None = None) -> dict[str, Any]:
        timestamp = _now(now)
        with self.transaction() as connection:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, timestamp)
            connection.execute("UPDATE run_leases SET heartbeat_at = ?, expires_at = ? WHERE attempt_id = ?", (timestamp, timestamp + ttl_seconds, attempt_id))
            return _row(connection.execute("SELECT * FROM run_leases WHERE attempt_id = ?", (attempt_id,)).fetchone())  # type: ignore[return-value]

    def expire_leases(self, *, now: float | None = None) -> list[str]:
        timestamp = _now(now)
        with self.transaction() as connection:
            return [row[0] for row in connection.execute("SELECT attempt_id FROM run_leases WHERE expires_at <= ? ORDER BY attempt_id", (timestamp,))]

    def _assert_lease(self, connection: sqlite3.Connection, attempt_id: str, owner_id: str, fence_token: int, timestamp: float) -> None:
        lease = connection.execute("SELECT owner_id, fence_token, expires_at FROM run_leases WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if lease is None or lease["owner_id"] != owner_id or lease["fence_token"] != fence_token or lease["expires_at"] <= timestamp:
            raise LeaseLostError("lease is missing, expired, or fenced")

    def _assert_optional_lease(
        self, connection: sqlite3.Connection, attempt_id: str,
        owner_id: str | None, fence_token: int | None,
    ) -> None:
        if (owner_id is None) != (fence_token is None):
            raise ValueError("owner_id and fence_token must be supplied together")
        if owner_id is not None and fence_token is not None:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, _now())

    def append_event(
        self, attempt_id: str, event_type: str, payload: Any, *, owner_id: str,
        fence_token: int, now: float | None = None, contract_version: str = "legacy/v0",
        actor: Mapping[str, Any] | None = None, idempotency_key: str | None = None,
        causation_id: str | None = None, correlation_id: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = _now(now)
        with self.transaction() as connection:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, timestamp)
            return self._append_event_in_transaction(
                connection, attempt_id, event_type, payload, timestamp=timestamp,
                contract_version=contract_version, actor=actor,
                idempotency_key=idempotency_key, causation_id=causation_id,
                correlation_id=correlation_id, event_id=event_id,
            )

    def append_harness_event(
        self, event: Any, *, owner_id: str, fence_token: int, now: float | None = None,
    ) -> dict[str, Any]:
        """Append an ``AgentEvent/v1`` after verifying its immutable run identity."""
        from sidecar.harness.contracts import AgentEvent

        if not isinstance(event, AgentEvent):
            raise TypeError("event must be an AgentEvent")
        attempt = self.get_attempt(event.attempt_id)
        if attempt is None:
            raise KeyError(event.attempt_id)
        run = self.get_run(attempt["run_id"])
        if run is None or run["run_id"] != event.run_id or run["lineage_id"] != event.lineage_id:
            raise ValueError("event_identity_mismatch")
        return self.append_event(
            event.attempt_id, event.event_type, dict(event.payload), owner_id=owner_id,
            fence_token=fence_token, now=now, contract_version=event.contract_version,
            actor={"kind": event.actor_kind, "id": event.actor_id},
            idempotency_key=event.idempotency_key, causation_id=event.causation_id,
            correlation_id=event.correlation_id, event_id=event.event_id,
        )

    def _append_event_in_transaction(
        self, connection: sqlite3.Connection, attempt_id: str, event_type: str, payload: Any, *,
        timestamp: float, contract_version: str, actor: Mapping[str, Any] | None,
        idempotency_key: str | None, causation_id: str | None, correlation_id: str | None,
        event_id: str | None,
    ) -> dict[str, Any]:
        event_type = _identifier(event_type, "event_type", required=True)
        contract_version = _identifier(contract_version, "contract_version", required=True)
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        causation_id = _identifier(causation_id, "causation_id")
        correlation_id = _identifier(correlation_id, "correlation_id")
        event_id = _identifier(event_id or str(uuid4()), "event_id", required=True)
        normalized_actor = dict(actor or {"kind": "system", "id": "legacy"})
        if not isinstance(normalized_actor.get("kind"), str) or not isinstance(normalized_actor.get("id"), str):
            raise ValueError("actor must contain string kind and id")
        actor_json = _dump({"kind": normalized_actor["kind"], "id": normalized_actor["id"]})
        payload_json = _dump(payload)
        if idempotency_key is not None:
            existing = connection.execute(
                "SELECT * FROM run_events WHERE attempt_id = ? AND idempotency_key = ?",
                (attempt_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                matches = (
                    existing["event_type"] == event_type
                    and existing["payload_json"] == payload_json
                    and existing["contract_version"] == contract_version
                    and (existing["actor_json"] or actor_json) == actor_json
                    and existing["causation_id"] == causation_id
                    and existing["correlation_id"] == correlation_id
                )
                if not matches:
                    raise ValueError("event_idempotency_conflict")
                result = _event_row(existing)
                assert result is not None
                return result
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()[0]
        try:
            connection.execute(
                "INSERT INTO run_events(event_id, attempt_id, sequence, event_type, payload_json, created_at, "
                "contract_version, actor_json, idempotency_key, causation_id, correlation_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, attempt_id, sequence, event_type, payload_json, timestamp,
                 contract_version, actor_json, idempotency_key, causation_id, correlation_id),
            )
        except sqlite3.IntegrityError as error:
            if "event_id" not in str(error).lower():
                raise
            existing = connection.execute("SELECT * FROM run_events WHERE event_id = ?", (event_id,)).fetchone()
            if existing is None:
                raise
            matches = (
                existing["attempt_id"] == attempt_id
                and existing["event_type"] == event_type
                and existing["payload_json"] == payload_json
                and existing["contract_version"] == contract_version
                and (existing["actor_json"] or actor_json) == actor_json
                and existing["idempotency_key"] == idempotency_key
                and existing["causation_id"] == causation_id
                and existing["correlation_id"] == correlation_id
            )
            if not matches:
                raise ValueError("event_id_conflict") from error
            result = _event_row(existing)
            assert result is not None
            return result
        result = _event_row(connection.execute("SELECT * FROM run_events WHERE event_id = ?", (event_id,)).fetchone())
        assert result is not None
        return result

    def append_control_event(
        self, attempt_id: str, command: str, payload: Any | None = None, *, decision_key: str,
    ) -> dict[str, Any]:
        """Durably record an idempotent human control command.

        Human commands intentionally do not need a worker lease, but they must use a
        caller-provided stable decision key.  Reusing that key for different command
        content is rejected rather than silently creating an ambiguous control trail.
        """
        command = _identifier(command, "command", required=True)
        decision_key = _identifier(decision_key, "decision_key", required=True)
        command_payload = {"command": command, "payload": payload or {}}
        payload_json = _dump(command_payload)
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone() is None:
                raise KeyError(attempt_id)
            existing = connection.execute(
                "SELECT * FROM human_decisions WHERE attempt_id = ? AND decision_key = ?",
                (attempt_id, decision_key),
            ).fetchone()
            if existing is not None:
                if existing["decision"] != "control" or existing["payload_json"] != payload_json:
                    raise ValueError("control_decision_conflict")
                event = self._append_event_in_transaction(
                    connection, attempt_id, "control", command_payload, timestamp=_now(),
                    contract_version="AgentEvent/v1", actor={"kind": "human", "id": "runtime_control"},
                    idempotency_key=f"control:{decision_key}", causation_id=decision_key,
                    correlation_id=None, event_id=None,
                )
                return {**event, "idempotent": True}
            else:
                connection.execute(
                    "INSERT INTO human_decisions(decision_id, attempt_id, decision_key, decision, payload_json, created_at) "
                    "VALUES (?, ?, ?, 'control', ?, ?)",
                    (str(uuid4()), attempt_id, decision_key, payload_json, _now()),
                )
            event = self._append_event_in_transaction(
                connection, attempt_id, "control", command_payload, timestamp=_now(),
                contract_version="AgentEvent/v1", actor={"kind": "human", "id": "runtime_control"},
                idempotency_key=f"control:{decision_key}", causation_id=decision_key,
                correlation_id=None, event_id=None,
            )
            return {**event, "idempotent": False}

    def record_artifact_receipt(
        self, attempt_id: str, artifact_type: str, artifact_uri: str, checksum: str | None = None,
        metadata: Any | None = None, *, owner_id: str, fence_token: int,
    ) -> dict[str, Any]:
        """Record a worker-produced receipt only while its current lease is valid."""
        receipt_id, timestamp = str(uuid4()), _now()
        with self.transaction() as connection:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, timestamp)
            connection.execute(
                "INSERT INTO artifact_receipts(receipt_id, attempt_id, artifact_type, artifact_uri, checksum, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (receipt_id, attempt_id, artifact_type, artifact_uri, checksum, _dump(metadata or {}), timestamp),
            )
            return _row(connection.execute("SELECT * FROM artifact_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone())  # type: ignore[return-value]

    def record_system_artifact_receipt(
        self, attempt_id: str, artifact_type: str, artifact_uri: str, checksum: str | None = None,
        metadata: Any | None = None, *, system_reason: str,
    ) -> dict[str, Any]:
        """Explicit non-worker path for import migration and recovery bookkeeping."""
        receipt_id, timestamp = str(uuid4()), _now()
        system_reason = _identifier(system_reason, "system_reason", required=True)
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone() is None:
                raise KeyError(attempt_id)
            connection.execute(
                "INSERT INTO artifact_receipts(receipt_id, attempt_id, artifact_type, artifact_uri, checksum, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt_id, attempt_id, artifact_type, artifact_uri, checksum,
                    _dump({"system_reason": system_reason, "metadata": metadata or {}}), timestamp,
                ),
            )
            return _row(connection.execute("SELECT * FROM artifact_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone())  # type: ignore[return-value]

    def list_events(self, attempt_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_event_row(row) for row in connection.execute("SELECT * FROM run_events WHERE attempt_id = ? AND sequence > ? ORDER BY sequence", (attempt_id, after_sequence))]  # type: ignore[misc]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _event_row(connection.execute("SELECT * FROM run_events WHERE event_id = ?", (event_id,)).fetchone())

    def get_event_by_idempotency(self, attempt_id: str, idempotency_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _event_row(connection.execute(
                "SELECT * FROM run_events WHERE attempt_id = ? AND idempotency_key = ?",
                (attempt_id, _identifier(idempotency_key, "idempotency_key", required=True)),
            ).fetchone())

    def record_human_decision(self, attempt_id: str, decision_key: str, decision: str, payload: Any, *, decision_id: str | None = None) -> dict[str, Any]:
        timestamp = _now()
        decision_id = _identifier(decision_id or str(uuid4()), "decision_id", required=True)
        decision_key = _identifier(decision_key, "decision_key", required=True)
        decision = _identifier(decision, "decision", required=True)
        payload_json = _dump(payload)
        with self.transaction() as connection:
            by_id = connection.execute(
                "SELECT * FROM human_decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
            if by_id is not None:
                if (
                    by_id["attempt_id"] != attempt_id
                    or by_id["decision_key"] != decision_key
                    or by_id["decision"] != decision
                    or by_id["payload_json"] != payload_json
                ):
                    raise ValueError("decision_id_conflict")
                return _row(by_id)  # type: ignore[return-value]
            existing = connection.execute("SELECT * FROM human_decisions WHERE attempt_id = ? AND decision_key = ?", (attempt_id, decision_key)).fetchone()
            if existing is not None:
                if existing["decision"] != decision or existing["payload_json"] != payload_json:
                    raise ValueError("decision_key_conflict")
                return _row(existing)  # type: ignore[return-value]
            connection.execute("INSERT INTO human_decisions(decision_id, attempt_id, decision_key, decision, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (decision_id, attempt_id, decision_key, decision, payload_json, timestamp))
            return _row(connection.execute("SELECT * FROM human_decisions WHERE decision_id = ?", (decision_id,)).fetchone())  # type: ignore[return-value]

    def list_human_decisions(self, attempt_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM human_decisions WHERE attempt_id = ? ORDER BY created_at", (attempt_id,))]  # type: ignore[misc]

    def get_human_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return _row(connection.execute("SELECT * FROM human_decisions WHERE decision_id = ?", (decision_id,)).fetchone())

    def record_approval(self, approval: Any) -> dict[str, Any]:
        """Persist a versioned Harness approval using the legacy decision table."""
        from sidecar.harness.contracts import ApprovalDecision

        if not isinstance(approval, ApprovalDecision):
            raise TypeError("approval must be an ApprovalDecision")
        payload = approval.to_dict()
        payload.pop("decision_id")
        payload.pop("decision_key")
        payload.pop("attempt_id")
        payload.pop("decision")
        return self.record_human_decision(
            approval.attempt_id, approval.decision_key, approval.decision, payload,
            decision_id=approval.decision_id,
        )

    def get_approval(self, decision_id: str) -> dict[str, Any] | None:
        approval = self.get_human_decision(decision_id)
        if approval is None or approval.get("payload", {}).get("contract_version") != "ApprovalDecision/v1":
            return None
        return approval

    def list_approvals(self, attempt_id: str) -> list[dict[str, Any]]:
        return [
            approval for approval in self.list_human_decisions(attempt_id)
            if approval.get("payload", {}).get("contract_version") == "ApprovalDecision/v1"
        ]

    def record_tool_intent(
        self, attempt_id: str, tool_name: str, payload: Any, *,
        tool_call_id: str | None = None, owner_id: str | None = None,
        fence_token: int | None = None,
    ) -> dict[str, Any]:
        call_id = _identifier(tool_call_id or str(uuid4()), "tool_call_id", required=True)
        timestamp = _now()
        with self.transaction() as connection:
            self._assert_optional_lease(connection, attempt_id, owner_id, fence_token)
            connection.execute("INSERT INTO tool_calls(tool_call_id, attempt_id, tool_name, intent_payload_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'intent', ?, ?)", (call_id, attempt_id, _identifier(tool_name, "tool_name", required=True), _dump(payload), timestamp, timestamp))
            return _row(connection.execute("SELECT * FROM tool_calls WHERE tool_call_id = ?", (call_id,)).fetchone())  # type: ignore[return-value]

    def record_tool_result(
        self, tool_call_id: str, payload: Any, *, attempt_id: str | None = None,
        owner_id: str | None = None, fence_token: int | None = None,
    ) -> dict[str, Any]:
        return self._update_tool_call(
            tool_call_id, "result", payload=payload, attempt_id=attempt_id,
            owner_id=owner_id, fence_token=fence_token,
        )

    def record_tool_unknown_outcome(
        self, tool_call_id: str, reason: str, *, attempt_id: str | None = None,
        owner_id: str | None = None, fence_token: int | None = None,
    ) -> dict[str, Any]:
        return self._update_tool_call(
            tool_call_id, "unknown_outcome", reason=reason, attempt_id=attempt_id,
            owner_id=owner_id, fence_token=fence_token,
        )

    def record_tool_failure(
        self, tool_call_id: str, payload: Any, *, attempt_id: str | None = None,
        owner_id: str | None = None, fence_token: int | None = None,
    ) -> dict[str, Any]:
        return self._update_tool_call(
            tool_call_id, "failed", payload=payload,
            reason=str(payload.get("failure_type", "provider_failed")) if isinstance(payload, dict) else "provider_failed",
            attempt_id=attempt_id, owner_id=owner_id, fence_token=fence_token,
        )

    def list_tool_calls(self, attempt_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM tool_calls WHERE attempt_id = ? ORDER BY created_at", (attempt_id,))]  # type: ignore[misc]

    def _update_tool_call(
        self, tool_call_id: str, status: str, *, payload: Any | None = None,
        reason: str | None = None, attempt_id: str | None = None,
        owner_id: str | None = None, fence_token: int | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            call = connection.execute(
                "SELECT attempt_id FROM tool_calls WHERE tool_call_id = ?", (tool_call_id,)
            ).fetchone()
            if call is None:
                raise KeyError(tool_call_id)
            actual_attempt_id = str(call["attempt_id"])
            if attempt_id is not None and attempt_id != actual_attempt_id:
                raise ValueError("tool_call_attempt_mismatch")
            self._assert_optional_lease(
                connection, actual_attempt_id, owner_id, fence_token
            )
            connection.execute("UPDATE tool_calls SET status = ?, result_payload_json = COALESCE(?, result_payload_json), unknown_reason = COALESCE(?, unknown_reason), updated_at = ? WHERE tool_call_id = ?", (status, _dump(payload) if payload is not None else None, reason, _now(), tool_call_id))
            row = _row(connection.execute("SELECT * FROM tool_calls WHERE tool_call_id = ?", (tool_call_id,)).fetchone())
            assert row is not None
            return row

    def list_unknown_call_summaries(self, attempt_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT tool_call_id, intent_payload_json, unknown_reason FROM tool_calls "
                "WHERE attempt_id = ? AND status = 'unknown_outcome' ORDER BY created_at",
                (attempt_id,),
            ).fetchall()
            decisions = {
                row["decision_key"]: row["decision"]
                for row in connection.execute(
                    "SELECT decision_key, decision FROM human_decisions WHERE attempt_id = ?",
                    (attempt_id,),
                )
            }
        summaries = []
        for row in rows:
            intent = json.loads(row["intent_payload_json"])
            idempotency_key = str(intent.get("idempotency_key") or hashlib.sha256(
                f"{attempt_id}:{row['tool_call_id']}".encode("utf-8")
            ).hexdigest())
            decision_key = f"retry_provider_call:{idempotency_key}"
            summaries.append({
                "tool_call_id": row["tool_call_id"],
                "idempotency_key": idempotency_key,
                "decision_key": decision_key,
                "safe_reason": _safe_unknown_reason(row["unknown_reason"]),
                "decision_state": decisions.get(decision_key, "pending"),
            })
        return summaries

    def record_unknown_call_decision(
        self, attempt_id: str, decision_key: str, decision: str,
    ) -> dict[str, Any]:
        if decision not in {"authorize_retry_once", "cancel"}:
            raise ValueError("unsupported_unknown_outcome_decision")
        decision_key = _identifier(decision_key, "decision_key", required=True)
        now = _now()
        with self.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone() is None:
                raise KeyError(attempt_id)
            matched = False
            for call in connection.execute(
                "SELECT intent_payload_json FROM tool_calls WHERE attempt_id = ? AND status = 'unknown_outcome'",
                (attempt_id,),
            ):
                idempotency_key = str(json.loads(call["intent_payload_json"]).get("idempotency_key", ""))
                if idempotency_key and decision_key == f"retry_provider_call:{idempotency_key}":
                    matched = True
                    break
            if not matched:
                raise ValueError("unknown_call_decision_key_not_found")
            existing = connection.execute(
                "SELECT * FROM human_decisions WHERE attempt_id = ? AND decision_key = ?",
                (attempt_id, decision_key),
            ).fetchone()
            recorded_now = existing is None
            if existing is not None:
                if existing["decision"] != decision or existing["payload_json"] != "{}":
                    raise ValueError("decision_key_conflict")
                result = _row(existing)
            else:
                decision_id = str(uuid4())
                connection.execute(
                    "INSERT INTO human_decisions(decision_id, attempt_id, decision_key, decision, payload_json, created_at) VALUES (?, ?, ?, ?, '{}', ?)",
                    (decision_id, attempt_id, decision_key, decision, now),
                )
                result = _row(connection.execute(
                    "SELECT * FROM human_decisions WHERE decision_id = ?", (decision_id,)
                ).fetchone())
            if decision == "cancel" and recorded_now:
                connection.execute(
                    "UPDATE agent_attempts SET status = 'cancelled', updated_at = ? WHERE attempt_id = ?",
                    (now, attempt_id),
                )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT OR IGNORE INTO run_events(event_id, attempt_id, sequence, event_type, payload_json, created_at) VALUES (?, ?, ?, 'control', ?, ?)",
                    (str(uuid4()), attempt_id, sequence, _dump({"command": "cancel", "decision_key": decision_key}), now),
                )
            assert result is not None
            return {**result, "attempt_status": "cancelled" if decision == "cancel" else "waiting_human"}

    def record_authorized_retry_intent(
        self, attempt_id: str, unknown_tool_call_id: str, decision_key: str,
        tool_name: str, payload: Any, *, tool_call_id: str,
        owner_id: str, fence_token: int,
    ) -> dict[str, Any]:
        """Consume one authorization and create its sole retry intent atomically."""
        now = _now()
        with self.transaction() as connection:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, now)
            unknown = connection.execute(
                "SELECT * FROM tool_calls WHERE tool_call_id = ? AND attempt_id = ?",
                (unknown_tool_call_id, attempt_id),
            ).fetchone()
            if unknown is None or unknown["status"] != "unknown_outcome":
                raise ValueError("unknown_retry_already_consumed")
            unknown_intent = json.loads(unknown["intent_payload_json"])
            expected_key = f"retry_provider_call:{unknown_intent.get('idempotency_key', '')}"
            if decision_key != expected_key:
                raise ValueError("unknown_retry_decision_key_mismatch")
            decision = connection.execute(
                "SELECT decision FROM human_decisions WHERE attempt_id = ? AND decision_key = ?",
                (attempt_id, decision_key),
            ).fetchone()
            if decision is None or decision["decision"] != "authorize_retry_once":
                raise ValueError("unknown_retry_not_authorized")
            connection.execute(
                "UPDATE tool_calls SET status = 'retry_consumed', updated_at = ? WHERE tool_call_id = ? AND status = 'unknown_outcome'",
                (now, unknown_tool_call_id),
            )
            connection.execute(
                "INSERT INTO tool_calls(tool_call_id, attempt_id, tool_name, intent_payload_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'intent', ?, ?)",
                (tool_call_id, attempt_id, _identifier(tool_name, "tool_name", required=True), _dump(payload), now, now),
            )
            row = _row(connection.execute(
                "SELECT * FROM tool_calls WHERE tool_call_id = ?", (tool_call_id,)
            ).fetchone())
            assert row is not None
            return row

    def resolve_authorized_unknown_with_artifact(
        self, attempt_id: str, unknown_tool_call_id: str, decision_key: str,
        artifact_receipt: Any, *, owner_id: str, fence_token: int,
    ) -> dict[str, Any]:
        """Atomically consume one authorized unknown using a verified artifact."""
        if not isinstance(artifact_receipt, dict):
            raise ValueError("artifact_receipt_must_be_an_object")
        safe_receipt = {
            "operation_key": _identifier(artifact_receipt.get("operation_key"), "operation_key", required=True),
            "artifact_path": _identifier(artifact_receipt.get("artifact_path"), "artifact_path", required=True),
            "artifact_hash": _identifier(artifact_receipt.get("artifact_hash"), "artifact_hash", required=True),
        }
        if not re.fullmatch(r"[0-9a-f]{64}", str(safe_receipt["operation_key"])):
            raise ValueError("artifact_operation_key_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(safe_receipt["artifact_hash"])):
            raise ValueError("artifact_hash_invalid")
        receipt_path = Path(str(safe_receipt["artifact_path"]))
        if receipt_path.is_absolute() or any(part in {"", ".", ".."} for part in receipt_path.parts):
            raise ValueError("artifact_path_invalid")
        project_root = self.project_root.resolve()
        artifact_path = project_root / receipt_path
        if not artifact_path.resolve(strict=False).is_relative_to(project_root):
            raise ValueError("artifact_path_escapes_project")
        now = _now()
        with self.transaction() as connection:
            self._assert_lease(connection, attempt_id, owner_id, fence_token, now)
            unknown = connection.execute(
                "SELECT * FROM tool_calls WHERE tool_call_id = ? AND attempt_id = ?",
                (unknown_tool_call_id, attempt_id),
            ).fetchone()
            if unknown is None:
                raise ValueError("unknown_retry_not_found")
            unknown_intent = json.loads(unknown["intent_payload_json"])
            idempotency_key = str(unknown_intent.get("idempotency_key", ""))
            expected_key = f"retry_provider_call:{idempotency_key}"
            if decision_key != expected_key:
                raise ValueError("unknown_retry_decision_key_mismatch")
            decision = connection.execute(
                "SELECT decision FROM human_decisions WHERE attempt_id = ? AND decision_key = ?",
                (attempt_id, decision_key),
            ).fetchone()
            if decision is None or decision["decision"] != "authorize_retry_once":
                raise ValueError("unknown_retry_not_authorized")
            try:
                resolved_artifact_path = artifact_path.resolve(strict=True)
            except FileNotFoundError as exc:
                raise ValueError("artifact_missing") from exc
            except OSError as exc:
                raise ValueError("artifact_path_invalid") from exc
            if not resolved_artifact_path.is_relative_to(project_root):
                raise ValueError("artifact_path_escapes_project")
            if artifact_path.is_symlink():
                raise ValueError("artifact_symlink_rejected")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(artifact_path, flags)
            except FileNotFoundError as exc:
                raise ValueError("artifact_missing") from exc
            except OSError as exc:
                raise ValueError("artifact_unreadable") from exc
            try:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ValueError("artifact_not_regular_file")
                with os.fdopen(descriptor, "rb") as artifact_file:
                    descriptor = -1
                    artifact_bytes = artifact_file.read()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if hashlib.sha256(artifact_bytes).hexdigest() != safe_receipt["artifact_hash"]:
                raise ValueError("artifact_hash_mismatch")
            try:
                artifact_payload = json.loads(artifact_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("artifact_contract_invalid") from exc
            if not isinstance(artifact_payload, dict) or artifact_payload.get("contract") != "W1ProviderResponse/v1":
                raise ValueError("artifact_contract_invalid")
            if artifact_payload.get("operation_key") != safe_receipt["operation_key"]:
                raise ValueError("artifact_operation_key_mismatch")
            resolution = {
                "outcome": "resolved_from_verified_artifact",
                "idempotency_key": idempotency_key,
                "artifact_receipt": safe_receipt,
            }
            if unknown["status"] == "retry_consumed":
                existing = json.loads(unknown["result_payload_json"]) if unknown["result_payload_json"] else None
                if existing == resolution:
                    row = _row(unknown)
                    assert row is not None
                    return {**row, "idempotent": True}
                raise ValueError("unknown_retry_already_consumed")
            if unknown["status"] != "unknown_outcome":
                raise ValueError("unknown_retry_already_consumed")
            connection.execute(
                "UPDATE tool_calls SET status = 'retry_consumed', result_payload_json = ?, updated_at = ? "
                "WHERE tool_call_id = ? AND status = 'unknown_outcome'",
                (_dump(resolution), now, unknown_tool_call_id),
            )
            row = _row(connection.execute(
                "SELECT * FROM tool_calls WHERE tool_call_id = ?", (unknown_tool_call_id,)
            ).fetchone())
            assert row is not None
            return {**row, "idempotent": False}

    def list_artifact_receipts(self, attempt_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM artifact_receipts WHERE attempt_id = ? ORDER BY created_at", (attempt_id,))]  # type: ignore[misc]

    def record_checkpoint_metadata(
        self, attempt_id: str, checkpoint_id: str, *, node: str, sequence: int,
        parent_checkpoint_id: str | None = None, metadata: Any | None = None,
    ) -> dict[str, Any]:
        checkpoint_id = _identifier(checkpoint_id, "checkpoint_id", required=True)
        parent_checkpoint_id = _identifier(parent_checkpoint_id, "parent_checkpoint_id")
        node = _identifier(node, "node", required=True)
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM agent_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone() is None:
                raise KeyError(attempt_id)
            connection.execute(
                "INSERT INTO checkpoint_metadata(checkpoint_id, attempt_id, parent_checkpoint_id, node, sequence, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(checkpoint_id) DO NOTHING",
                (checkpoint_id, attempt_id, parent_checkpoint_id, node, sequence, _dump(metadata or {}), _now()),
            )
            row = _row(connection.execute("SELECT * FROM checkpoint_metadata WHERE checkpoint_id = ?", (checkpoint_id,)).fetchone())
            if row is None:
                raise RuntimeStoreError("checkpoint metadata was not recorded")
            return row

    def list_checkpoint_metadata(self, attempt_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM checkpoint_metadata WHERE attempt_id = ? ORDER BY sequence", (attempt_id,))]  # type: ignore[misc]

    def acquire_resource_lease(self, resource_key: str, owner_id: str, *, ttl_seconds: float, now: float | None = None) -> dict[str, Any]:
        resource_key = _identifier(resource_key, "resource_key", required=True)
        owner_id = _identifier(owner_id, "owner_id", required=True)
        timestamp = _now(now)
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self.transaction() as connection:
            lease = connection.execute("SELECT * FROM resource_leases WHERE resource_key = ?", (resource_key,)).fetchone()
            if lease is not None and lease["expires_at"] > timestamp and lease["owner_id"] != owner_id:
                raise LeaseLostError("resource is leased by another worker")
            token = 1 if lease is None else lease["fence_token"] + (1 if lease["owner_id"] != owner_id or lease["expires_at"] <= timestamp else 0)
            connection.execute(
                "INSERT INTO resource_leases(resource_key, owner_id, fence_token, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(resource_key) DO UPDATE SET owner_id=excluded.owner_id, fence_token=excluded.fence_token, heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at",
                (resource_key, owner_id, token, timestamp, timestamp + ttl_seconds),
            )
            return _row(connection.execute("SELECT * FROM resource_leases WHERE resource_key = ?", (resource_key,)).fetchone())  # type: ignore[return-value]

    def release_resource_lease(self, resource_key: str, owner_id: str, fence_token: int) -> None:
        with self.transaction() as connection:
            result = connection.execute(
                "DELETE FROM resource_leases WHERE resource_key = ? AND owner_id = ? AND fence_token = ?",
                (resource_key, owner_id, fence_token),
            )
            if result.rowcount != 1:
                raise LeaseLostError("resource lease is missing or fenced")

    def enqueue_outbox(self, topic: str, payload: Any, *, attempt_id: str | None = None) -> dict[str, Any]:
        outbox_id, timestamp = str(uuid4()), _now()
        with self.transaction() as connection:
            connection.execute("INSERT INTO outbox(outbox_id, attempt_id, topic, payload_json, created_at) VALUES (?, ?, ?, ?, ?)", (outbox_id, attempt_id, _identifier(topic, "topic", required=True), _dump(payload), timestamp))
            return _row(connection.execute("SELECT * FROM outbox WHERE outbox_id = ?", (outbox_id,)).fetchone())  # type: ignore[return-value]

    def list_pending_outbox(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM outbox WHERE delivered_at IS NULL ORDER BY created_at LIMIT ?", (limit,))]  # type: ignore[misc]

    def mark_outbox_delivered(self, outbox_id: str, *, now: float | None = None) -> None:
        with self.transaction() as connection:
            result = connection.execute("UPDATE outbox SET delivered_at = COALESCE(delivered_at, ?) WHERE outbox_id = ?", (_now(now), outbox_id))
            if result.rowcount != 1:
                raise KeyError(outbox_id)

    def submit_task_plan(self, run_id: str, plan: Any, *, now: float | None = None) -> dict[str, Any]:
        """Persist a typed task DAG once; repeated identical submissions are no-ops."""
        timestamp = _now(now)
        plan_id = _identifier(getattr(plan, "plan_id", None), "plan_id", required=True)
        tasks = tuple(getattr(plan, "tasks", ()))
        policy_version = _identifier(getattr(plan, "policy_version", "v1"), "policy_version", required=True)
        task_ids = [getattr(task, "task_id", None) for task in tasks]
        if not tasks or len(task_ids) != len(set(task_ids)) or any(not isinstance(task_id, str) or not task_id for task_id in task_ids):
            raise ValueError("plan must contain unique tasks")
        known = set(task_ids)
        for task in tasks:
            if not set(getattr(task, "dependencies", ())).issubset(known):
                raise ValueError("task has an unknown dependency")
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise KeyError(run_id)
            existing = connection.execute("SELECT * FROM agent_task_plans WHERE run_id = ?", (run_id,)).fetchone()
            if existing is not None:
                if existing["plan_id"] != plan_id:
                    raise RuntimeStoreError("a different plan is already submitted for this run")
                return {"plan_id": plan_id, "idempotent": True, "tasks": self._task_rows(connection, run_id)}
            connection.execute("INSERT INTO agent_task_plans(run_id, plan_id, policy_version, submitted_at, updated_at) VALUES (?, ?, ?, ?, ?)", (run_id, plan_id, policy_version, timestamp, timestamp))
            for task in tasks:
                task_id = _identifier(task.task_id, "task_id", required=True)
                connection.execute(
                    "INSERT INTO agent_tasks(run_id, task_id, title, dependencies_json, read_set_json, write_set_json, status, fence_map_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', '{}', ?, ?)",
                    (run_id, task_id, _identifier(task.title, "title", required=True), _dump(tuple(task.dependencies)), _dump(tuple(task.read_set)), _dump(tuple(task.write_set)), timestamp, timestamp),
                )
            return {"plan_id": plan_id, "idempotent": False, "tasks": self._task_rows(connection, run_id)}

    def claim_ready_tasks(self, run_id: str, worker_id: str, *, max_concurrency: int = 4, ttl_seconds: float = 30, now: float | None = None) -> list[dict[str, Any]]:
        """Atomically claim dependency-ready tasks and acquire every write fence."""
        worker_id = _identifier(worker_id, "worker_id", required=True)
        timestamp = _now(now)
        if max_concurrency < 1 or ttl_seconds <= 0:
            raise ValueError("max_concurrency and ttl_seconds must be positive")
        with self.transaction() as connection:
            self._recover_expired_task_claims(connection, run_id, timestamp)
            running = connection.execute("SELECT COUNT(*) FROM agent_tasks WHERE run_id = ? AND status = 'running'", (run_id,)).fetchone()[0]
            slots = max(max_concurrency - running, 0)
            claimed: list[dict[str, Any]] = []
            for row in connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND status = 'pending' ORDER BY created_at, task_id", (run_id,)).fetchall():
                if not slots:
                    break
                dependencies = json.loads(row["dependencies_json"])
                dependency_statuses = self._dependency_statuses(connection, run_id, dependencies)
                if any(status in {"failed", "blocked", "cancelled"} for status in dependency_statuses.values()):
                    self._block_task(connection, run_id, row["task_id"], "dependency_failed", timestamp)
                    continue
                if len(dependency_statuses) != len(dependencies) or not all(status == "completed" for status in dependency_statuses.values()):
                    continue
                fences = self._acquire_task_resources(connection, run_id, row["task_id"], json.loads(row["write_set_json"]), ttl_seconds, timestamp)
                if fences is None:
                    continue
                connection.execute("UPDATE agent_tasks SET status = 'running', assigned_agent = ?, claim_owner = ?, claim_expires_at = ?, fence_map_json = ?, attempts = attempts + 1, updated_at = ? WHERE run_id = ? AND task_id = ? AND status = 'pending'", (worker_id, worker_id, timestamp + ttl_seconds, _dump(fences), timestamp, run_id, row["task_id"]))
                task = _row(connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, row["task_id"])).fetchone())
                assert task is not None
                claimed.append(task)
                slots -= 1
            return claimed

    def complete_task(self, run_id: str, task_id: str, worker_id: str, fences: dict[str, int], *, now: float | None = None) -> dict[str, Any]:
        return self._finish_task(run_id, task_id, worker_id, fences, "completed", now=now)

    def heartbeat_task_claim(
        self, run_id: str, task_id: str, worker_id: str, fences: dict[str, int],
        *, ttl_seconds: float, now: float | None = None,
    ) -> dict[str, Any]:
        """Atomically renew a task claim and every write resource it fences."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        timestamp = _now(now)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?",
                (run_id, task_id),
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            expected = json.loads(row["fence_map_json"])
            if (
                row["status"] != "running"
                or row["claim_owner"] != worker_id
                or row["claim_expires_at"] <= timestamp
                or expected != fences
            ):
                raise LeaseLostError("task claim is missing, expired, or fenced")
            self._assert_task_resources(connection, run_id, task_id, expected, timestamp)
            expires_at = timestamp + ttl_seconds
            connection.execute(
                "UPDATE agent_tasks SET claim_expires_at = ?, updated_at = ? "
                "WHERE run_id = ? AND task_id = ?",
                (expires_at, timestamp, run_id, task_id),
            )
            owner = self._task_owner(run_id, task_id)
            for resource, fence in expected.items():
                result = connection.execute(
                    "UPDATE resource_leases SET heartbeat_at = ?, expires_at = ? "
                    "WHERE resource_key = ? AND owner_id = ? AND fence_token = ?",
                    (timestamp, expires_at, resource, owner, fence),
                )
                if result.rowcount != 1:
                    raise LeaseLostError("resource lease is missing, expired, or fenced")
            renewed = _row(connection.execute(
                "SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?",
                (run_id, task_id),
            ).fetchone())
            assert renewed is not None
            return renewed

    def fail_task(self, run_id: str, task_id: str, worker_id: str, fences: dict[str, int], reason: str, *, now: float | None = None) -> dict[str, Any]:
        result = self._finish_task(run_id, task_id, worker_id, fences, "failed", reason=reason, now=now)
        with self.transaction() as connection:
            self._propagate_task_blocks(connection, run_id, _now(now))
        return result

    def cancel_task_plan(self, run_id: str, *, reason: str = "run_cancelled", now: float | None = None) -> None:
        timestamp = _now(now)
        with self.transaction() as connection:
            for row in connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND status IN ('pending', 'running')", (run_id,)).fetchall():
                self._release_task_resources(connection, run_id, row["task_id"], json.loads(row["fence_map_json"]))
                connection.execute("UPDATE agent_tasks SET status = 'cancelled', updated_at = ? WHERE run_id = ? AND task_id = ?", (timestamp, run_id, row["task_id"]))
                self._dead_letter(connection, run_id, row["task_id"], reason, None, timestamp)

    def recover_expired_task_claims(self, run_id: str, *, now: float | None = None) -> list[str]:
        with self.transaction() as connection:
            return self._recover_expired_task_claims(connection, run_id, _now(now))

    def get_task_status(self, run_id: str, task_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)).fetchone()
            if row is None:
                raise KeyError(task_id)
            return row[0]

    def get_task_dag(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._task_rows(connection, run_id)

    def list_dead_letters(self, run_id: str, *, recoverable_only: bool = False) -> list[dict[str, Any]]:
        clause = " AND recovered_at IS NULL" if recoverable_only else ""
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM dead_letters WHERE run_id = ?" + clause + " ORDER BY created_at, task_id", (run_id,))]  # type: ignore[misc]

    def recover_dead_letter(self, run_id: str, task_id: str, *, now: float | None = None) -> dict[str, Any]:
        timestamp = _now(now)
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row["status"] not in {"failed", "blocked", "cancelled"}:
                raise ValueError("task is not recoverable")
            connection.execute("UPDATE agent_tasks SET status = 'pending', assigned_agent = NULL, claim_owner = NULL, claim_expires_at = NULL, fence_map_json = '{}', failure_signature = NULL, updated_at = ? WHERE run_id = ? AND task_id = ?", (timestamp, run_id, task_id))
            connection.execute("UPDATE dead_letters SET recovered_at = ? WHERE run_id = ? AND task_id = ? AND recovered_at IS NULL", (timestamp, run_id, task_id))
            return _row(connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)).fetchone())  # type: ignore[return-value]

    def record_memory(self, *, layer: str, record_type: str, content: str, provenance: str, confidence: float, references: Any | None = None, run_id: str | None = None, policy_version: str = "v1", memory_id: str | None = None, now: float | None = None) -> dict[str, Any]:
        if layer not in {"working", "episodic", "semantic", "procedural"}:
            raise ValueError("unsupported memory layer")
        allowed = {"working": {"checkpoint_reference", "token_delta"}, "episodic": {"decision_summary", "event_summary", "detailed_episodic", "human_decision", "cost_summary", "final_summary"}, "semantic": {"project_entity_reference"}, "procedural": {"prompt_version", "tool_version", "policy_version"}}
        if record_type not in allowed[layer] or not provenance or not 0 <= confidence <= 1:
            raise ValueError("memory type, provenance, or confidence is invalid")
        if _SECRET_VALUE.search(content) or _SECRET_KEY.search(content) or re.search(r"(?i)(hidden chain.?of.?thought|prompt body|source body|internal reasoning)", content) or _contains_unsafe_memory(references or {}):
            raise SecretValueError("memory content is not safe to persist")
        timestamp = _now(now)
        expires_at = None if record_type in {"human_decision", "cost_summary", "final_summary", "project_entity_reference", "prompt_version", "tool_version", "policy_version"} else timestamp + (7 * 86400 if record_type in {"checkpoint_reference", "token_delta"} else 30 * 86400)
        memory_id = _identifier(memory_id or str(uuid4()), "memory_id", required=True)
        with self.transaction() as connection:
            connection.execute("INSERT INTO memory_records(memory_id, run_id, layer, record_type, content, reference_json, provenance, confidence, policy_version, expires_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(memory_id) DO NOTHING", (memory_id, run_id, layer, record_type, redact_secrets(content), _dump(references or {}), provenance, confidence, policy_version, expires_at, timestamp, timestamp))
            return _row(connection.execute("SELECT * FROM memory_records WHERE memory_id = ?", (memory_id,)).fetchone())  # type: ignore[return-value]

    store_memory = record_memory

    def query_blackboard(self, *, run_id: str | None = None, layer: str | None = None, now: float | None = None) -> list[dict[str, Any]]:
        timestamp = _now(now)
        clauses, values = ["(expires_at IS NULL OR expires_at > ?)"], [timestamp]
        if run_id is not None:
            clauses.append("run_id = ?")
            values.append(run_id)
        if layer is not None:
            clauses.append("layer = ?")
            values.append(layer)
        with self._connect() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM memory_records WHERE " + " AND ".join(clauses) + " ORDER BY created_at, rowid", values)]  # type: ignore[misc]

    def compact_memory(self, *, now: float | None = None) -> dict[str, int]:
        timestamp = _now(now)
        with self.transaction() as connection:
            deleted = connection.execute("DELETE FROM memory_records WHERE expires_at IS NOT NULL AND expires_at <= ?", (timestamp,)).rowcount
            connection.execute("VACUUM") if False else None
            return {"deleted": deleted, "remaining": connection.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0]}

    janitor_memory = compact_memory

    def _finish_task(self, run_id: str, task_id: str, worker_id: str, fences: dict[str, int], status: str, *, reason: str | None = None, now: float | None = None) -> dict[str, Any]:
        timestamp = _now(now)
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)).fetchone()
            if row is None:
                raise KeyError(task_id)
            expected = json.loads(row["fence_map_json"])
            if row["status"] != "running" or row["claim_owner"] != worker_id or row["claim_expires_at"] <= timestamp or expected != fences:
                raise LeaseLostError("task claim is missing, expired, or fenced")
            self._assert_task_resources(connection, run_id, task_id, expected, timestamp)
            self._release_task_resources(connection, run_id, task_id, expected)
            signature = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16] if reason else None
            connection.execute("UPDATE agent_tasks SET status = ?, claim_expires_at = NULL, fence_map_json = '{}', failure_signature = ?, completed_at = ?, updated_at = ? WHERE run_id = ? AND task_id = ?", (status, signature, timestamp, timestamp, run_id, task_id))
            if status == "failed":
                self._dead_letter(connection, run_id, task_id, reason or "task_failed", signature, timestamp)
            return _row(connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND task_id = ?", (run_id, task_id)).fetchone())  # type: ignore[return-value]

    @staticmethod
    def _task_owner(run_id: str, task_id: str) -> str:
        return f"task:{run_id}:{task_id}"

    def _acquire_task_resources(self, connection: sqlite3.Connection, run_id: str, task_id: str, resources: list[str], ttl_seconds: float, timestamp: float) -> dict[str, int] | None:
        owner = self._task_owner(run_id, task_id)
        acquired: dict[str, int] = {}
        for resource in sorted(set(resources)):
            lease = connection.execute("SELECT * FROM resource_leases WHERE resource_key = ?", (resource,)).fetchone()
            if lease is not None and lease["expires_at"] > timestamp and lease["owner_id"] != owner:
                self._release_task_resources(connection, run_id, task_id, acquired)
                return None
            fence = 1 if lease is None else lease["fence_token"] + (1 if lease["owner_id"] != owner or lease["expires_at"] <= timestamp else 0)
            connection.execute("INSERT INTO resource_leases(resource_key, owner_id, fence_token, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(resource_key) DO UPDATE SET owner_id=excluded.owner_id, fence_token=excluded.fence_token, heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at", (resource, owner, fence, timestamp, timestamp + ttl_seconds))
            acquired[resource] = fence
        return acquired

    def _assert_task_resources(self, connection: sqlite3.Connection, run_id: str, task_id: str, fences: dict[str, int], timestamp: float) -> None:
        owner = self._task_owner(run_id, task_id)
        for resource, fence in fences.items():
            lease = connection.execute("SELECT * FROM resource_leases WHERE resource_key = ?", (resource,)).fetchone()
            if lease is None or lease["owner_id"] != owner or lease["fence_token"] != fence or lease["expires_at"] <= timestamp:
                raise LeaseLostError("resource lease is missing, expired, or fenced")

    def _release_task_resources(self, connection: sqlite3.Connection, run_id: str, task_id: str, fences: dict[str, int]) -> None:
        owner = self._task_owner(run_id, task_id)
        for resource, fence in fences.items():
            connection.execute("DELETE FROM resource_leases WHERE resource_key = ? AND owner_id = ? AND fence_token = ?", (resource, owner, fence))

    def _recover_expired_task_claims(self, connection: sqlite3.Connection, run_id: str, timestamp: float) -> list[str]:
        recovered: list[str] = []
        for row in connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND status = 'running' AND claim_expires_at <= ?", (run_id, timestamp)).fetchall():
            # Keep expired lease rows so the replacement claim advances, rather
            # than reuses, every fence token.
            connection.execute("UPDATE agent_tasks SET status = 'pending', assigned_agent = NULL, claim_owner = NULL, claim_expires_at = NULL, fence_map_json = '{}', updated_at = ? WHERE run_id = ? AND task_id = ?", (timestamp, run_id, row["task_id"]))
            recovered.append(row["task_id"])
        return recovered

    def _dependency_statuses(self, connection: sqlite3.Connection, run_id: str, dependencies: list[str]) -> dict[str, str]:
        if not dependencies:
            return {}
        placeholders = ",".join("?" for _ in dependencies)
        return {row["task_id"]: row["status"] for row in connection.execute(f"SELECT task_id, status FROM agent_tasks WHERE run_id = ? AND task_id IN ({placeholders})", [run_id, *dependencies])}

    def _propagate_task_blocks(self, connection: sqlite3.Connection, run_id: str, timestamp: float) -> None:
        changed = True
        while changed:
            changed = False
            for row in connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? AND status = 'pending'", (run_id,)).fetchall():
                statuses = self._dependency_statuses(connection, run_id, json.loads(row["dependencies_json"]))
                if any(status in {"failed", "blocked", "cancelled"} for status in statuses.values()):
                    self._block_task(connection, run_id, row["task_id"], "dependency_failed", timestamp)
                    changed = True

    def _block_task(self, connection: sqlite3.Connection, run_id: str, task_id: str, reason: str, timestamp: float) -> None:
        connection.execute("UPDATE agent_tasks SET status = 'blocked', updated_at = ? WHERE run_id = ? AND task_id = ? AND status = 'pending'", (timestamp, run_id, task_id))
        self._dead_letter(connection, run_id, task_id, reason, None, timestamp)

    def _dead_letter(self, connection: sqlite3.Connection, run_id: str, task_id: str, reason: str, signature: str | None, timestamp: float) -> None:
        connection.execute("INSERT INTO dead_letters(dead_letter_id, run_id, task_id, reason, failure_signature, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, task_id, reason) DO NOTHING", (str(uuid4()), run_id, task_id, reason, signature, timestamp))

    @staticmethod
    def _task_rows(connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
        return [_row(row) for row in connection.execute("SELECT * FROM agent_tasks WHERE run_id = ? ORDER BY created_at, task_id", (run_id,))]  # type: ignore[misc]

    def scan_recoverable_attempts(self, *, now: float | None = None) -> list[dict[str, Any]]:
        timestamp = _now(now)
        with self.transaction() as connection:
            # A dead worker must never continue to appear as running to recovery/UI.
            connection.execute(
                "UPDATE agent_attempts SET status = 'interrupted', updated_at = ? "
                "WHERE status = 'running' AND attempt_id IN "
                "(SELECT attempt_id FROM run_leases WHERE expires_at <= ?)",
                (timestamp, timestamp),
            )
            rows = connection.execute("SELECT a.*, r.lineage_id, r.workflow_id, r.config_json FROM agent_attempts a JOIN agent_runs r ON r.run_id = a.run_id LEFT JOIN run_leases l ON l.attempt_id = a.attempt_id WHERE a.status IN ('running', 'interrupted', 'waiting_human', 'paused', 'needs_credentials') AND (l.attempt_id IS NULL OR l.expires_at <= ?) ORDER BY a.created_at", (timestamp,))
            attempts = [_row(row) for row in rows]  # type: ignore[misc]
            for attempt in attempts:
                config = dict(attempt.pop("config", {}) or {})
                completed = int(config.get("completed_chunks", 0) or 0)
                total = int(config.get("total_chunks", 0) or 0)
                source_compatible = self._source_is_compatible(config)
                usage = self._load_usage_ledger(attempt["lineage_id"], attempt["attempt_id"])
                budget_config = dict(config.get("budget_config") or {})
                max_cost = budget_config.get("max_cost_usd")
                spent_cost = usage.get("cost_usd") if isinstance(usage, dict) else None
                known_spend = isinstance(spent_cost, (int, float)) and not isinstance(spent_cost, bool)
                remaining_cost = {
                    "max_cost_usd": max_cost if isinstance(max_cost, (int, float)) and not isinstance(max_cost, bool) else None,
                    "spent_cost_usd": float(spent_cost) if known_spend else None,
                    "remaining_cost_usd": max(0.0, float(max_cost) - float(spent_cost)) if known_spend and isinstance(max_cost, (int, float)) and not isinstance(max_cost, bool) else None,
                    "unknown_spend": not known_spend,
                    "remaining_chunks": max(total - completed, 0),
                }
                attempt.update({
                    "config": config,
                    "progress": config.get("progress", (completed / total if total else 0.0)),
                    "source_compatible": source_compatible,
                    "remaining_cost": remaining_cost,
                    "unknown_calls": self.list_unknown_call_summaries(attempt["attempt_id"]),
                })
            return attempts

    def _source_is_compatible(self, config: dict[str, Any]) -> bool:
        source_path = config.get("source_file_path")
        source_hash = config.get("source_hash")
        if not isinstance(source_path, str) or not source_path or not isinstance(source_hash, str) or not source_hash:
            return False
        candidates = [Path(source_path)]
        staged_relative = config.get("w1_supervisor_staged_source_relative_path")
        if isinstance(staged_relative, str) and staged_relative:
            candidates.append(self.project_root / staged_relative)
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(self.project_root) if candidate != Path(source_path) else None
                if hashlib.sha256(resolved.read_bytes()).hexdigest() == source_hash:
                    return True
            except (OSError, ValueError):
                continue
        return False

    def _load_usage_ledger(self, lineage_id: str, attempt_id: str) -> dict[str, Any]:
        path = self.project_root / "system" / "imports" / lineage_id / "attempts" / attempt_id / "usage_ledger.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def invalidate_leases_for_restart(self) -> None:
        """Make persisted attempts recoverable when this project sidecar restarts."""
        with self.transaction() as connection:
            timestamp = _now()
            # An intent without a durable result is ambiguous after shutdown.
            # Preserve it as a human-gated outcome; never turn it into a retry.
            connection.execute(
                "UPDATE tool_calls SET status = 'unknown_outcome', unknown_reason = 'runtime_interrupted', updated_at = ? "
                "WHERE status = 'intent' AND attempt_id IN (SELECT attempt_id FROM agent_attempts WHERE status = 'running')",
                (timestamp,),
            )
            connection.execute("UPDATE agent_attempts SET status = 'interrupted', updated_at = ? WHERE status = 'running'", (timestamp,))
            connection.execute("UPDATE run_leases SET expires_at = 0")
