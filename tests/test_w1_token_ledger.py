"""Unit tests for w1_run_events token ledger — zero cost, no LLM calls."""
from __future__ import annotations

import asyncio

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


def test_gpt4o_mini_does_not_match_gpt4o_price():
    """Longer key must win — gpt-4o-mini must not be priced as gpt-4o."""
    sid = _fresh("gpt-mini-test")
    ev.add_token_usage(sid, input_tokens=1_000_000, output_tokens=1_000_000)
    ledger = ev.session_token_ledger(sid, model="gpt-4o-mini")
    assert "cost_usd" in ledger
    # gpt-4o-mini: 0.15 input + 0.60 output = 0.75 per 1M each
    assert abs(ledger["cost_usd"] - 0.75) < 0.001, f"Expected ~0.75, got {ledger['cost_usd']}"


def test_empty_session_id_is_noop():
    ev.add_token_usage("", input_tokens=100, output_tokens=50)
    ledger = ev.session_token_ledger("")
    assert ledger == {}


@pytest.mark.parametrize(("model", "expected_cost"), [
    ("deepseek-v4-flash", 0.42),
    ("provider/deepseek-v4-pro:latest", 1.305),
])
def test_v4_pricing_is_explicit_and_has_metadata(model, expected_cost):
    sid = _fresh(f"pricing-{model}")
    ev.add_token_usage(sid, input_tokens=1_000_000, output_tokens=1_000_000)

    ledger = ev.session_token_ledger(sid, model=model)

    assert ledger["cost_usd"] == pytest.approx(expected_cost)
    assert ledger["pricing"]["model_match"] in {"deepseek-v4-flash", "deepseek-v4-pro"}
    assert ledger["pricing"]["pricing_version"] == ev.PRICING_VERSION
    assert ev.resolve_model_pricing("deepseek-v4") is None
    assert ev.resolve_model_pricing("deepseek-v4-flashx") is None


def test_budget_policy_fails_closed_for_unknown_model_before_call():
    sid = _fresh("unknown-budget")
    ev.configure_budget(sid, ev.BudgetPolicy(max_cost_usd=3), model="unknown-model")

    assert ev.budget_allows_call(sid) is False
    ledger = ev.session_token_ledger(sid, model="unknown-model")
    assert ledger["budget_exhausted"] is True
    assert ledger["budget_exhausted_reason"].startswith("unknown_pricing:")
    assert ev.cancel_requested(sid) is True


def test_budget_policy_fails_closed_when_usage_is_missing():
    sid = _fresh("missing-usage")
    ev.configure_budget(sid, ev.BudgetPolicy(max_cost_usd=3), model="deepseek-v4-flash")

    assert ev.budget_allows_call(sid) is True
    assert ev.record_call_usage(sid, None, 12, model="deepseek-v4-flash") is False
    ledger = ev.session_token_ledger(sid, model="deepseek-v4-flash")
    assert ledger["budget_exhausted_reason"] == "missing_usage"
    assert ledger["api_call_count"] == 1


def test_authoritative_usage_ledger_has_durable_aliases_and_budget_status():
    sid = _fresh("authoritative-usage")
    ev.configure_budget(sid, ev.BudgetPolicy(max_calls=3), model="deepseek-v4-flash")
    assert ev.record_call_usage(sid, 120, 45, model="deepseek-v4-flash") is True

    ledger = ev.authoritative_usage_ledger(sid, "deepseek-v4-flash")

    assert ledger["actual_calls"] == 1
    assert ledger["api_call_count"] == 1
    assert ledger["cost_usd"] is not None
    assert ledger["model"] == "deepseek-v4-flash"
    assert ledger["budget_status"] == {"exhausted": False, "reason": "", "remaining": ledger["budget_status"]["remaining"]}


def test_crossing_budget_cancels_and_blocks_the_next_call():
    sid = _fresh("budget-crossing")
    ev.configure_budget(sid, ev.BudgetPolicy(max_total_tokens=100, max_calls=2), model="deepseek-v4-flash")

    assert ev.budget_allows_call(sid, estimated_input_tokens=30, estimated_output_tokens=30) is True
    assert ev.record_call_usage(sid, 60, 50, model="deepseek-v4-flash") is False
    assert ev.cancel_requested(sid) is True
    assert ev.budget_allows_call(sid) is False
    ledger = ev.session_token_ledger(sid, model="deepseek-v4-flash")
    assert ledger["budget_exhausted_reason"] == "max_total_tokens"
    assert ledger["remaining_budget"]["total_tokens"] == 0


def test_preflight_stops_call_that_would_cross_call_or_cost_limit():
    sid = _fresh("budget-preflight")
    ev.configure_budget(sid, ev.BudgetPolicy(max_cost_usd=0.01, max_calls=1), model="deepseek-v4-flash")

    assert ev.budget_allows_call(sid, estimated_input_tokens=100_000) is False
    assert ev.session_token_ledger(sid, model="deepseek-v4-flash")["budget_exhausted_reason"] == "max_cost_usd"


def test_concurrent_preflight_reservations_do_not_overspend_and_can_release():
    sid = _fresh("concurrent-reservations")
    ev.configure_budget(sid, ev.BudgetPolicy(max_calls=1), model="deepseek-v4-flash")

    async def reserve() -> bool:
        await asyncio.sleep(0)
        return ev.budget_allows_call(sid, model="deepseek-v4-flash")

    async def reserve_concurrently() -> tuple[bool, bool]:
        first, second = await asyncio.gather(reserve(), reserve())
        return first, second

    first, second = asyncio.run(reserve_concurrently())

    assert [first, second].count(True) == 1
    assert ev.cancel_requested(sid) is False
    ev.release_call_reservation(sid)
    assert ev.budget_allows_call(sid, model="deepseek-v4-flash") is True


def test_different_estimates_settle_in_reverse_order_by_reservation_identity():
    sid = _fresh("reverse-settlement")
    ev.configure_budget(sid, ev.BudgetPolicy(max_input_tokens=100, max_calls=3), model="deepseek-v4-flash")

    large = ev.reserve_call_budget(sid, estimated_input_tokens=70, model="deepseek-v4-flash")
    small = ev.reserve_call_budget(sid, estimated_input_tokens=20, model="deepseek-v4-flash")
    assert large and small and large != small
    assert ev.session_token_ledger(sid, model="deepseek-v4-flash")["remaining_budget"]["input_tokens"] == 10

    # The smaller provider response completes first. Its token must remove the
    # 20-token reservation, leaving the 70-token call reserved in flight.
    assert ev.record_call_usage(
        sid, 20, 0, model="deepseek-v4-flash", reservation_token=small,
    ) is True
    ledger = ev.session_token_ledger(sid, model="deepseek-v4-flash")
    assert ledger["actual_input_tokens"] == 20
    assert ledger["remaining_budget"]["input_tokens"] == 10
    assert ev.reserve_call_budget(sid, estimated_input_tokens=11, model="deepseek-v4-flash") is None
    assert ev.cancel_requested(sid) is False

    fitting = ev.reserve_call_budget(sid, estimated_input_tokens=10, model="deepseek-v4-flash")
    assert fitting
    ev.release_call_reservation(sid, fitting)
    assert ev.record_call_usage(
        sid, 70, 0, model="deepseek-v4-flash", reservation_token=large,
    ) is True
    final = ev.session_token_ledger(sid, model="deepseek-v4-flash")
    assert final["actual_input_tokens"] == 90
    assert final["remaining_budget"]["input_tokens"] == 10
