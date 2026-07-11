"""In-memory W1 import activity feed.

This feed is separate from chunk extraction logs. It exists so long-running
supervisor imports can show the user what the AI is doing before a chunk/window
finishes and before proposals are written.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any

_events: dict[str, list[dict[str, Any]]] = {}
_started_at: dict[str, datetime] = {}
_last_activity_at: dict[str, datetime] = {}
_active_calls: dict[str, int] = {}
_cancel_requested: set[str] = set()
_token_ledger: dict[str, dict[str, int]] = {}
_budget_ledgers: dict[str, "BudgetLedger"] = {}

# Per-million-token USD prices for known model name substrings (longest match wins).
# V4 prices use cache-miss input because W1 usage does not separately report cache
# hits. Source: https://api-docs.deepseek.com/quick_start/pricing (2026-07-11).
PRICING_VERSION = "2026-07-11-deepseek-v4"
_DEFAULT_PRICE_TABLE: dict[str, dict[str, Any]] = {
    "deepseek-v4-flash": {
        "input_usd_per_1m": 0.14,
        "output_usd_per_1m": 0.28,
        "pricing_version": PRICING_VERSION,
        "pricing_source": "deepseek_api_cache_miss",
    },
    "deepseek-v4-pro": {
        "input_usd_per_1m": 0.435,
        "output_usd_per_1m": 0.87,
        "pricing_version": PRICING_VERSION,
        "pricing_source": "deepseek_api_cache_miss",
    },
    # Compatibility entries. Do not add a generic "deepseek-v4" matcher: that
    # would silently price unrecognized V4 variants.
    "deepseek-chat":    {"input_usd_per_1m": 0.27,  "output_usd_per_1m": 1.10},
    "deepseek-v3":      {"input_usd_per_1m": 0.27,  "output_usd_per_1m": 1.10},
    "deepseek-r1":      {"input_usd_per_1m": 0.55,  "output_usd_per_1m": 2.19},
    "gpt-4o":           {"input_usd_per_1m": 2.50,  "output_usd_per_1m": 10.00},
    "gpt-4.1":          {"input_usd_per_1m": 2.00,  "output_usd_per_1m": 8.00},
    "gpt-4o-mini":      {"input_usd_per_1m": 0.15,  "output_usd_per_1m": 0.60},
    "claude-3-5":       {"input_usd_per_1m": 3.00,  "output_usd_per_1m": 15.00},
    "claude-3-7":       {"input_usd_per_1m": 3.00,  "output_usd_per_1m": 15.00},
}

_SORTED_PRICE_TABLE: list[tuple[str, dict[str, Any]]] = sorted(
    _DEFAULT_PRICE_TABLE.items(), key=lambda kv: len(kv[0]), reverse=True
)

_SECRET_KEYS = {"api_key", "apikey", "authorization", "token", "password", "secret"}


def _matches_model_key(model: str, key: str) -> bool:
    """Match a model identifier as a full punctuation-delimited segment."""
    return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", model, re.IGNORECASE) is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in _SECRET_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str) and ("sk-" in value or "api_key" in value.lower()):
        return "[redacted]"
    return value


@dataclass(frozen=True)
class BudgetPolicy:
    """Fail-closed limits for a W1 model run; ``None`` means no limit."""

    max_cost_usd: float | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    max_calls: int | None = None
    fail_on_unknown_pricing: bool = True
    fail_on_missing_usage: bool = True

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name.startswith("max_") and value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass
class BudgetLedger:
    """Per-session actual usage and preflight budget evaluator.

    The caller must invoke ``can_start_call`` before every provider call and
    ``record_usage`` immediately after it returns. Missing usage and unknown
    pricing exhaust a policy by default instead of allowing an unbounded run.
    """

    policy: BudgetPolicy
    model: str = ""
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    api_call_count: int = 0
    exhausted_reason: str = ""

    @property
    def actual_total_tokens(self) -> int:
        return self.actual_input_tokens + self.actual_output_tokens

    def _pricing(self, model: str = "") -> tuple[dict[str, Any] | None, str | None]:
        model_lower = model or self.model or ""
        for key, prices in _SORTED_PRICE_TABLE:
            if _matches_model_key(model_lower, key):
                return prices, None
        return None, f"unknown_pricing:{model or self.model or 'unknown'}"

    def _cost(self, input_tokens: int, output_tokens: int, model: str = "") -> float | None:
        prices, _ = self._pricing(model)
        if prices is None:
            return None
        return input_tokens * prices["input_usd_per_1m"] / 1_000_000 + output_tokens * prices["output_usd_per_1m"] / 1_000_000

    def _limit_reason(self, input_tokens: int, output_tokens: int, calls: int, model: str = "") -> str:
        policy = self.policy
        total_tokens = input_tokens + output_tokens
        if policy.max_input_tokens is not None and input_tokens > policy.max_input_tokens:
            return "max_input_tokens"
        if policy.max_output_tokens is not None and output_tokens > policy.max_output_tokens:
            return "max_output_tokens"
        if policy.max_total_tokens is not None and total_tokens > policy.max_total_tokens:
            return "max_total_tokens"
        if policy.max_calls is not None and calls > policy.max_calls:
            return "max_calls"
        if policy.max_cost_usd is not None:
            cost = self._cost(input_tokens, output_tokens, model)
            if cost is None:
                return self._pricing(model)[1] if policy.fail_on_unknown_pricing else ""
            if cost > policy.max_cost_usd:
                return "max_cost_usd"
        return ""

    def can_start_call(self, *, estimated_input_tokens: int = 0, estimated_output_tokens: int = 0, model: str = "") -> bool:
        """Reserve a possible call. False means callers must cancel before it starts."""
        if self.exhausted_reason:
            return False
        if model:
            self.model = model
        if self.policy.fail_on_unknown_pricing and self._pricing(model)[0] is None:
            self.exhausted_reason = self._pricing(model)[1] or "unknown_pricing"
            return False
        reason = self._limit_reason(
            self.actual_input_tokens + max(0, int(estimated_input_tokens or 0)),
            self.actual_output_tokens + max(0, int(estimated_output_tokens or 0)),
            self.api_call_count + 1,
            model,
        )
        if reason:
            self.exhausted_reason = reason
            return False
        return True

    def record_usage(self, input_tokens: int | None, output_tokens: int | None, *, model: str = "") -> bool:
        """Record one completed provider call and fail closed when usage is absent."""
        if model:
            self.model = model
        if self.policy.fail_on_unknown_pricing and self._pricing(model)[0] is None:
            self.exhausted_reason = self._pricing(model)[1] or "unknown_pricing"
            return False
        if input_tokens is None or output_tokens is None:
            if self.policy.fail_on_missing_usage:
                self.exhausted_reason = "missing_usage"
                return False
            input_tokens, output_tokens = input_tokens or 0, output_tokens or 0
        self.actual_input_tokens += max(0, int(input_tokens))
        self.actual_output_tokens += max(0, int(output_tokens))
        self.api_call_count += 1
        reason = self._limit_reason(self.actual_input_tokens, self.actual_output_tokens, self.api_call_count, model)
        if reason:
            self.exhausted_reason = reason
            return False
        return True

    def remaining(self) -> dict[str, float | int | None]:
        cost = self._cost(self.actual_input_tokens, self.actual_output_tokens)
        return {
            "cost_usd": None if self.policy.max_cost_usd is None or cost is None else max(0.0, round(self.policy.max_cost_usd - cost, 6)),
            "input_tokens": None if self.policy.max_input_tokens is None else max(0, self.policy.max_input_tokens - self.actual_input_tokens),
            "output_tokens": None if self.policy.max_output_tokens is None else max(0, self.policy.max_output_tokens - self.actual_output_tokens),
            "total_tokens": None if self.policy.max_total_tokens is None else max(0, self.policy.max_total_tokens - self.actual_total_tokens),
            "calls": None if self.policy.max_calls is None else max(0, self.policy.max_calls - self.api_call_count),
        }

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "actual_input_tokens": self.actual_input_tokens,
            "actual_output_tokens": self.actual_output_tokens,
            "actual_total_tokens": self.actual_total_tokens,
            "api_call_count": self.api_call_count,
            "budget_policy": asdict(self.policy),
            "remaining_budget": self.remaining(),
            "budget_exhausted": bool(self.exhausted_reason),
            "budget_exhausted_reason": self.exhausted_reason,
        }
        cost = self._cost(self.actual_input_tokens, self.actual_output_tokens)
        if cost is not None:
            payload["cost_usd"] = round(cost, 6)
        return payload


def ensure_session(session_id: str) -> None:
    if not session_id:
        return
    now = _now()
    _events.setdefault(session_id, [])
    _started_at.setdefault(session_id, now)
    _last_activity_at.setdefault(session_id, now)
    _active_calls.setdefault(session_id, 0)
    _token_ledger.setdefault(session_id, {
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "actual_total_tokens": 0,
        "api_call_count": 0,
    })


def clear_session(session_id: str) -> None:
    _events.pop(session_id, None)
    _started_at.pop(session_id, None)
    _last_activity_at.pop(session_id, None)
    _active_calls.pop(session_id, None)
    _token_ledger.pop(session_id, None)
    _budget_ledgers.pop(session_id, None)
    _cancel_requested.discard(session_id)


def set_active_call(session_id: str, delta: int) -> int:
    if not session_id:
        return 0
    ensure_session(session_id)
    _active_calls[session_id] = max(0, _active_calls.get(session_id, 0) + delta)
    return _active_calls[session_id]


def active_calls(session_id: str) -> int:
    return _active_calls.get(session_id, 0)


def mark_cancel_requested(session_id: str) -> None:
    if session_id:
        ensure_session(session_id)
        _cancel_requested.add(session_id)


def cancel_requested(session_id: str) -> bool:
    return session_id in _cancel_requested


def configure_budget(session_id: str, policy: BudgetPolicy, *, model: str = "") -> BudgetLedger:
    """Attach a fail-closed budget policy to a session before its first call."""
    if not session_id:
        raise ValueError("session_id is required")
    ensure_session(session_id)
    ledger = BudgetLedger(policy=policy, model=model)
    _budget_ledgers[session_id] = ledger
    return ledger


def budget_allows_call(
    session_id: str,
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    model: str = "",
) -> bool:
    """Pre-call integration hook. False marks cancellation before provider I/O."""
    ledger = _budget_ledgers.get(session_id)
    if ledger is None:
        return True
    allowed = ledger.can_start_call(
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        model=model,
    )
    if not allowed:
        mark_cancel_requested(session_id)
        append_event(session_id, {
            "level": "warning",
            "phase": "token_ledger",
            "tool": "budget_preflight",
            "status": "cancelled",
            "message": f"budget_exhausted:{ledger.exhausted_reason}",
        })
    return allowed


def record_call_usage(
    session_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    model: str = "",
) -> bool:
    """Post-call integration hook. False stops the next call after a crossing."""
    if not session_id:
        return True
    ensure_session(session_id)
    ledger = _budget_ledgers.get(session_id)
    if ledger is None:
        add_token_usage(session_id, int(input_tokens or 0), int(output_tokens or 0))
        return True
    allowed = ledger.record_usage(input_tokens, output_tokens, model=model)
    _token_ledger[session_id] = {
        "actual_input_tokens": ledger.actual_input_tokens,
        "actual_output_tokens": ledger.actual_output_tokens,
        "actual_total_tokens": ledger.actual_total_tokens,
        "api_call_count": ledger.api_call_count,
    }
    if not allowed:
        mark_cancel_requested(session_id)
        append_event(session_id, {
            "level": "warning",
            "phase": "token_ledger",
            "tool": "budget_postflight",
            "status": "cancelled",
            "message": f"budget_exhausted:{ledger.exhausted_reason}",
        })
    return allowed


def add_token_usage(session_id: str, input_tokens: int, output_tokens: int) -> None:
    """Accumulate actual LLM usage for this session. Never call with secret values."""
    if not session_id:
        return
    ensure_session(session_id)
    budget_ledger = _budget_ledgers.get(session_id)
    if budget_ledger is not None:
        record_call_usage(session_id, input_tokens, output_tokens)
        return
    ledger = _token_ledger[session_id]
    ledger["actual_input_tokens"] += max(0, int(input_tokens or 0))
    ledger["actual_output_tokens"] += max(0, int(output_tokens or 0))
    ledger["actual_total_tokens"] = ledger["actual_input_tokens"] + ledger["actual_output_tokens"]
    ledger["api_call_count"] += 1


def _cost_for_model(model: str, input_tokens: int, output_tokens: int) -> tuple[float | None, str | None]:
    """Return (cost_usd, None) if model matches price table, else (None, reason)."""
    model_lower = model or ""
    for key, prices in _SORTED_PRICE_TABLE:
        if _matches_model_key(model_lower, key):
            cost = (
                input_tokens * prices["input_usd_per_1m"] / 1_000_000
                + output_tokens * prices["output_usd_per_1m"] / 1_000_000
            )
            return round(cost, 6), None
    return None, f"No price configured for model: {model or 'unknown'}"


def resolve_model_pricing(model: str) -> dict[str, Any] | None:
    """Return immutable-display pricing metadata using longest exact-safe matching."""
    model_lower = model or ""
    for key, prices in _SORTED_PRICE_TABLE:
        if _matches_model_key(model_lower, key):
            return {"model_match": key, **prices}
    return None


def session_token_ledger(session_id: str, model: str = "", estimated_input_tokens: int = 0) -> dict:
    """Return the current token ledger for UI display. Contains no secrets."""
    if not session_id:
        return {}
    ensure_session(session_id)
    budget_ledger = _budget_ledgers.get(session_id)
    ledger = budget_ledger.snapshot() if budget_ledger is not None else dict(_token_ledger[session_id])
    ledger["estimated_input_tokens"] = max(0, int(estimated_input_tokens or 0))
    ledger["pricing_version"] = PRICING_VERSION
    pricing = resolve_model_pricing(model)
    if pricing is not None:
        ledger["pricing"] = pricing
    cost_usd, cost_reason = _cost_for_model(
        model,
        ledger.get("actual_input_tokens", 0),
        ledger.get("actual_output_tokens", 0),
    )
    if cost_usd is not None:
        ledger["cost_usd"] = cost_usd
    else:
        ledger["cost_unavailable_reason"] = cost_reason or "cost unavailable"
        if session_id:
            append_event(session_id, {
                "level": "info",
                "phase": "token_ledger",
                "tool": "cost_estimate",
                "status": "heartbeat",
                "message": ledger["cost_unavailable_reason"],
            })
    return ledger


def append_event(session_id: str, event: dict[str, Any]) -> dict[str, Any]:
    if not session_id:
        return {}
    ensure_session(session_id)
    now = _now()
    started = _started_at.get(session_id, now)
    clean = _redact(event)
    entries = _events.setdefault(session_id, [])
    entry = {
        "id": len(entries) + 1,
        "timestamp": _iso(now),
        "level": clean.get("level", "info"),
        "phase": clean.get("phase", ""),
        "tool": clean.get("tool", ""),
        "window_id": clean.get("window_id", ""),
        "chapter_range": clean.get("chapter_range", ""),
        "prompt_label": clean.get("prompt_label", ""),
        "status": clean.get("status", "heartbeat"),
        "message": clean.get("message", ""),
        "elapsed_ms": int((now - started).total_seconds() * 1000),
        "duration_ms": clean.get("duration_ms"),
        "completed": clean.get("completed"),
        "total": clean.get("total"),
        "active_api_calls": active_calls(session_id),
        "error": clean.get("error", ""),
    }
    entries.append(entry)
    _last_activity_at[session_id] = now
    return entry


def list_events(session_id: str, after: int = 0) -> list[dict[str, Any]]:
    if not session_id:
        return []
    ensure_session(session_id)
    return list(_events.get(session_id, [])[max(after, 0):])


def session_status(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {
            "last_activity_at": "",
            "last_activity_message": "",
            "active_api_calls": 0,
            "elapsed_seconds": 0,
            "idle_seconds": 0,
            "cancel_requested": False,
        }
    ensure_session(session_id)
    now = _now()
    started = _started_at.get(session_id, now)
    last = _last_activity_at.get(session_id, started)
    entries = _events.get(session_id, [])
    return {
        "last_activity_at": _iso(last),
        "last_activity_message": entries[-1].get("message", "") if entries else "",
        "active_api_calls": active_calls(session_id),
        "elapsed_seconds": int((now - started).total_seconds()),
        "idle_seconds": int((now - last).total_seconds()),
        "cancel_requested": cancel_requested(session_id),
    }
