import asyncio
import json
import sqlite3
import time
from pathlib import Path

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


def test_pending_unknown_blocks_verified_cache_until_durably_authorized(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="lineage-unknown-cache")
    source_attempt = store.create_attempt(run["run_id"], attempt_id="unknown-cache-source")
    source_lease = store.acquire_lease(source_attempt["attempt_id"], "source-worker", ttl_seconds=30)
    events.clear_session("unknown-cache-source-session")
    events.bind_runtime(
        "unknown-cache-source-session", store, source_attempt["attempt_id"], "source-worker", source_lease["fence_token"],
    )
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "cached prompt", session_id="unknown-cache-source-session",
    )) == {"ok": True}

    cached_attempt = store.create_attempt(run["run_id"], attempt_id="unknown-cache-target")
    unknown = store.record_tool_intent(
        cached_attempt["attempt_id"],
        "provider.chat.completions",
        {"idempotency_key": "unknown-cache-call", "model": "deepseek-chat", "message_hash": "f" * 64},
    )
    store.record_tool_unknown_outcome(unknown["tool_call_id"], "runtime_interrupted")
    cached_lease = store.acquire_lease(cached_attempt["attempt_id"], "cached-worker", ttl_seconds=30)
    cached_session = "unknown-cache-target-session"
    events.clear_session(cached_session)
    events.bind_runtime(
        cached_session, store, cached_attempt["attempt_id"], "cached-worker", cached_lease["fence_token"],
    )

    blocked_llm = _FakeLlm([])
    with pytest.raises(events.ProviderCallRequiresHumanConfirmation, match="unknown-cache-call"):
        asyncio.run(w1_import._invoke_json_prompt(
            blocked_llm, "cached prompt", session_id=cached_session,
        ))
    assert blocked_llm.calls == 0
    assert store.get_attempt(cached_attempt["attempt_id"])["status"] == "waiting_human"
    assert len(store.list_tool_calls(cached_attempt["attempt_id"])) == 1

    store.record_unknown_call_decision(
        cached_attempt["attempt_id"],
        "retry_provider_call:unknown-cache-call",
        "authorize_retry_once",
    )
    allowed_llm = _FakeLlm([])
    assert asyncio.run(w1_import._invoke_json_prompt(
        allowed_llm, "cached prompt", session_id=cached_session,
    )) == {"ok": True}
    assert allowed_llm.calls == 0
    calls = store.list_tool_calls(cached_attempt["attempt_id"])
    assert len(calls) == 1
    assert calls[0]["status"] == "unknown_outcome"

    events.clear_session("unknown-cache-source-session")
    events.clear_session(cached_session)


