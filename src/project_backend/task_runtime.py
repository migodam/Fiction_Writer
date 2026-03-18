from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .contracts import RetrievalRequest, TaskRun, make_id, utc_now
from .project_repository import append_run_log, migrate_project, write_artifact, write_proposals, write_task_request, write_task_run
from .rag_store import query_rag


def create_task_request(root_path: str | Path, task_request_json: Dict[str, Any]) -> Dict[str, Any]:
    migrate_project(root_path)
    payload = {
        "id": task_request_json.get("id", make_id("task")),
        "createdAt": task_request_json.get("createdAt", utc_now()),
        "status": task_request_json.get("status", "queued"),
        **task_request_json,
    }
    return write_task_request(root_path, payload)


def start_task_run(root_path: str | Path, task_request_id: str, executor: str = "local-cli") -> Dict[str, Any]:
    migrate_project(root_path)
    run = TaskRun(
        id=make_id("run"),
        taskRequestId=task_request_id,
        status="running",
        attempt=1,
        executor=executor,
        adapter=f"{executor}-placeholder-adapter",
        startedAt=utc_now(),
        heartbeatAt=utc_now(),
        summary=f"Started {task_request_id} with {executor}.",
    )
    payload = write_task_run(root_path, run)
    append_run_log(root_path, run.id, {"at": utc_now(), "event": "run_started", "taskRequestId": task_request_id, "executor": executor})
    return payload


def append_run_log_event(root_path: str | Path, run_id: str, log_event_json: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"at": utc_now(), **log_event_json}
    return append_run_log(root_path, run_id, payload)


def write_artifact_payload(root_path: str | Path, run_id: str, artifact_json: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    artifact_payload = {"id": artifact_json.get("id", make_id("artifact")), "taskRunId": run_id, **artifact_json}
    return write_artifact(root_path, run_id, artifact_payload, payload)


def submit_proposals(root_path: str | Path, proposal_batch_json: Dict[str, Any]) -> Any:
    proposals = proposal_batch_json.get("proposals", proposal_batch_json)
    return write_proposals(root_path, proposals)


def query_rag_runtime(root_path: str | Path, retrieval_request_json: Dict[str, Any]) -> Dict[str, Any]:
    request = RetrievalRequest(
        id=retrieval_request_json.get("id", make_id("retrieval")),
        query=retrieval_request_json["query"],
        scope=retrieval_request_json.get("scope", {}),
        filters=retrieval_request_json.get("filters", {}),
        topK=int(retrieval_request_json.get("topK", 5)),
        includeNeighborChunks=bool(retrieval_request_json.get("includeNeighborChunks", False)),
    )
    return query_rag(root_path, request)
