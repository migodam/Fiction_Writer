from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from sidecar.main import create_app
from sidecar.runtime.agent_runtime import RuntimeStore


def test_import_all_defaults_to_supervisor_even_when_legacy_flag_is_false(tmp_path, monkeypatch):
    from sidecar.routers import workflows

    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFixture", encoding="utf-8")
    captured: list[dict] = []

    async def fake_run(_session_id: str, config: dict) -> None:
        captured.append(config)

    monkeypatch.setattr(workflows, "_run_w1", fake_run)
    with TestClient(create_app(str(tmp_path))) as client:
        response = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path),
            "source_file_path": str(source),
            "import_mode": "import_all",
            "prompt_profile": "balanced",
            "use_supervisor": False,
        })
        execution_mode = client.get(
            "/workflow/w1/status", params={"session_id": response.json()["session_id"]}
        ).json()["execution_mode"]

    assert response.status_code == 200
    assert captured
    config = captured[0]
    assert config["execution_mode"] == "supervisor"
    assert config["use_supervisor"] is True
    assert config["use_orchestrator"] is True
    assert execution_mode == "supervisor"


def test_compatibility_mode_is_explicit_and_content_only_stays_deterministic(tmp_path, monkeypatch):
    from sidecar.routers import workflows

    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFixture", encoding="utf-8")
    captured: list[dict] = []

    async def fake_run(_session_id: str, config: dict) -> None:
        captured.append(config)

    monkeypatch.setattr(workflows, "_run_w1", fake_run)
    with TestClient(create_app(str(tmp_path))) as client:
        compatibility = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path), "source_file_path": str(source),
            "import_mode": "import_all", "compatibility_mode": True,
        })
        content = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path), "source_file_path": str(source),
            "import_mode": "import_content_only",
        })
        compatibility_mode = client.get(
            "/workflow/w1/status", params={"session_id": compatibility.json()["session_id"]}
        ).json()["execution_mode"]

    assert compatibility.status_code == content.status_code == 200
    assert captured[0]["execution_mode"] == "compatibility_direct"
    assert captured[0]["use_supervisor"] is False
    assert captured[1]["execution_mode"] == "content_only"
    assert captured[1]["use_supervisor"] is False
    assert compatibility_mode == "compatibility_direct"


def test_explicit_product_supervisor_stream_is_wrapped_by_v2_observer(tmp_path, monkeypatch):
    from sidecar.supervisor import policy
    from sidecar.workflows import w1_import

    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="supervisor-lineage", thread_id="supervisor-thread")
    attempt = store.create_attempt(run["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "observer", ttl_seconds=60)

    async def fake_supervisor(_project_path: str, _config: dict):
        for node in ("validate_file", "extract_windows", "reduce_repair", "architect_timeline", "qa_review", "judge_import", "proposal_write", "done"):
            yield {"current_node": node, "progress": 1.0, "errors": []}

    monkeypatch.setattr(policy, "run_supervisor_streaming", fake_supervisor)

    async def collect():
        return [item async for item in w1_import.run_streaming(str(tmp_path), {
            "import_mode": "import_all", "execution_mode": "supervisor",
            "runtime_store": store, "attempt_id": attempt["attempt_id"],
            "runtime_owner_id": "observer", "runtime_fence_token": lease["fence_token"],
        })]

    assert len(asyncio.run(collect())) == 8
    events = store.list_events(attempt["attempt_id"])
    assert any(event["contract_version"] == "AgentEvent/v1" for event in events)
