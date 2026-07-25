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


def test_product_start_applies_non_empty_budget_to_legacy_client_and_safe_config(tmp_path, monkeypatch):
    """An Electron client that predates budget_policy must never create an unlimited run."""
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
            "model": "deepseek-v4-flash",
            "api_key": "never-persist-this",
        })
        attempt = client.app.state.runtime_store.get_attempt(response.json()["session_id"])
        run = client.app.state.runtime_store.get_run(attempt["run_id"])
        status = client.get("/workflow/w1/status", params={"session_id": response.json()["session_id"]}).json()

    assert response.status_code == 200
    expected = {
        "max_cost_usd": 3.0,
        "max_calls": 100,
        "max_input_tokens": 3_000_000,
        "max_output_tokens": 500_000,
        "max_total_tokens": 3_500_000,
        "fail_on_unknown_pricing": True,
        "fail_on_missing_usage": True,
    }
    assert response.json()["budget_policy"] == expected
    assert status["budget_policy"] == expected
    assert captured[0]["budget_policy"] == expected
    assert captured[0]["context"]["budget_policy"] == expected
    assert run["config"]["budget_config"] == expected
    assert "api_key" not in run["config"]


def test_product_start_rejects_unbounded_or_invalid_budget_requests(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("Chapter 1\nFixture", encoding="utf-8")

    with TestClient(create_app(str(tmp_path))) as client:
        over_flash = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path), "source_file_path": str(source),
            "model": "deepseek-v4-flash", "budget_policy": {"max_cost_usd": 3.01},
        })
        negative = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path), "source_file_path": str(source),
            "budget_policy": {"max_calls": -1},
        })
        pro = client.post("/workflow/w1/start", json={
            "project_path": str(tmp_path), "source_file_path": str(source),
            "model": "deepseek-v4-pro", "budget_policy": {"max_cost_usd": 8.0, "max_calls": 12},
        })

    assert over_flash.status_code == 422
    assert over_flash.json()["detail"] == "budget_max_cost_exceeds_model_cap"
    assert negative.status_code == 422
    assert pro.status_code == 200
    assert pro.json()["budget_policy"]["max_cost_usd"] == 8.0
    assert pro.json()["budget_policy"]["max_calls"] == 12


def test_proposal_gate_is_waiting_human_not_canonical_import_complete(tmp_path, monkeypatch):
    from sidecar.routers import workflows
    from sidecar.workflows import w1_import
    from sidecar.workflows import w1_run_events as events

    store = RuntimeStore(tmp_path)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    session_id = attempt["attempt_id"]
    lease = store.acquire_lease(session_id, "proposal-gate-worker", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, session_id, "proposal-gate-worker", lease["fence_token"])
    workflows._w1_sessions[session_id] = {"status": "running", "progress": 0.8}

    async def proposal_gate_stream(_project_path: str, _config: dict):
        yield {
            "current_node": "proposal_write",
            "progress": 1.0,
            "errors": [],
            "converge_status": "awaiting_acceptance",
        }

    monkeypatch.setattr(w1_import, "run_streaming", proposal_gate_stream)
    asyncio.run(workflows._run_w1(session_id, {
        "project_path": str(tmp_path),
        "runtime_store": store,
        "runtime_owner_id": "proposal-gate-worker",
        "runtime_fence_token": lease["fence_token"],
    }))

    assert workflows._w1_sessions[session_id]["status"] == "awaiting_acceptance"
    assert store.get_attempt(session_id)["status"] == "waiting_human"
    assert any("canonical import has not run" in event["message"] for event in events.list_events(session_id))
    workflows._w1_sessions.pop(session_id, None)
    events.clear_session(session_id)


def test_provider_402_stops_the_attempt_as_budget_exhausted(tmp_path, monkeypatch):
    from sidecar.routers import workflows
    from sidecar.workflows import w1_import
    from sidecar.workflows import w1_run_events as events

    store = RuntimeStore(tmp_path)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    session_id = attempt["attempt_id"]
    lease = store.acquire_lease(session_id, "budget-stop-worker", ttl_seconds=60)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, session_id, "budget-stop-worker", lease["fence_token"])
    workflows._w1_sessions[session_id] = {"status": "running", "progress": 0.5}

    async def exhausted_stream(_project_path: str, _config: dict):
        if False:
            yield {}
        raise RuntimeError("402: Insufficient balance")

    monkeypatch.setattr(w1_import, "run_streaming", exhausted_stream)
    asyncio.run(workflows._run_w1(session_id, {
        "project_path": str(tmp_path),
        "runtime_store": store,
        "runtime_owner_id": "budget-stop-worker",
        "runtime_fence_token": lease["fence_token"],
    }))

    assert workflows._w1_sessions[session_id]["status"] == "error"
    assert workflows._w1_sessions[session_id]["converge_status"] == "budget_exhausted"
    assert store.get_attempt(session_id)["status"] == "failed"
    assert any(event["phase"] == "budget_stop" for event in events.list_events(session_id))
    workflows._w1_sessions.pop(session_id, None)
    events.clear_session(session_id)


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
