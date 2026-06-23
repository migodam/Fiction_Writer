from sidecar.workflows import w1_run_events as events


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
