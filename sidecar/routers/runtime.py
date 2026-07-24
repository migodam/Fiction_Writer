from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/runtime")


def _merge_budget_config(existing: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    """Keep persisted limits when a resume body omits them and never raise a cap."""
    merged = {**existing, **requested}
    old_max, new_max = existing.get("max_cost_usd"), requested.get("max_cost_usd")
    if isinstance(old_max, (int, float)) and not isinstance(old_max, bool):
        if not isinstance(new_max, (int, float)) or isinstance(new_max, bool):
            merged["max_cost_usd"] = old_max
        else:
            merged["max_cost_usd"] = min(float(old_max), float(new_max))
    for key in ("fail_on_unknown_pricing", "fail_on_missing_usage"):
        if existing.get(key) is True:
            merged[key] = True
    return merged


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


class ResumeRequest(BaseModel):
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
        return {"run": run, "attempts": attempts}
    attempt = store.get_attempt(lineage_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {
        "run": store.get_run(attempt["run_id"]),
        "attempt": attempt,
        "unknown_calls": store.list_unknown_call_summaries(attempt["attempt_id"]),
    }


@router.get("/runs/{attempt_id}/events")
async def run_events(attempt_id: str, request: Request, afterSequence: int = 0) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    return {"events": _store(request).list_events(attempt_id, after_sequence=max(afterSequence, 0))}


@router.get("/runs/{attempt_id}/checkpoints")
async def checkpoints(attempt_id: str, request: Request) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    return {"checkpoints": _store(request).list_checkpoint_metadata(attempt_id)}


@router.post("/runs/{attempt_id}/pause")
async def pause(attempt_id: str, request: Request) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
    if attempt["status"] not in {"cancelled", "completed", "failed"}:
        try:
            _store(request).append_control_event(attempt_id, "pause", decision_key="runtime:pause")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        attempt = _store(request).set_attempt_status(attempt_id, "paused")
        from sidecar.routers.workflows import apply_runtime_command
        apply_runtime_command(attempt_id, "pause")
    return {"attempt_id": attempt_id, "status": attempt["status"]}


@router.post("/runs/{attempt_id}/cancel")
async def cancel(attempt_id: str, request: Request) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
    if attempt["status"] != "cancelled":
        try:
            _store(request).append_control_event(attempt_id, "cancel", decision_key="runtime:cancel")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        attempt = _store(request).set_attempt_status(attempt_id, "cancelled")
        from sidecar.routers.workflows import apply_runtime_command
        apply_runtime_command(attempt_id, "cancel")
    return {"attempt_id": attempt_id, "status": attempt["status"]}


@router.post("/runs/{attempt_id}/resume")
async def resume(attempt_id: str, body: ResumeRequest, request: Request) -> dict[str, Any]:
    attempt = _attempt_or_404(request, attempt_id)
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
    if body.budget_config:
        config["budget_config"] = _merge_budget_config(dict(config.get("budget_config") or {}), body.budget_config)
    source_compatible = _store(request)._source_is_compatible(config)
    _store(request).update_run_config(attempt["run_id"], config)
    if not source_compatible:
        raise HTTPException(status_code=409, detail="source_incompatible")
    if not body.api_key:
        attempt = _store(request).set_attempt_status(attempt_id, "needs_credentials")
        return {"attempt_id": attempt_id, "status": "needs_credentials"}
    try:
        from sidecar.routers.workflows import resume_w1_attempt
        launched = await resume_w1_attempt(
            attempt_id=attempt_id, runtime_store=_store(request),
            runtime_owner_id=request.app.state.runtime_owner_id, api_key=body.api_key,
            persisted_config=config,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        _store(request).append_control_event(
            attempt_id, "resume", {"requested": True}, decision_key="runtime:resume",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    attempt = _store(request).set_attempt_status(attempt_id, "running")
    return {"attempt_id": attempt_id, "status": "resumed", "restarted": launched}


@router.post("/runs/{attempt_id}/fork")
async def fork(attempt_id: str, body: ForkRequest, request: Request) -> dict[str, Any]:
    _attempt_or_404(request, attempt_id)
    try:
        result = _store(request).fork_attempt(attempt_id, checkpoint_id=body.checkpoint_id, decision_id=body.decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**result, "parent_attempt_id": attempt_id}


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