def test_authorized_unknown_only_allows_matching_retry_then_downstream_call(tmp_path):
    session_id = "provider-authorized-match-only"
    store, attempt = _bound_runtime(tmp_path, session_id)
    retry_prompt = "retry this exact operation"
    retry_hash = events.provider_message_hash([w1_import.HumanMessage(content=retry_prompt)])
    unknown = store.record_tool_intent(
        attempt["attempt_id"],
        "provider.chat.completions",
        {"idempotency_key": "match-only-key", "model": "deepseek-chat", "message_hash": retry_hash},
    )
    store.record_tool_unknown_outcome(unknown["tool_call_id"], "runtime_interrupted")
    decision_key = "retry_provider_call:match-only-key"
    store.record_unknown_call_decision(attempt["attempt_id"], decision_key, "authorize_retry_once")

    mismatched = _FakeLlm([_Response()])
    with pytest.raises(events.ProviderCallRequiresHumanConfirmation, match="match-only-key"):
        asyncio.run(w1_import._invoke_json_prompt(
            mismatched, "different paid operation", session_id=session_id,
        ))
    assert mismatched.calls == 0
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 1

    matching = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        matching, retry_prompt, session_id=session_id,
    )) == {"ok": True}
    assert matching.calls == 1
    assert events.cancel_requested(session_id) is False
    calls = store.list_tool_calls(attempt["attempt_id"])
    assert [call["status"] for call in calls] == ["retry_consumed", "result"]

    cached_repeat = _FakeLlm([])
    assert asyncio.run(w1_import._invoke_json_prompt(
        cached_repeat, retry_prompt, session_id=session_id,
    )) == {"ok": True}
    assert cached_repeat.calls == 0
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 2

    downstream = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        downstream, "downstream paid operation", session_id=session_id,
    )) == {"ok": True}
    assert downstream.calls == 1
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 3

    with pytest.raises(ValueError, match="unknown_call_decision_key_not_found"):
        store.record_unknown_call_decision(
            attempt["attempt_id"], decision_key, "authorize_retry_once",
        )
    second_unknown = store.record_tool_intent(
        attempt["attempt_id"],
        "provider.chat.completions",
        {"idempotency_key": "new-unknown-key", "model": "deepseek-chat", "message_hash": retry_hash},
    )
    store.record_tool_unknown_outcome(second_unknown["tool_call_id"], "runtime_interrupted")
    duplicate_auth = _FakeLlm([])
    with pytest.raises(events.ProviderCallRequiresHumanConfirmation, match="new-unknown-key"):
        asyncio.run(w1_import._invoke_json_prompt(
            duplicate_auth, retry_prompt, session_id=session_id,
        ))
    assert duplicate_auth.calls == 0
    events.clear_session(session_id)


def test_matching_verified_cache_consumes_authorized_unknown_then_allows_downstream(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="lineage-cache-resolution")
    prompt = "operation recovered from cache"
    prompt_hash = events.provider_message_hash([w1_import.HumanMessage(content=prompt)])

    source_attempt = store.create_attempt(run["run_id"], attempt_id="cache-resolution-source")
    source_lease = store.acquire_lease(source_attempt["attempt_id"], "source-worker", ttl_seconds=30)
    events.clear_session("cache-resolution-source-session")
    events.bind_runtime(
        "cache-resolution-source-session", store, source_attempt["attempt_id"], "source-worker", source_lease["fence_token"],
    )
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), prompt, session_id="cache-resolution-source-session",
    )) == {"ok": True}

    attempt = store.create_attempt(run["run_id"], attempt_id="cache-resolution-target")
    unknown = store.record_tool_intent(
        attempt["attempt_id"],
        "provider.chat.completions",
        {"idempotency_key": "cache-resolution-key", "model": "deepseek-chat", "message_hash": prompt_hash},
    )
    store.record_tool_unknown_outcome(unknown["tool_call_id"], "runtime_interrupted")
    decision_key = "retry_provider_call:cache-resolution-key"
    store.record_unknown_call_decision(attempt["attempt_id"], decision_key, "authorize_retry_once")
    lease = store.acquire_lease(attempt["attempt_id"], "target-worker", ttl_seconds=30)
    session_id = "cache-resolution-target-session"
    events.clear_session(session_id)
    events.bind_runtime(
        session_id, store, attempt["attempt_id"], "target-worker", lease["fence_token"],
    )

    cached = _FakeLlm([])
    assert asyncio.run(w1_import._invoke_json_prompt(
        cached, prompt, session_id=session_id,
    )) == {"ok": True}
    assert cached.calls == 0
    assert events.cancel_requested(session_id) is False
    reconciled = store.list_tool_calls(attempt["attempt_id"])
    assert len(reconciled) == 1
    assert reconciled[0]["status"] == "retry_consumed"
    assert reconciled[0]["result_payload"]["outcome"] == "resolved_from_verified_artifact"
    assert set(reconciled[0]["result_payload"]["artifact_receipt"]) == {
        "operation_key", "artifact_path", "artifact_hash",
    }

    downstream = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        downstream, "downstream after cache resolution", session_id=session_id,
    )) == {"ok": True}
    assert downstream.calls == 1
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 2
    events.clear_session("cache-resolution-source-session")
    events.clear_session(session_id)


