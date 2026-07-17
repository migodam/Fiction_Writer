import asyncio
import json
import sqlite3
import time

import pytest

from sidecar.runtime.agent_runtime import LeaseLostError, RuntimeStore
from sidecar.routers import workflows as workflow_router
from sidecar.workflows import w1_import
from sidecar.workflows import w1_run_events as events


class _Response:
    content = '{"ok":true}'
    usage_metadata = {"input_tokens": 11, "output_tokens": 7}
    response_metadata = {}


class _StatusError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"provider status {status_code}")


class _FakeLlm:
    model = "deepseek-chat"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _bound_runtime(tmp_path, session_id: str):
    store = RuntimeStore(tmp_path)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "test-worker", ttl_seconds=30)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, attempt["attempt_id"], "test-worker", lease["fence_token"])
    return store, attempt


def test_append_and_list_events_preserves_order():
    session_id = "test-events-order"
    events.clear_session(session_id)

    events.append_event(session_id, {"phase": "planning", "status": "start", "message": "one"})
    events.append_event(session_id, {"phase": "extracting", "status": "success", "message": "two"})

    listed = events.list_events(session_id)
    assert [entry["id"] for entry in listed] == [1, 2]
    assert [entry["message"] for entry in listed] == ["one", "two"]
    assert events.list_events(session_id, after=1)[0]["message"] == "two"

    events.clear_session(session_id)


def test_active_call_counter_is_bounded_at_zero():
    session_id = "test-events-active"
    events.clear_session(session_id)

    assert events.set_active_call(session_id, 1) == 1
    assert events.set_active_call(session_id, 2) == 3
    assert events.set_active_call(session_id, -99) == 0

    events.clear_session(session_id)


def test_cancel_requested_flag():
    session_id = "test-events-cancel"
    events.clear_session(session_id)

    assert events.cancel_requested(session_id) is False
    events.mark_cancel_requested(session_id)
    assert events.cancel_requested(session_id) is True

    events.clear_session(session_id)


def test_event_payload_redacts_api_keys():
    session_id = "test-events-redact"
    events.clear_session(session_id)

    entry = events.append_event(session_id, {
        "phase": "start",
        "status": "start",
        "message": "api_key=sk-secret should not leak",
        "api_key": "sk-secret",
        "error": "authorization token sk-secret",
    })

    assert "sk-secret" not in str(entry)
    assert "[redacted]" in str(entry)

    events.clear_session(session_id)


def test_runtime_mirror_receives_monotonic_events():
    from sidecar.runtime.agent_runtime import RuntimeStore

    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp())
    store = RuntimeStore(root)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "test", ttl_seconds=30)
    session_id = "test-events-runtime-mirror"
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, attempt["attempt_id"], "test", lease["fence_token"])

    events.append_event(session_id, {"message": "first"})
    events.append_event(session_id, {"message": "second"})

    assert [entry["sequence"] for entry in store.list_events(attempt["attempt_id"])] == [1, 2]
    events.clear_session(session_id)


def test_provider_timeout_is_unknown_and_never_retried(tmp_path):
    session_id = "provider-timeout"
    store, attempt = _bound_runtime(tmp_path, session_id)
    llm = _FakeLlm([TimeoutError("socket timeout")])

    with pytest.raises(events.ProviderCallRequiresHumanConfirmation, match="requires_human_confirmation"):
        asyncio.run(w1_import._invoke_json_prompt(
            llm, "Sensitive source sk-do-not-store", session_id=session_id
        ))

    calls = store.list_tool_calls(attempt["attempt_id"])
    assert llm.calls == 1
    assert len(calls) == 1
    assert calls[0]["status"] == "unknown_outcome"
    assert calls[0]["unknown_reason"] == "ambiguous_transport"
    assert store.get_attempt(attempt["attempt_id"])["status"] == "waiting_human"
    events.clear_session(session_id)


def test_provider_401_is_definitive_and_never_retried(tmp_path):
    session_id = "provider-auth"
    store, attempt = _bound_runtime(tmp_path, session_id)
    llm = _FakeLlm([_StatusError(401)])

    with pytest.raises(_StatusError):
        asyncio.run(w1_import._invoke_json_prompt(llm, "Return JSON", session_id=session_id))

    calls = store.list_tool_calls(attempt["attempt_id"])
    assert llm.calls == 1
    assert [call["status"] for call in calls] == ["failed"]
    assert calls[0]["result_payload"]["failure_type"] == "authentication_denied"
    events.clear_session(session_id)


def test_provider_429_retries_only_to_the_bounded_limit(tmp_path, monkeypatch):
    session_id = "provider-rate-limit"
    store, attempt = _bound_runtime(tmp_path, session_id)
    llm = _FakeLlm([_StatusError(429) for _ in range(4)])

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(w1_import.asyncio, "sleep", no_sleep)
    with pytest.raises(_StatusError):
        asyncio.run(w1_import._invoke_json_prompt(llm, "Return JSON", session_id=session_id))

    assert llm.calls == 4
    calls = store.list_tool_calls(attempt["attempt_id"])
    assert len(calls) == 4
    assert {call["status"] for call in calls} == {"failed"}
    assert {call["result_payload"]["failure_type"] for call in calls} == {"rate_limited"}
    events.clear_session(session_id)


