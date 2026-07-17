from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import sys
from uuid import uuid4
from pathlib import Path

import uvicorn
from fastapi import FastAPI

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidecar.routers import metadata, orchestrator, prompts, proposals, runtime, status, workflows
from sidecar.runtime import RuntimeStore
from sidecar.workflows.w1_recovery import discover_legacy_progress


def _register_legacy_w1_recovery(project_path: str, runtime_store: RuntimeStore) -> None:
    legacy = discover_legacy_progress(project_path)
    if legacy.get("status") != "ok" or runtime_store.get_run_by_lineage(legacy["lineage_id"]) is not None:
        return
    run = runtime_store.create_run(
        workflow_id="W1", lineage_id=legacy["lineage_id"],
        thread_id=f"w1-{legacy['attempt_id']}",
        config={**legacy["config"], "lineage_id": legacy["lineage_id"]},
    )
    attempt = runtime_store.create_attempt(run["run_id"], attempt_id=legacy["attempt_id"])
    runtime_store.set_attempt_status(attempt["attempt_id"], "interrupted")


def _close_workflow_checkpointers(project_path: str) -> None:
    """Close every module-local project saver; LangGraph state stays in its own DB."""
    from sidecar.workflows import (
        w0_orchestrator, w1_import, w2_manuscript_sync, w3_writing_assistant,
        w4_consistency_check, w5_simulation, w6_beta_reader, w7_metadata_ingestion,
    )

    for workflow in (
        w0_orchestrator, w1_import, w2_manuscript_sync, w3_writing_assistant,
        w4_consistency_check, w5_simulation, w6_beta_reader, w7_metadata_ingestion,
    ):
        workflow.close_project_checkpointer(project_path)


def create_app(project_path: str = "") -> FastAPI:
    resolved_project_path = str(Path(project_path).resolve()) if project_path else ""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if resolved_project_path:
            _close_workflow_checkpointers(resolved_project_path)

    app = FastAPI(title="Narrative IDE Sidecar", version="0.1.0", lifespan=lifespan)
    app.state.project_path = resolved_project_path
    app.state.runtime_owner_id = f"sidecar-{uuid4()}"
    if resolved_project_path:
        app.state.runtime_store = RuntimeStore(resolved_project_path)
        app.state.runtime_store.invalidate_leases_for_restart()
        _register_legacy_w1_recovery(resolved_project_path, app.state.runtime_store)

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    app.include_router(workflows.router)
    app.include_router(status.router)
    app.include_router(runtime.router)
    app.include_router(proposals.router, prefix="/proposals")
    app.include_router(metadata.router, prefix="/metadata")
    app.include_router(orchestrator.router, prefix="/orchestrator")
    app.include_router(prompts.router, prefix="/prompts")
    return app


app = create_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Narrative IDE Sidecar")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--project-path", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(create_app(args.project_path), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
