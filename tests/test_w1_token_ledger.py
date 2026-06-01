"""Unit tests for w1_run_events token ledger — zero cost, no LLM calls."""
from __future__ import annotations

import pytest
from sidecar.workflows import w1_run_events as ev


def _fresh(session_id: str = "test-session") -> str:
    ev.clear_session(session_id)
    ev.ensure_session(session_id)
    return session_id


def test_add_token_usage_accumulates():
    sid = _fresh()
    ev.add_token_usage(sid, input_tokens=100, output_tokens=50)
    ev.add_token_usage(sid, input_tokens=200, output_tokens=80)
    ledger = ev.session_token_ledger(sid)
    assert ledger["actual_input_tokens"] == 300
    assert ledger["actual_output_tokens"] == 130
    assert ledger["actual_total_tokens"] == 430
    assert ledger["api_call_count"] == 2


def test_session_token_ledger_returns_estimated_input():
    sid = _fresh()
    ledger = ev.session_token_ledger(sid, estimated_input_tokens=12345)
    assert ledger["estimated_input_tokens"] == 12345


def test_cost_calculated_for_known_model():
    sid = _fresh()
    ev.add_token_usage(sid, input_tokens=1_000_000, output_tokens=1_000_000)
    ledger = ev.session_token_ledger(sid, model="deepseek-chat")
    assert "cost_usd" in ledger
    # 1M input * 0.27 + 1M output * 1.10 = 1.37
    assert abs(ledger["cost_usd"] - 1.37) < 0.0001
    assert "cost_unavailable_reason" not in ledger


def test_cost_unavailable_for_unknown_model():
    sid = _fresh()
    ev.add_token_usage(sid, input_tokens=100, output_tokens=50)
    ledger = ev.session_token_ledger(sid, model="some-unknown-model-xyz")
    assert "cost_usd" not in ledger
    assert "cost_unavailable_reason" in ledger


def test_empty_ledger_when_no_calls():
    sid = _fresh()
    ledger = ev.session_token_ledger(sid)
    assert ledger["actual_input_tokens"] == 0
    assert ledger["actual_output_tokens"] == 0
    assert ledger["api_call_count"] == 0


def test_secret_scan_ledger_contains_no_secret_keys():
    """Token ledger must never contain keys that look like credentials."""
    sid = _fresh()
    ev.add_token_usage(sid, input_tokens=500, output_tokens=200)
    ledger = ev.session_token_ledger(sid, model="deepseek-chat")
    forbidden = {"api_key", "apikey", "authorization", "token", "password", "secret"}
    leaked = forbidden & {k.lower() for k in ledger}
    assert leaked == set(), f"Secret-like keys found in ledger: {leaked}"


def test_clear_session_resets_ledger():
    sid = _fresh()
    ev.add_token_usage(sid, input_tokens=999, output_tokens=999)
    ev.clear_session(sid)
    ev.ensure_session(sid)
    ledger = ev.session_token_ledger(sid)
    assert ledger["actual_input_tokens"] == 0
    assert ledger["api_call_count"] == 0


def test_empty_session_id_is_noop():
    ev.add_token_usage("", input_tokens=100, output_tokens=50)
    ledger = ev.session_token_ledger("")
    assert ledger == {}