def test_concurrent_identical_provider_calls_singleflight_and_account_once(tmp_path):
    session_id = "provider-singleflight"
    store, attempt = _bound_runtime(tmp_path, session_id)
    events.configure_budget(
        session_id,
        events.BudgetPolicy(max_calls=2, max_total_tokens=100),
        model="deepseek-chat",
    )

    class DelayedLlm:
        model = "deepseek-chat"

        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            await asyncio.sleep(0.03)
            return _Response()

    async def invoke_concurrently(llm):
        return await asyncio.gather(*(
            w1_import._invoke_json_prompt(llm, "same concurrent prompt", session_id=session_id)
            for _ in range(12)
        ))

    llm = DelayedLlm()
    results = asyncio.run(invoke_concurrently(llm))
    ledger = events.authoritative_usage_ledger(session_id, "deepseek-chat")
    assert results == [{"ok": True}] * 12
    assert llm.calls == 1
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 1
    assert ledger["actual_input_tokens"] == 11
    assert ledger["actual_output_tokens"] == 7
    assert ledger["actual_calls"] == 1

    events.clear_session(session_id)
    lease = store.acquire_lease(attempt["attempt_id"], "test-worker", ttl_seconds=30)
    events.bind_runtime(session_id, store, attempt["attempt_id"], "test-worker", lease["fence_token"])
    events.configure_budget(
        session_id,
        events.BudgetPolicy(max_calls=2, max_total_tokens=100),
        model="deepseek-chat",
    )
    cached_llm = _FakeLlm([])
    assert asyncio.run(w1_import._invoke_json_prompt(
        cached_llm, "same concurrent prompt", session_id=session_id,
    )) == {"ok": True}
    rebuilt = events.authoritative_usage_ledger(session_id, "deepseek-chat")
    assert cached_llm.calls == 0
    assert rebuilt["actual_calls"] == 1
    assert rebuilt["actual_total_tokens"] == 18
    events.clear_session(session_id)


def test_singleflight_follower_cancellation_does_not_cancel_leader(tmp_path):
    session_id = "provider-singleflight-follower-cancel"
    store, attempt = _bound_runtime(tmp_path, session_id)

    class BlockingLlm:
        model = "deepseek-chat"

        def __init__(self):
            self.calls = 0
            self.started: asyncio.Event | None = None
            self.release: asyncio.Event | None = None

        async def ainvoke(self, _messages):
            self.calls += 1
            assert self.started is not None and self.release is not None
            self.started.set()
            await self.release.wait()
            return _Response()

    async def exercise():
        llm = BlockingLlm()
        llm.started = asyncio.Event()
        llm.release = asyncio.Event()
        leader = asyncio.create_task(w1_import._invoke_json_prompt(
            llm, "follower cancellation prompt", session_id=session_id,
        ))
        await llm.started.wait()
        follower = asyncio.create_task(w1_import._invoke_json_prompt(
            llm, "follower cancellation prompt", session_id=session_id,
        ))
        await asyncio.sleep(0)
        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower
        llm.release.set()
        return llm, await leader

    llm, result = asyncio.run(exercise())
    assert result == {"ok": True}
    assert llm.calls == 1
    assert len(store.list_tool_calls(attempt["attempt_id"])) == 1
    events.clear_session(session_id)


