from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .contracts import TaskArtifact, TaskRequest, TaskRun, to_dict


SCHEMA_VERSION = 4


def _project_path(root_path: str | Path) -> Path:
    return Path(root_path)


def _read_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def migrate_project(root_path: str | Path) -> Dict[str, Any]:
    root = _project_path(root_path)
    system_dir = root / "system"
    schema_dir = system_dir / "schema"
    tasks_dir = system_dir / "tasks"
    runs_dir = system_dir / "runs"
    prompts_dir = system_dir / "prompts" / "templates"
    imports_dir = system_dir / "imports" / "staging"
    rag_docs_dir = system_dir / "rag" / "documents"
    rag_chunks_dir = system_dir / "rag" / "chunks"
    rag_indexes_dir = system_dir / "rag" / "indexes"
    scripts_dir = root / "entities" / "scripts"
    storyboards_dir = root / "entities" / "storyboards"
    video_dir = root / "exports" / "video"

    for directory in [
        schema_dir,
        tasks_dir,
        runs_dir / "logs",
        prompts_dir,
        imports_dir,
        rag_docs_dir,
        rag_chunks_dir,
        rag_indexes_dir,
        scripts_dir,
        storyboards_dir,
        video_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    schema_path = schema_dir / "schema.json"
    schema = _read_json(schema_path, {})
    schema.update(
        {
            "schemaVersion": SCHEMA_VERSION,
            "capabilities": {
                "import": True,
                "rag": True,
                "scripts": True,
                "videoWorkflow": True,
                "promptTemplates": True,
            },
            "storageBackends": {
                "canonical": "project-folder-json",
                "rag": "project-folder-keyword-index",
            },
            "futureBackends": ["sqlite", "embedding-provider", "video-provider"],
        }
    )
    _write_json(schema_path, schema)

    defaults = {
        system_dir / "prompts" / "registry.json": [],
        system_dir / "imports" / "jobs.json": [],
        system_dir / "rag" / "manifest.json": {
            "activeBackend": "keyword",
            "futureBackends": ["embedding"],
            "storageBackend": "project-folder-keyword-index",
        },
        system_dir / "rag" / "retrieval-history.json": [],
        system_dir / "rag" / "indexes" / "keyword-index.json": {"backend": "keyword", "documents": [], "chunks": []},
        runs_dir / "logs.json": [],
        runs_dir / "runs.json": _read_json(runs_dir / "runs.json", []),
        runs_dir / "artifacts.json": _read_json(runs_dir / "artifacts.json", []),
        tasks_dir / "requests.json": _read_json(tasks_dir / "requests.json", []),
        system_dir / "inbox.json": _read_json(system_dir / "inbox.json", []),
        system_dir / "history.json": _read_json(system_dir / "history.json", []),
        system_dir / "issues.json": _read_json(system_dir / "issues.json", []),
    }
    for path, payload in defaults.items():
        if not path.exists():
            _write_json(path, payload)

    project_index_path = root / "project.json"
    project_index = _read_json(project_index_path, {"metadata": {}, "counts": {}})
    project_index.setdefault("metadata", {})["schemaVersion"] = SCHEMA_VERSION
    _write_json(project_index_path, project_index)
    return schema


def load_project(root_path: str | Path) -> Dict[str, Any]:
    root = _project_path(root_path)
    migrate_project(root)
    system_dir = root / "system"
    return {
        "project": _read_json(root / "project.json", {"metadata": {}, "counts": {}}),
        "task_requests": _read_json(system_dir / "tasks" / "requests.json", []),
        "task_runs": _read_json(system_dir / "runs" / "runs.json", []),
        "task_artifacts": _read_json(system_dir / "runs" / "artifacts.json", []),
        "task_run_logs": _read_json(system_dir / "runs" / "logs.json", []),
        "proposals": _read_json(system_dir / "inbox.json", []),
        "issues": _read_json(system_dir / "issues.json", []),
        "import_jobs": _read_json(system_dir / "imports" / "jobs.json", []),
        "prompt_templates": list_prompt_templates(root),
        "rag_manifest": _read_json(system_dir / "rag" / "manifest.json", {}),
        "rag_retrieval_history": _read_json(system_dir / "rag" / "retrieval-history.json", []),
    }


def write_task_request(root_path: str | Path, task_request: TaskRequest | Dict[str, Any]) -> Dict[str, Any]:
    root = _project_path(root_path)
    migrate_project(root)
    path = root / "system" / "tasks" / "requests.json"
    payload = to_dict(task_request)
    requests = _read_json(path, [])
    requests.insert(0, payload)
    _write_json(path, requests)
    return payload


def write_task_run(root_path: str | Path, task_run: TaskRun | Dict[str, Any]) -> Dict[str, Any]:
    root = _project_path(root_path)
    migrate_project(root)
    path = root / "system" / "runs" / "runs.json"
    payload = to_dict(task_run)
    runs = _read_json(path, [])
    runs.insert(0, payload)
    _write_json(path, runs)
    return payload


def write_artifact(root_path: str | Path, task_run_id: str, artifact: TaskArtifact | Dict[str, Any], payload: Any | None = None) -> Dict[str, Any]:
    root = _project_path(root_path)
    migrate_project(root)
    artifact_path = root / "system" / "runs" / "artifacts.json"
    artifact_payload = to_dict(artifact)
    artifact_payload["taskRunId"] = task_run_id
    artifacts = _read_json(artifact_path, [])
    artifacts.insert(0, artifact_payload)
    _write_json(artifact_path, artifacts)
    if payload is not None and artifact_payload.get("path"):
        _write_json(root / artifact_payload["path"], payload)
    return artifact_payload


def append_run_log(root_path: str | Path, run_id: str, log_event_json: Dict[str, Any]) -> Dict[str, Any]:
    root = _project_path(root_path)
    migrate_project(root)
    log_path = root / "system" / "runs" / "logs" / f"{run_id}.jsonl"
    _append_jsonl(log_path, log_event_json)
    index_path = root / "system" / "runs" / "logs.json"
    entries = _read_json(index_path, [])
    existing = next((entry for entry in entries if entry["taskRunId"] == run_id), None)
    if existing:
        existing["entryCount"] += 1
    else:
        entries.append({"taskRunId": run_id, "path": str(log_path.relative_to(root)).replace("\\", "/"), "entryCount": 1})
    _write_json(index_path, entries)
    return log_event_json


def write_proposals(root_path: str | Path, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    root = _project_path(root_path)
    migrate_project(root)
    inbox_path = root / "system" / "inbox.json"
    current = _read_json(inbox_path, [])
    current = proposals + current
    _write_json(inbox_path, current)
    return proposals


def list_prompt_templates(root_path: str | Path) -> List[Dict[str, Any]]:
    root = _project_path(root_path)
    templates_dir = root / "system" / "prompts" / "templates"
    if not templates_dir.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(templates_dir.glob("*.json"))]