def test_provider_success_persists_redacted_intent_and_usage_receipt(tmp_path):
    session_id = "provider-success"
    store, attempt = _bound_runtime(tmp_path, session_id)
    secret_prompt = "private manuscript content with sk-never-persist-this"

    result = asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), secret_prompt, session_id=session_id
    ))

    assert result == {"ok": True}
    call = store.list_tool_calls(attempt["attempt_id"])[0]
    assert call["status"] == "result"
    assert set(call["intent_payload"]) == {
        "message_hash", "model", "estimated_input_tokens",
        "estimated_output_tokens", "sequence", "idempotency_key",
    }
    assert call["result_payload"]["input_tokens"] == 11
    assert call["result_payload"]["output_tokens"] == 7
    assert len(call["result_payload"]["result_hash"]) == 64
    with sqlite3.connect(store.database_path) as connection:
        persisted = json.dumps(connection.execute(
            "SELECT intent_payload_json, result_payload_json FROM tool_calls"
        ).fetchall())
    assert secret_prompt not in persisted
    assert "sk-never-persist-this" not in persisted
    assert '{"ok":true}' not in persisted
    events.clear_session(session_id)


def test_unknown_idempotency_key_requires_durable_retry_decision(tmp_path):
    session_id = "provider-resume-gate"
    store, attempt = _bound_runtime(tmp_path, session_id)
    with pytest.raises(events.ProviderCallRequiresHumanConfirmation):
        asyncio.run(w1_import._invoke_json_prompt(
            _FakeLlm([ConnectionError("connection lost")]), "Return JSON", session_id=session_id
        ))
    unknown = store.list_tool_calls(attempt["attempt_id"])[0]
    unknown_key = unknown["intent_payload"]["idempotency_key"]

    blocked_llm = _FakeLlm([_Response()])
    with pytest.raises(events.ProviderCallRequiresHumanConfirmation):
        asyncio.run(w1_import._invoke_json_prompt(blocked_llm, "Return JSON", session_id=session_id))
    assert blocked_llm.calls == 0
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 1

    store.record_human_decision(
        attempt["attempt_id"], f"retry_provider_call:{unknown_key}", "authorize_retry_once", {}
    )
    retry_llm = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        retry_llm, "Return JSON", session_id=session_id
    )) == {"ok": True}
    assert retry_llm.calls == 1
    calls = store.list_tool_calls(attempt["attempt_id"])
    assert len(calls) == 2
    assert calls[0]["status"] == "retry_consumed"
    assert calls[1]["status"] == "result"
    events.clear_session(session_id)


def test_fenced_event_append_preserves_managed_binding_and_blocks_provider_io(tmp_path):
    session_id = "provider-fenced-append"
    store, attempt = _bound_runtime(tmp_path, session_id)
    store.acquire_lease(
        attempt["attempt_id"], "replacement-worker", ttl_seconds=30,
        now=time.time() + 31,
    )

    events.append_event(session_id, {"message": "stale worker heartbeat"})
    assert session_id in events._runtime_bindings
    llm = _FakeLlm([_Response()])
    with pytest.raises(LeaseLostError):
        asyncio.run(w1_import._invoke_json_prompt(llm, "Return JSON", session_id=session_id))

    assert llm.calls == 0
    assert store.list_tool_calls(attempt["attempt_id"]) == []
    assert session_id in events._runtime_bindings
    events.clear_session(session_id)


def test_fenced_worker_cannot_settle_provider_tool_call(tmp_path):
    session_id = "provider-fenced-settle"
    store, attempt = _bound_runtime(tmp_path, session_id)
    call = events.begin_provider_call(
        session_id,
        model="deepseek-chat",
        message_hash="d" * 64,
        estimated_input_tokens=10,
        estimated_output_tokens=5,
    )
    store.acquire_lease(
        attempt["attempt_id"], "replacement-worker", ttl_seconds=30,
        now=time.time() + 31,
    )

    with pytest.raises(LeaseLostError):
        events.settle_provider_success(
            call, model="deepseek-chat", input_tokens=1, output_tokens=1,
            result_hash="e" * 64,
        )
    with pytest.raises(LeaseLostError):
        events.settle_provider_failure(call, failure_type="authentication_denied", status_code=401)
    with pytest.raises(LeaseLostError):
        events.settle_provider_unknown(session_id, call, reason="ambiguous_transport")

    persisted = store.list_tool_calls(attempt["attempt_id"])[0]
    assert persisted["status"] == "intent"
    assert persisted.get("result_payload") is None
    assert persisted["unknown_reason"] is None
    events.clear_session(session_id)


def test_run_w1_consumes_unknown_outcome_and_leaves_attempt_waiting_human(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    session_id = attempt["attempt_id"]
    owner_id = "test-worker"
    lease = store.acquire_lease(session_id, owner_id, ttl_seconds=30)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, session_id, owner_id, lease["fence_token"])
    workflow_router._w1_sessions[session_id] = {"status": "running", "progress": 0.25}

    async def raise_unknown(_project_path, _config):
        if False:
            yield {}
        raise events.ProviderCallRequiresHumanConfirmation("provider-call-1")

    monkeypatch.setattr(w1_import, "run_streaming", raise_unknown)

    async def exercise():
        task = asyncio.create_task(workflow_router._run_w1(session_id, {
            "project_path": str(tmp_path),
            "runtime_store": store,
            "runtime_owner_id": owner_id,
            "runtime_fence_token": lease["fence_token"],
        }))
        await asyncio.wait_for(task, timeout=2)
        return task

    task = asyncio.run(exercise())
    assert task.done()
    assert task.exception() is None
    assert store.get_attempt(session_id)["status"] == "waiting_human"
    assert workflow_router._w1_sessions[session_id]["status"] == "paused"
    assert workflow_router._w1_sessions[session_id]["recoverable"] is True
    assert workflow_router._w1_sessions[session_id]["paused"] is True
    assert any(event["status"] == "paused" for event in events.list_events(session_id))

    workflow_router._w1_sessions.pop(session_id, None)
    events.clear_session(session_id)