def test_singleflight_leader_cancellation_releases_followers_and_gates_retry(tmp_path):
    session_id = "provider-singleflight-leader-cancel"
    store, attempt = _bound_runtime(tmp_path, session_id)
    prompt = "leader cancellation prompt"

    class BlockingLlm:
        model = "deepseek-chat"

        def __init__(self):
            self.calls = 0
            self.started: asyncio.Event | None = None

        async def ainvoke(self, _messages):
            self.calls += 1
            assert self.started is not None
            self.started.set()
            await asyncio.Event().wait()

    async def exercise():
        llm = BlockingLlm()
        llm.started = asyncio.Event()
        leader = asyncio.create_task(w1_import._invoke_json_prompt(
            llm, prompt, session_id=session_id,
        ))
        await llm.started.wait()
        follower = asyncio.create_task(w1_import._invoke_json_prompt(
            llm, prompt, session_id=session_id,
        ))
        await asyncio.sleep(0)
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        with pytest.raises(asyncio.CancelledError):
            await follower
        return llm

    llm = asyncio.run(exercise())
    assert llm.calls == 1
    calls = store.list_tool_calls(attempt["attempt_id"])
    assert len(calls) == 1
    assert calls[0]["status"] == "unknown_outcome"
    unknown_key = calls[0]["intent_payload"]["idempotency_key"]
    store.record_unknown_call_decision(
        attempt["attempt_id"],
        f"retry_provider_call:{unknown_key}",
        "authorize_retry_once",
    )
    retry = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        retry, prompt, session_id=session_id,
    )) == {"ok": True}
    assert retry.calls == 1
    assert [call["status"] for call in store.list_tool_calls(attempt["attempt_id"])] == [
        "retry_consumed", "result",
    ]
    events.clear_session(session_id)


def test_restart_reuses_five_verified_role_artifacts_and_calls_only_missing_role(tmp_path):
    session_id = "provider-five-of-six-restart"
    store = RuntimeStore(tmp_path)
    run = store.create_run(
        workflow_id="W1",
        lineage_id="lineage-provider-reuse",
        config={
            "prompt_version": "w1-prompts-v7",
            "schema_version": "w1-schema-v3",
            "tool_version": "w1-tools-v2",
            "config_version": "w1-config-v4",
        },
    )
    attempt = store.create_attempt(run["run_id"], attempt_id="attempt-provider-reuse")
    lease = store.acquire_lease(attempt["attempt_id"], "worker-before", ttl_seconds=30)
    events.clear_session(session_id)
    events.bind_runtime(session_id, store, attempt["attempt_id"], "worker-before", lease["fence_token"])

    role_prompts = ["characters", "events", "world", "relationships", "scenes", "validation"]

    async def invoke_all(llm, prompts):
        return await asyncio.gather(*(
            w1_import._invoke_json_prompt(llm, prompt, session_id=session_id)
            for prompt in prompts
        ))

    first = _FakeLlm([_Response() for _ in role_prompts[:-1]])
    first_results = asyncio.run(invoke_all(first, role_prompts[:-1]))
    assert first.calls == 5
    assert first_results == [{"ok": True}] * 5
    completed = store.list_tool_calls(attempt["attempt_id"])
    assert len(completed) == 5
    assert all(call["status"] == "result" for call in completed)
    assert all(call["result_payload"].get("artifact_receipt", {}).get("artifact_path", "").startswith("system/imports/") for call in completed)

    store.invalidate_leases_for_restart()
    resumed_store = RuntimeStore(tmp_path)
    resumed_lease = resumed_store.acquire_lease(attempt["attempt_id"], "worker-after", ttl_seconds=30)
    resumed_store.set_attempt_status(
        attempt["attempt_id"], "running", owner_id="worker-after", fence_token=resumed_lease["fence_token"],
    )
    events.clear_session(session_id)
    events.bind_runtime(session_id, resumed_store, attempt["attempt_id"], "worker-after", resumed_lease["fence_token"])

    resumed = _FakeLlm([_Response()])
    resumed_results = asyncio.run(invoke_all(resumed, role_prompts))

    assert resumed.calls == 1
    assert resumed_results == [{"ok": True}] * 6
    calls = resumed_store.list_tool_calls(attempt["attempt_id"])
    assert len(calls) == 6
    assert all(call["status"] == "result" for call in calls)
    assert len({call["intent_payload"]["message_hash"] for call in calls}) == 6
    events.clear_session(session_id)


