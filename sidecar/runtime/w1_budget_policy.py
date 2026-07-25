"""Pure server-owned W1 budget policy normalization.

The API layer may let a caller tighten a recovered run, but it must never let
request data or an old persisted shape widen the server safety envelope.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


W1_BUDGET_LIMITS: dict[str, int] = {
    "max_calls": 100,
    "max_input_tokens": 3_000_000,
    "max_output_tokens": 500_000,
    "max_total_tokens": 3_500_000,
}
W1_BUDGET_REQUIRED_FLAGS = ("fail_on_unknown_pricing", "fail_on_missing_usage")
W1_BUDGET_ALLOWED_KEYS = frozenset({
    "max_cost_usd",
    *W1_BUDGET_LIMITS,
    *W1_BUDGET_REQUIRED_FLAGS,
})


class W1BudgetPolicyError(ValueError):
    """A stable, non-secret validation failure suitable for an API detail."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def w1_budget_cost_cap(model: str) -> float:
    """Return the server-owned spend ceiling for a W1 model."""
    return 8.0 if "deepseek-v4-pro" in (model or "").lower() else 3.0


def w1_budget_envelope(model: str) -> dict[str, Any]:
    return {
        "max_cost_usd": w1_budget_cost_cap(model),
        **W1_BUDGET_LIMITS,
        "fail_on_unknown_pricing": True,
        "fail_on_missing_usage": True,
    }


def _validated_values(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if values is not None and not isinstance(values, Mapping):
        raise W1BudgetPolicyError("budget_config_invalid")
    raw = dict(values or {})
    if set(raw) - W1_BUDGET_ALLOWED_KEYS:
        raise W1BudgetPolicyError("budget_unknown_keys")

    for key, value in raw.items():
        if key == "max_cost_usd":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise W1BudgetPolicyError("budget_max_cost_usd_invalid")
        elif key in W1_BUDGET_LIMITS:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise W1BudgetPolicyError(f"budget_{key}_invalid")
        elif not isinstance(value, bool):
            raise W1BudgetPolicyError(f"budget_{key}_invalid")
    return raw


def normalize_w1_budget_policy(
    model: str,
    values: Mapping[str, Any] | None,
    *,
    persisted_legacy: bool = False,
) -> dict[str, Any]:
    """Fill the complete policy and enforce the model-aware server envelope.

    Public request values outside the envelope are rejected. Historical values
    are clamped because they were persisted before this contract existed; bad
    types, negative/non-finite values, and unknown keys still fail closed.
    """
    raw = _validated_values(values)
    effective = w1_budget_envelope(model)

    if "max_cost_usd" in raw:
        requested_cost = float(raw["max_cost_usd"])
        cap = float(effective["max_cost_usd"])
        if requested_cost > cap and not persisted_legacy:
            raise W1BudgetPolicyError("budget_max_cost_exceeds_model_cap")
        effective["max_cost_usd"] = min(requested_cost, cap)

    for key, cap in W1_BUDGET_LIMITS.items():
        if key not in raw:
            continue
        requested_limit = raw[key]
        if requested_limit > cap and not persisted_legacy:
            raise W1BudgetPolicyError(f"budget_{key}_exceeds_server_cap")
        effective[key] = min(requested_limit, cap)

    for key in W1_BUDGET_REQUIRED_FLAGS:
        if raw.get(key) is False and not persisted_legacy:
            raise W1BudgetPolicyError(f"budget_{key}_must_be_true")
        effective[key] = True
    return effective


def merge_w1_resume_budget_policy(
    model: str,
    persisted: Mapping[str, Any] | None,
    requested: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize old state, then intersect it with a caller's tighter limits."""
    baseline = normalize_w1_budget_policy(model, persisted, persisted_legacy=True)
    requested_policy = normalize_w1_budget_policy(model, requested)
    return {
        "max_cost_usd": min(baseline["max_cost_usd"], requested_policy["max_cost_usd"]),
        **{
            key: min(baseline[key], requested_policy[key])
            for key in W1_BUDGET_LIMITS
        },
        "fail_on_unknown_pricing": True,
        "fail_on_missing_usage": True,
    }
