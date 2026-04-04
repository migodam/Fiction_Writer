from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidecar.routers import metadata, orchestrator, proposals, status, workflows


def create_app(project_path: str = "") -> FastAPI:
    app = FastAPI(title="Narrative IDE Sidecar", version="0.1.0")
    app.state.project_path = project_path

    app.include_router(workflows.router)
    app.include_router(status.router)
    app.include_router(proposals.router, prefix="/proposals")
    app.include_router(metadata.router, prefix="/metadata")
    app.include_router(orchestrator.router, prefix="/orchestrator")
    return app


app = create_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Narrative IDE Sidecar")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--project-path", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app.state.project_path = args.project_path
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