def test_verified_provider_artifact_reuses_across_attempts_but_identity_changes_miss(tmp_path):
    store = RuntimeStore(tmp_path)
    base_config = {
        "prompt_profile": "deep",
        "prompt_version": "w1-prompts-v7",
        "schema_version": "w1-schema-v3",
        "tool_version": "w1-tools-v2",
        "config_version": "w1-config-v4",
    }
    run = store.create_run(workflow_id="W1", lineage_id="lineage-cross-attempt", config=base_config)
    first_attempt = store.create_attempt(run["run_id"], attempt_id="attempt-first")
    first_lease = store.acquire_lease(first_attempt["attempt_id"], "worker-first", ttl_seconds=30)
    events.clear_session("cross-attempt-first")
    events.bind_runtime(
        "cross-attempt-first", store, first_attempt["attempt_id"], "worker-first", first_lease["fence_token"],
    )
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "same prompt", session_id="cross-attempt-first",
    )) == {"ok": True}
    receipt = store.list_tool_calls(first_attempt["attempt_id"])[0]["result_payload"]["artifact_receipt"]
    assert "/attempts/" not in receipt["artifact_path"]
    assert receipt["artifact_path"].startswith("system/imports/lineage-cross-attempt/provider_responses/")
    artifact_path = tmp_path / receipt["artifact_path"]
    assert (artifact_path.parent.parent.stat().st_mode & 0o777) == 0o700
    assert (artifact_path.parent.stat().st_mode & 0o777) == 0o700
    assert (artifact_path.stat().st_mode & 0o777) == 0o600

    second_attempt = store.create_attempt(
        run["run_id"], attempt_id="attempt-second", parent_attempt_id=first_attempt["attempt_id"],
    )
    second_lease = store.acquire_lease(second_attempt["attempt_id"], "worker-second", ttl_seconds=30)
    events.clear_session("cross-attempt-second")
    events.bind_runtime(
        "cross-attempt-second", store, second_attempt["attempt_id"], "worker-second", second_lease["fence_token"],
    )
    cached_llm = _FakeLlm([])
    assert asyncio.run(w1_import._invoke_json_prompt(
        cached_llm, "same prompt", session_id="cross-attempt-second",
    )) == {"ok": True}
    assert cached_llm.calls == 0
    assert store.list_tool_calls(second_attempt["attempt_id"]) == []

    changed_message_llm = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        changed_message_llm, "changed prompt", session_id="cross-attempt-second",
    )) == {"ok": True}
    assert changed_message_llm.calls == 1

    changed_model_llm = _FakeLlm([_Response()])
    changed_model_llm.model = "deepseek-v3"
    assert asyncio.run(w1_import._invoke_json_prompt(
        changed_model_llm, "same prompt", session_id="cross-attempt-second",
    )) == {"ok": True}
    assert changed_model_llm.calls == 1

    changed_run = store.create_run(
        workflow_id="W1",
        lineage_id="lineage-cross-attempt",
        config={**base_config, "config_version": "w1-config-v5"},
    )
    changed_attempt = store.create_attempt(changed_run["run_id"], attempt_id="attempt-changed-config")
    changed_lease = store.acquire_lease(changed_attempt["attempt_id"], "worker-config", ttl_seconds=30)
    events.clear_session("cross-attempt-config")
    events.bind_runtime(
        "cross-attempt-config", store, changed_attempt["attempt_id"], "worker-config", changed_lease["fence_token"],
    )
    changed_config_llm = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(
        changed_config_llm, "same prompt", session_id="cross-attempt-config",
    )) == {"ok": True}
    assert changed_config_llm.calls == 1

    events.clear_session("cross-attempt-first")
    events.clear_session("cross-attempt-second")
    events.clear_session("cross-attempt-config")


