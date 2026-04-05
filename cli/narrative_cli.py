"""Narrative IDE CLI — Mode 1.

Talks directly to the sidecar HTTP API (no Electron).
Discovers or spawns the sidecar on first command.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import click
import requests


# ── Sidecar discovery ─────────────────────────────────────────────────────────

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_or_spawn_sidecar(project_path: str) -> int:
    """Return the port of a running sidecar, spawning one if necessary."""
    project_id = Path(project_path.rstrip("/\\")).name
    pid_file = Path.home() / ".narrative-ide" / "processes" / f"{project_id}.json"

    # Try existing sidecar
    if pid_file.exists():
        try:
            info = json.loads(pid_file.read_text())
            port = info["port"]
            resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=2)
            if resp.status_code == 200:
                return port
        except Exception:
            pass  # Fall through to spawn

    # Spawn new sidecar
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "sidecar.main", "--port", str(port), "--project-path", project_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Write PID file
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(json.dumps({"pid": proc.pid, "port": port, "projectPath": project_path}))

    # Wait for health check
    for _ in range(10):
        time.sleep(0.5)
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=2)
            if resp.status_code == 200:
                return port
        except Exception:
            continue

    raise RuntimeError(f"Sidecar failed to start on port {port}")


def _poll_workflow_status(port: int, workflow: str, session_id: str | None = None) -> dict:
    """Poll workflow status until done/error. Print progress. Return final status dict."""
    if workflow == "orchestrator":
        url = f"http://127.0.0.1:{port}/orchestrator/status"
        params = {"session_id": session_id or ""}
    elif workflow == "metadata":
        # Metadata doesn't have a separate status endpoint yet
        return {"status": "done"}
    else:
        url = f"http://127.0.0.1:{port}/workflow/{workflow.lower()}/status"
        params = {}

    terminal_statuses = {"done", "error", "completed", "failed", "cancelled"}
    while True:
        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            status = data.get("status", "")
            progress = data.get("progress", 0.0)
            click.echo(f"  [{workflow}] status={status} progress={progress:.0%}", err=True)
            if status in terminal_statuses:
                return data
        except Exception as e:
            click.echo(f"  [{workflow}] poll error: {e}", err=True)
        time.sleep(2)


# ── Dispatch table ─────────────────────────────────────────────────────────────

_WORKFLOW_ENDPOINTS: dict[str, tuple[str, str]] = {
    "import":      ("/workflow/w1/start", "W1"),
    "write":       ("/workflow/w3/start", "W3"),
    "check":       ("/workflow/w4/start", "W4"),
    "simulate":    ("/workflow/w5/start", "W5"),
    "beta-read":   ("/workflow/w6/start", "W6"),
    "ingest":      ("/metadata/ingest",   "metadata"),
    "orchestrate": ("/orchestrator/start", "orchestrator"),
}


def run_command(command_name: str, project_path: str, **kwargs) -> str:  # noqa: ANN001
    """Discover sidecar, call the right endpoint, poll until done, return summary."""
    port = _get_or_spawn_sidecar(project_path)

    if command_name == "status":
        resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=5)
        return json.dumps(resp.json(), indent=2)

    if command_name == "proposals-list":
        resp = requests.get(f"http://127.0.0.1:{port}/proposals/", timeout=5)
        return json.dumps(resp.json(), indent=2)

    if command_name == "proposals-accept":
        resp = requests.post(f"http://127.0.0.1:{port}/proposals/{kwargs['id']}/accept", timeout=5)
        return json.dumps(resp.json(), indent=2)

    if command_name == "proposals-reject":
        resp = requests.post(f"http://127.0.0.1:{port}/proposals/{kwargs['id']}/reject", timeout=5)
        return json.dumps(resp.json(), indent=2)

    endpoint, workflow_label = _WORKFLOW_ENDPOINTS[command_name]

    # Build payload from kwargs
    payload = {"project_path": project_path}
    if command_name == "import":
        payload["source_file_path"] = kwargs["file"]
    elif command_name == "write":
        payload.update({"scene_id": kwargs["scene"], "task": kwargs["task"],
                         "hitl_mode": kwargs["mode"], "api_key": "", "model": "claude-sonnet-4-6",
                         "endpoint": "https://api.anthropic.com"})
    elif command_name == "check":
        payload.update({"scope": kwargs["scope"], "target_id": kwargs["target"]})
    elif command_name == "simulate":
        payload.update({
            "scenario_variable": kwargs["scenario"],
            "affected_chapter_ids": [c.strip() for c in kwargs["chapters"].split(",")],
            "engines_selected": [e.strip() for e in kwargs["engines"].split(",")],
        })
    elif command_name == "beta-read":
        payload.update({
            "persona_id": kwargs["persona"],
            "target_chapter_ids": [c.strip() for c in kwargs["chapters"].split(",")],
        })
    elif command_name == "ingest":
        payload.update({"source_file_path": kwargs["file"], "file_type": kwargs["type"]})
    elif command_name == "orchestrate":
        payload.update({"goal": kwargs["goal"], "auto_apply_threshold": kwargs["auto_apply_threshold"]})

    resp = requests.post(f"http://127.0.0.1:{port}{endpoint}", json=payload, timeout=30)
    resp.raise_for_status()
    start_data = resp.json()
    session_id = start_data.get("session_id")

    click.echo(f"Started {workflow_label} session={session_id}", err=True)

    # Poll for completion
    final = _poll_workflow_status(port, workflow_label, session_id)
    return json.dumps(final, indent=2)


# ── CLI definition ─────────────────────────────────────────────────────────────

@click.group()
@click.option("--project", required=True, type=click.Path(), help="Path to the project directory")
@click.pass_context
def cli(ctx: click.Context, project: str) -> None:
    """Narrative IDE CLI — interact with the sidecar directly."""
    ctx.ensure_object(dict)
    ctx.obj["project"] = project


@cli.command("import")
@click.option("--file", required=True, type=click.Path(), help="Source file path")
@click.pass_context
def import_novel(ctx: click.Context, file: str) -> None:
    """Import a novel manuscript into the project."""
    click.echo(run_command("import", ctx.obj["project"], file=file))


@cli.command("write")
@click.option("--scene", required=True, help="Scene ID to write for")
@click.option("--task", default="continue", help="Writing task description")
@click.option("--mode", default="direct_output", type=click.Choice(["direct_output", "three_options"]))
@click.pass_context
def write(ctx: click.Context, scene: str, task: str, mode: str) -> None:
    """Generate prose for a scene using the Writing Assistant."""
    click.echo(run_command("write", ctx.obj["project"], scene=scene, task=task, mode=mode))


@cli.command("check")
@click.option("--scope", required=True, type=click.Choice(["scene", "chapter", "full"]))
@click.option("--target", required=True, help="Target ID (scene/chapter ID or 'all')")
@click.pass_context
def check(ctx: click.Context, scope: str, target: str) -> None:
    """Run a consistency check on the project."""
    click.echo(run_command("check", ctx.obj["project"], scope=scope, target=target))


@cli.command("simulate")
@click.option("--scenario", required=True, help="Scenario variable to simulate")
@click.option("--chapters", required=True, help="Comma-separated chapter IDs")
@click.option("--engines", required=True, help="Comma-separated engine names (scenario,character,author,reader,logic)")
@click.pass_context
def simulate(ctx: click.Context, scenario: str, chapters: str, engines: str) -> None:
    """Run the Simulation Engine on a scenario."""
    click.echo(run_command("simulate", ctx.obj["project"], scenario=scenario, chapters=chapters, engines=engines))


@cli.command("beta-read")
@click.option("--persona", required=True, help="Persona ID")
@click.option("--chapters", required=True, help="Comma-separated chapter IDs")
@click.pass_context
def beta_read(ctx: click.Context, persona: str, chapters: str) -> None:
    """Run a beta reader persona over target chapters."""
    click.echo(run_command("beta-read", ctx.obj["project"], persona=persona, chapters=chapters))


@cli.command("ingest")
@click.option("--file", required=True, type=click.Path(), help="Source file path")
@click.option("--type", "file_type", default="other",
              type=click.Choice(["novel", "script", "news", "essay", "draft", "other"]))
@click.pass_context
def ingest(ctx: click.Context, file: str, file_type: str) -> None:
    """Ingest a reference file into the metadata store."""
    click.echo(run_command("ingest", ctx.obj["project"], file=file, type=file_type))


@cli.command("orchestrate")
@click.option("--goal", required=True, help="Natural language goal for the Orchestrator")
@click.option("--auto-apply-threshold", default=0.85, type=float)
@click.pass_context
def orchestrate(ctx: click.Context, goal: str, auto_apply_threshold: float) -> None:
    """Run the Orchestrator to achieve a high-level narrative goal."""
    click.echo(run_command("orchestrate", ctx.obj["project"], goal=goal, auto_apply_threshold=auto_apply_threshold))


@cli.command("status")
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show sidecar and workflow status."""
    click.echo(run_command("status", ctx.obj["project"]))


@cli.group("proposals")
def proposals_group() -> None:
    """Manage pending proposals in the inbox."""


@proposals_group.command("list")
@click.pass_context
def proposals_list(ctx: click.Context) -> None:
    """List all pending proposals."""
    click.echo(run_command("proposals-list", ctx.obj["project"]))


@proposals_group.command("accept")
@click.argument("id")
@click.pass_context
def proposals_accept(ctx: click.Context, id: str) -> None:
    """Accept a proposal by ID."""
    click.echo(run_command("proposals-accept", ctx.obj["project"], id=id))


@proposals_group.command("reject")
@click.argument("id")
@click.pass_context
def proposals_reject(ctx: click.Context, id: str) -> None:
    """Reject a proposal by ID."""
    click.echo(run_command("proposals-reject", ctx.obj["project"], id=id))


if __name__ == "__main__":
    cli()
