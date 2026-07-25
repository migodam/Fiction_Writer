from __future__ import annotations

import os
import re
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sidecar.runtime.w1_budget_policy import (
    W1BudgetPolicyError,
    merge_w1_resume_budget_policy,
)


router = APIRouter(prefix="/runtime")


def _merge_budget_config(
    existing: Mapping[str, Any] | None,
    requested: Mapping[str, Any] | None,
    *,
    model: str,
) -> dict[str, Any]:
    """Return the server-normalized intersection of stored and requested limits."""
    return merge_w1_resume_budget_policy(model, existing, requested)


def require_project_identity(request: Request, project_path: str) -> None:
    configured = str(getattr(request.app.state, "project_path", "") or "")
    if configured and os.path.realpath(project_path) != os.path.realpath(configured):
        raise HTTPException(status_code=409, detail="project_path_mismatch")


def _store(request: Request):
    return request.app.state.runtime_store


def _registered_path_identity(value: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def _attempt_or_404(request: Request, attempt_id: str) -> dict[str, Any]:
    attempt = _store(request).get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="attempt_not_found")
    return attempt


def _resume_snapshot_reference(store: Any, attempt: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Return the immutable v1 ref and the attempt that owns its source state."""
    fork = store.get_fork_snapshot(attempt["attempt_id"])
    if isinstance(fork, dict):
        reference = fork.get("state_reference", {}).get("snapshot_ref") if isinstance(fork.get("state_reference"), dict) else None
        source_attempt = str(fork.get("state_reference", {}).get("source_attempt_id") or "") if isinstance(fork.get("state_reference"), dict) else ""
        return (dict(reference), source_attempt) if isinstance(reference, dict) and source_attempt else (None, "")
    checkpoints = store.list_checkpoint_metadata(attempt["attempt_id"])
    for checkpoint in reversed(checkpoints):
        metadata = checkpoint.get("metadata") if isinstance(checkpoint.get("metadata"), dict) else {}
        reference = metadata.get("snapshot_ref")
        if metadata.get("recovery_mode") == "resumable" and isinstance(reference, dict):
            return dict(reference), attempt["attempt_id"]
    return None, ""


def _validate_resume_snapshot(store: Any, attempt: dict[str, Any], config: dict[str, Any]) -> None:
    """Validate a real Supervisor snapshot before scheduling any recovered worker."""
    reference, source_attempt_id = _resume_snapshot_reference(store, attempt)
    if reference is None:
        return
    from sidecar.runtime.agent_runtime import _snapshot_artifact_refs_are_valid
    from sidecar.runtime.w1_supervisor_snapshot import SnapshotValidationError, load_w1_supervisor_snapshot_for_resume
    from sidecar.workflows.w1_agentic_adapter import build_supervisor_snapshot_identities

    lineage_id = str(reference.get("lineage_id") or "")
    reference_attempt_id = str(reference.get("attempt_id") or "")
    safe_id = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
    if not safe_id.fullmatch(lineage_id) or not safe_id.fullmatch(reference_attempt_id):
        raise ValueError("fork_snapshot_reference_identity_invalid")
    config["w1_supervisor_resume_snapshot_ref"] = reference
    config["snapshot_source_attempt_id"] = source_attempt_id
    config["w1_supervisor_staged_source_relative_path"] = (
        f"system/imports/{lineage_id}/attempts/{reference_attempt_id}/raw_source.txt"
    )
    source_identity, config_identity = build_supervisor_snapshot_identities(
        config, project_path=str(config.get("project_path") or store.project_root),
    )
    try:
        loaded = load_w1_supervisor_snapshot_for_resume(
            store.project_root,
            reference,
            expected_source_identity=source_identity,
            expected_config_identity=config_identity,
            artifact_receipt_validator=store.validate_w1_snapshot_artifact_receipt,
        )
    except SnapshotValidationError as exc:
        raise ValueError(f"fork_snapshot_validation_failed:{exc}") from exc
    snapshot = loaded["snapshot"]
    if snapshot.get("attempt_id") != source_attempt_id:
        raise ValueError("fork_snapshot_provenance_mismatch")
    checkpoint_id = str(snapshot.get("checkpoint_id") or "")
    source_checkpoint = next(
        (
            item for item in store.list_checkpoint_metadata(source_attempt_id)
            if item.get("checkpoint_id") == checkpoint_id
        ),
        None,
    )
    if source_checkpoint is None or source_checkpoint.get("parent_checkpoint_id") != snapshot.get("parent_checkpoint_id"):
        raise ValueError("fork_snapshot_parent_checkpoint_mismatch")
    fork = store.get_fork_snapshot(attempt["attempt_id"])
    if isinstance(fork, dict) and (
        fork.get("source_checkpoint_id") != checkpoint_id
        or fork.get("checkpoint_parent_id") != snapshot.get("parent_checkpoint_id")
    ):
        raise ValueError("fork_snapshot_parent_checkpoint_mismatch")
    # A fork owns no inherited tool calls. The immutable source attempt owns
    # the provider outcomes that produced the snapshot and must be clean too.
    unknown_summaries = store.list_unknown_call_summaries(source_attempt_id)
    actual_unknown = sorted(str(item.get("tool_call_id")) for item in unknown_summaries)
    declared_unknown = sorted(str(item) for item in snapshot.get("unknown_tool_call_ids", []))
    if actual_unknown != declared_unknown:
        raise ValueError("fork_snapshot_unknown_tool_calls_mismatch")
    pending_unknown = [
        item for item in unknown_summaries
        if item.get("decision_state") != "authorize_retry_once"
    ]
    if pending_unknown:
        raise ValueError("fork_snapshot_unknown_tool_calls_present")
    if unknown_summaries:
        # Authorizing a retry records consent only. The fenced provider runtime
        # consumes it atomically immediately before a replacement call.
        config["w1_authorized_unknown_call_ids"] = actual_unknown
        config["w1_authorized_unknown_decision_keys"] = sorted(
            str(item.get("decision_key")) for item in unknown_summaries
        )
    if not _snapshot_artifact_refs_are_valid(store.project_root, snapshot):
        raise ValueError("fork_snapshot_artifact_reference_invalid")
    budget = snapshot.get("budget_snapshot") if isinstance(snapshot.get("budget_snapshot"), dict) else {}
    spent = float(budget.get("spent_usd", 0.0) or 0.0)
    policy = config.get("budget_config") if isinstance(config.get("budget_config"), dict) else {}
    limit = policy.get("budget_limit_usd", policy.get("max_cost_usd"))
    if limit is not None and float(limit) < spent:
        raise ValueError("fork_snapshot_budget_incompatible")


class ResumeRequest(BaseModel):
    decision_id: str | None = None
    api_key: str | None = None
    provider: str | None = None
    model: str | None = None
    profile: str | None = None
    source_file_path: str | None = None
    source_hash: str | None = None
    budget_config: dict[str, Any] = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    attempt_id: str
    decision: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ForkRequest(BaseModel):
    checkpoint_id: str
    decision_id: str


class ControlRequest(BaseModel):
    """Optional caller key makes retries stable across renderer/network failures."""

    decision_id: str | None = None


def _control_decision_key(attempt: dict[str, Any], command: str, decision_id: str | None = None) -> str:
    if isinstance(decision_id, str) and decision_id.strip():
        return f"runtime:{command}:request:{decision_id.strip()}"
    # Legacy callers do not send a request ID.  The pre-transition version still
    # makes a later pause after a resume a distinct durable command.
    return f"runtime:{command}:transition:{attempt.get('status', '')}:{attempt.get('updated_at', '')}"


@router.get("/runs/recoverable")
async def recoverable_runs(request: Request) -> dict[str, Any]:
    return {"runs": _store(request).scan_recoverable_attempts()}


@router.get("/runs/{lineage_id}")
async def run_detail(lineage_id: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    run = store.get_run_by_lineage(lineage_id) or store.get_run(lineage_id)
    if run is not None:
        attempts = store.list_attempts(run["run_id"])
        for item in attempts:
            item["unknown_calls"] = store.list_unknown_call_summaries(item["attempt_id"])
            snapshot = store.get_fork_snapshot(item["attempt_id"])
            if snapshot is not None:
                item["fork_snapshot"] = snapshot
        return {"run": run, "attempts": attempts}
    attempt = store.get_attempt(lineage_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    snapshot = store.get_fork_snapshot(attempt["attempt_id"])
    detail = {
        "run": store.get_run(attempt["run_id"]),
        "attempt": attempt,
        "unknown_calls": store.list_unknown_call_summaries(attempt["attempt_id"]),
    }
    if snapshot is not None:
        detail["fork_snapshot"] = snapshot
    return detail


@router.get("/runs/{attempt_id}/events")
async def run_events(attempt_id: str, request: Request, afterSequence: int = 0) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    return {"events": _store(request).list_events(attempt_id, after_sequence=max(afterSequence, 0))}


@router.get("/runs/{attempt_id}/checkpoints")
async def checkpoints(attempt_id: str, request: Request) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    return {"checkpoints": _store(request).list_checkpoint_metadata(attempt_id)}


@router.post("/runs/{attempt_id}/pause")
async def pause(attempt_id: str, request: Request, body: ControlRequest | None = None) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
    if attempt["status"] in {"running", "interrupted", "waiting_human", "needs_credentials"}:
        try:
            control = _store(request).append_control_event(
                attempt_id, "pause", decision_key=_control_decision_key(attempt, "pause", body.decision_id if body else None),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # A delayed renderer or IPC retry must never re-apply an earlier pause
        # after a later resume has made this attempt runnable again.
        if control.get("idempotent"):
            current = _attempt_or_404(request, attempt_id)
            return {"attempt_id": attempt_id, "status": current["status"]}
        attempt = _store(request).set_attempt_status(attempt_id, "paused")
        from sidecar.routers.workflows import apply_runtime_command
        apply_runtime_command(attempt_id, "pause")
    return {"attempt_id": attempt_id, "status": attempt["status"]}


@router.post("/runs/{attempt_id}/cancel")
async def cancel(attempt_id: str, request: Request, body: ControlRequest | None = None) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
    if attempt["status"] != "cancelled":
        try:
            control = _store(request).append_control_event(
                attempt_id, "cancel", decision_key=_control_decision_key(attempt, "cancel", body.decision_id if body else None),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if control.get("idempotent"):
            current = _attempt_or_404(request, attempt_id)
            return {"attempt_id": attempt_id, "status": current["status"]}
        attempt = _store(request).set_attempt_status(attempt_id, "cancelled")
        from sidecar.routers.workflows import apply_runtime_command
        apply_runtime_command(attempt_id, "cancel")
    return {"attempt_id": attempt_id, "status": attempt["status"]}


@router.post("/runs/{attempt_id}/resume")
async def resume(attempt_id: str, body: ResumeRequest, request: Request) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
    fork_snapshot = _store(request).get_fork_snapshot(attempt_id)
    if fork_snapshot is not None and not fork_snapshot["resumable"]:
        raise HTTPException(status_code=409, detail=fork_snapshot["non_resumable_reason"])
    run = _store(request).get_run(attempt["run_id"])
    config = dict((run or {}).get("config", {}))
    registered_project = str(config.get("project_path") or "")
    registered_source = str(config.get("source_file_path") or "")
    registered_hash = str(config.get("source_hash") or "")
    configured_project = str(getattr(request.app.state, "project_path", "") or "")
    if not registered_project or _registered_path_identity(registered_project) != _registered_path_identity(configured_project):
        raise HTTPException(status_code=409, detail="registered_project_identity_mismatch")
    if not registered_source:
        raise HTTPException(status_code=409, detail="registered_source_identity_missing")
    if body.source_file_path is not None and _registered_path_identity(body.source_file_path) != _registered_path_identity(registered_source):
        raise HTTPException(status_code=409, detail="registered_source_path_mismatch")
    if body.source_hash is not None and body.source_hash != registered_hash:
        raise HTTPException(status_code=409, detail="registered_source_hash_mismatch")
    unknown_calls = _store(request).list_unknown_call_summaries(attempt_id)
    unauthorized = [
        call for call in unknown_calls
        if call.get("decision_state") != "authorize_retry_once"
    ]
    if unauthorized:
        raise HTTPException(status_code=409, detail={
            "code": "unknown_outcome_requires_human_confirmation",
            "unknown_calls": unauthorized,
        })
    config.update({key: value for key, value in {
        "provider": body.provider, "model": body.model, "profile": body.profile,
    }.items() if value is not None})
    if body.profile is not None:
        config["prompt_profile"] = body.profile
    context = config.get("context") if isinstance(config.get("context"), dict) else {}
    stored_budget = (
        config.get("budget_config")
        or config.get("budget_policy")
        or context.get("budget_policy")
        or {}
    )
    try:
        config["budget_config"] = _merge_budget_config(
            stored_budget,
            body.budget_config,
            model=str(config.get("model") or ""),
        )
    except W1BudgetPolicyError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    try:
        _validate_resume_snapshot(_store(request), attempt, config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    source_compatible = _store(request)._source_is_compatible(config)
    if not source_compatible:
        raise HTTPException(status_code=409, detail="source_incompatible")
    # A lost renderer response must not start another worker. A stable decision
    # ID is still recorded while already running so its duplicate receives the
    # same semantic result as the original delivery.
    if attempt["status"] == "running":
        if body.decision_id:
            try:
                control = _store(request).append_control_event(
                    attempt_id, "resume", {"requested": True},
                    decision_key=_control_decision_key(attempt, "resume", body.decision_id),
                )
            except (ValueError, KeyError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if control.get("idempotent"):
                return {
                    "attempt_id": attempt_id,
                    "status": "resumed",
                    "restarted": True,
                    "decision_id": body.decision_id,
                }
        return {
            "attempt_id": attempt_id,
            "status": "resumed",
            "restarted": False,
            "decision_id": body.decision_id,
            "already_running": True,
        }
    if not body.api_key:
        attempt = _store(request).set_attempt_status(attempt_id, "needs_credentials")
        return {"attempt_id": attempt_id, "status": "needs_credentials"}
    try:
        control = _store(request).append_control_event(
            attempt_id, "resume", {"requested": True},
            decision_key=_control_decision_key(attempt, "resume", body.decision_id),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if control.get("idempotent"):
        if attempt["status"] == "running":
            return {"attempt_id": attempt_id, "status": "resumed", "restarted": False, "decision_id": body.decision_id, "idempotent": True}
        raise HTTPException(status_code=409, detail="resume_request_already_recorded_retry_with_new_decision_id")
    _store(request).update_run_config(attempt["run_id"], config)
    # Record the intent first, then move to running before scheduling the task.
    # A concurrent/new delivery now observes running and cannot schedule a second
    # recovered worker; a failed launch returns this attempt to a retryable state.
    _store(request).set_attempt_status(attempt_id, "running")
    try:
        from sidecar.routers.workflows import resume_w1_attempt
        launched = await resume_w1_attempt(
            attempt_id=attempt_id, runtime_store=_store(request),
            runtime_owner_id=request.app.state.runtime_owner_id, api_key=body.api_key,
            persisted_config=config,
        )
    except (ValueError, KeyError) as exc:
        current = _attempt_or_404(request, attempt_id)
        if current["status"] == "running":
            _store(request).set_attempt_status(attempt_id, "paused")
        raise HTTPException(status_code=503, detail="resume_launch_failed_retry_with_new_decision_id") from exc
    return {"attempt_id": attempt_id, "status": "resumed", "restarted": launched, "decision_id": body.decision_id}


@router.post("/runs/{attempt_id}/fork")
async def fork(attempt_id: str, body: ForkRequest, request: Request) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    try:
        result = _store(request).fork_attempt(attempt_id, checkpoint_id=body.checkpoint_id, decision_id=body.decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    child_id = result["attempt"]["attempt_id"]
    return {**result, "parent_attempt_id": attempt_id, "fork_snapshot": _store(request).get_fork_snapshot(child_id)}


@router.post("/decisions/{decision_id}")
async def decision(decision_id: str, body: DecisionRequest, request: Request) -> dict[str, Any]:
    _attempt_or_404(request, body.attempt_id)
    try:
        if decision_id.startswith("retry_provider_call:"):
            if body.payload:
                raise ValueError("unknown_outcome_decision_payload_not_allowed")
            recorded = _store(request).record_unknown_call_decision(
                body.attempt_id, decision_id, body.decision
            )
            if body.decision == "cancel":
                from sidecar.routers.workflows import apply_runtime_command
                apply_runtime_command(body.attempt_id, "cancel")
        else:
            recorded = _store(request).record_human_decision(
                body.attempt_id, decision_id, body.decision, body.payload,
                decision_id=decision_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return recorded