def test_cached_usage_is_restored_once_and_enforces_budget_ceiling(tmp_path):
    store = RuntimeStore(tmp_path)
    run = store.create_run(
        workflow_id="W1", lineage_id="lineage-cached-usage", config={"prompt_version": "w1-prompts-v1"},
    )
    source_attempt = store.create_attempt(run["run_id"], attempt_id="usage-source")
    source_lease = store.acquire_lease(source_attempt["attempt_id"], "usage-source-worker", ttl_seconds=30)
    events.clear_session("usage-source-session")
    events.bind_runtime(
        "usage-source-session", store, source_attempt["attempt_id"], "usage-source-worker", source_lease["fence_token"],
    )
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "paid prompt", session_id="usage-source-session",
    )) == {"ok": True}
    source_ledger = events.authoritative_usage_ledger("usage-source-session", "deepseek-chat")

    cached_attempt = store.create_attempt(run["run_id"], attempt_id="usage-cached")
    cached_lease = store.acquire_lease(cached_attempt["attempt_id"], "usage-cached-worker", ttl_seconds=30)
    cached_session = "usage-cached-session"
    events.clear_session(cached_session)
    events.bind_runtime(
        cached_session, store, cached_attempt["attempt_id"], "usage-cached-worker", cached_lease["fence_token"],
    )
    events.configure_budget(
        cached_session,
        events.BudgetPolicy(max_total_tokens=100, max_calls=2),
        model="deepseek-chat",
    )
    cached_llm = _FakeLlm([])
    for _ in range(2):
        assert asyncio.run(w1_import._invoke_json_prompt(
            cached_llm, "paid prompt", session_id=cached_session,
        )) == {"ok": True}
    ledger = events.authoritative_usage_ledger(cached_session, "deepseek-chat")
    assert cached_llm.calls == 0
    assert store.list_tool_calls(cached_attempt["attempt_id"]) == []
    assert ledger["actual_input_tokens"] == 11
    assert ledger["actual_output_tokens"] == 7
    assert ledger["actual_calls"] == 1
    assert ledger["cost_usd"] == source_ledger["cost_usd"]
    assert ledger["budget_status"]["remaining"]["total_tokens"] == 82
    assert ledger["budget_status"]["remaining"]["calls"] == 1

    ceiling_attempt = store.create_attempt(run["run_id"], attempt_id="usage-ceiling")
    ceiling_lease = store.acquire_lease(ceiling_attempt["attempt_id"], "usage-ceiling-worker", ttl_seconds=30)
    ceiling_session = "usage-ceiling-session"
    events.clear_session(ceiling_session)
    events.bind_runtime(
        ceiling_session, store, ceiling_attempt["attempt_id"], "usage-ceiling-worker", ceiling_lease["fence_token"],
    )
    events.configure_budget(
        ceiling_session,
        events.BudgetPolicy(max_cost_usd=0.000010),
        model="deepseek-chat",
    )
    denied_llm = _FakeLlm([])
    with pytest.raises(RuntimeError, match=r"budget_exhausted: cached provider response denied \(max_cost_usd\)"):
        asyncio.run(w1_import._invoke_json_prompt(
            denied_llm, "paid prompt", session_id=ceiling_session,
        ))
    denied_ledger = events.authoritative_usage_ledger(ceiling_session, "deepseek-chat")
    assert denied_llm.calls == 0
    assert store.list_tool_calls(ceiling_attempt["attempt_id"]) == []
    assert denied_ledger["actual_total_tokens"] == 18
    assert denied_ledger["actual_calls"] == 1
    assert denied_ledger["cost_usd"] == source_ledger["cost_usd"]
    assert denied_ledger["budget_status"]["exhausted"] is True
    assert denied_ledger["budget_status"]["reason"] == "max_cost_usd"

    events.clear_session("usage-source-session")
    events.clear_session(cached_session)
    events.clear_session(ceiling_session)


def test_tampered_provider_artifact_is_not_a_cache_hit(tmp_path):
    session_id = "provider-artifact-tamper"
    store, attempt = _bound_runtime(tmp_path, session_id)
    assert asyncio.run(w1_import._invoke_json_prompt(_FakeLlm([_Response()]), "Return JSON", session_id=session_id)) == {"ok": True}
    receipt = store.list_tool_calls(attempt["attempt_id"])[0]["result_payload"]["artifact_receipt"]
    artifact = tmp_path / receipt["artifact_path"]
    artifact.write_text('{"tampered":true}', encoding="utf-8")

    replacement = _FakeLlm([_Response()])
    assert asyncio.run(w1_import._invoke_json_prompt(replacement, "Return JSON", session_id=session_id)) == {"ok": True}
    assert replacement.calls == 1
    assert Path(artifact).read_bytes().startswith(b'{"contract"')
    events.clear_session(session_id)


def test_symlinked_provider_artifact_file_misses_cache_and_persist_raises(tmp_path):
    session_id = "provider-artifact-symlink"
    store, attempt = _bound_runtime(tmp_path, session_id)
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "symlinked artifact prompt", session_id=session_id,
    )) == {"ok": True}
    receipt = store.list_tool_calls(attempt["attempt_id"])[0]["result_payload"]["artifact_receipt"]
    artifact = tmp_path / receipt["artifact_path"]
    target = tmp_path / "symlinked-artifact-target.json"
    target.write_bytes(artifact.read_bytes())
    artifact.unlink()
    try:
        artifact.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    replacement = _FakeLlm([_Response()])
    with pytest.raises(RuntimeError, match="provider_cache_symlink_or_escape_rejected"):
        asyncio.run(w1_import._invoke_json_prompt(
            replacement, "symlinked artifact prompt", session_id=session_id,
        ))
    assert replacement.calls == 1
    assert artifact.is_symlink()
    assert target.read_bytes().startswith(b'{"contract"')
    events.clear_session(session_id)


def test_symlinked_provider_responses_directory_misses_cache_and_persist_raises(tmp_path):
    session_id = "provider-directory-symlink"
    store = RuntimeStore(tmp_path)
    run = store.create_run(workflow_id="W1", lineage_id="lineage-directory-symlink")
    attempt = store.create_attempt(run["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "directory-worker", ttl_seconds=30)
    events.clear_session(session_id)
    events.bind_runtime(
        session_id, store, attempt["attempt_id"], "directory-worker", lease["fence_token"],
    )
    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "symlinked directory prompt", session_id=session_id,
    )) == {"ok": True}
    receipt = store.list_tool_calls(attempt["attempt_id"])[0]["result_payload"]["artifact_receipt"]
    artifact = tmp_path / receipt["artifact_path"]
    provider_root = artifact.parent.parent
    target = tmp_path / "symlinked-provider-root-target"
    provider_root.rename(target)
    try:
        provider_root.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    replacement = _FakeLlm([_Response()])
    with pytest.raises(RuntimeError, match="provider_cache_symlink_or_escape_rejected"):
        asyncio.run(w1_import._invoke_json_prompt(
            replacement, "symlinked directory prompt", session_id=session_id,
        ))
    assert replacement.calls == 1
    assert provider_root.is_symlink()
    assert artifact.relative_to(provider_root).as_posix() in {
        path.relative_to(target).as_posix() for path in target.rglob("*.json")
    }
    events.clear_session(session_id)


def test_provider_receipt_is_relative_to_resolved_project_root(tmp_path):
    session_id = "provider-symlinked-project-root"
    store = RuntimeStore(tmp_path)
    project_link = tmp_path / "project-root-link"
    try:
        project_link.symlink_to(tmp_path, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    store.project_root = project_link
    run = store.create_run(workflow_id="W1", lineage_id="lineage-project-root-link")
    attempt = store.create_attempt(run["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "project-link-worker", ttl_seconds=30)
    events.clear_session(session_id)
    events.bind_runtime(
        session_id, store, attempt["attempt_id"], "project-link-worker", lease["fence_token"],
    )

    assert asyncio.run(w1_import._invoke_json_prompt(
        _FakeLlm([_Response()]), "linked project root prompt", session_id=session_id,
    )) == {"ok": True}
    receipt = store.list_tool_calls(attempt["attempt_id"])[0]["result_payload"]["artifact_receipt"]
    assert receipt["artifact_path"].startswith(
        "system/imports/lineage-project-root-link/provider_responses/"
    )
    assert (tmp_path / receipt["artifact_path"]).is_file()
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
