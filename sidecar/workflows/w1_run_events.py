"""In-memory W1 import activity feed.

This feed is separate from chunk extraction logs. It exists so long-running
supervisor imports can show the user what the AI is doing before a chunk/window
finishes and before proposals are written.
"""
from __future__ import annotations

from contextvars import ContextVar
from concurrent.futures import Future
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
import tempfile
from typing import Any

from sidecar.runtime.agent_runtime import LeaseLostError

_events: dict[str, list[dict[str, Any]]] = {}
_started_at: dict[str, datetime] = {}
_last_activity_at: dict[str, datetime] = {}
_active_calls: dict[str, int] = {}
_cancel_requested: set[str] = set()
_token_ledger: dict[str, dict[str, int]] = {}
_budget_ledgers: dict[str, "BudgetLedger"] = {}
_runtime_bindings: dict[str, tuple[Any, str, str, int]] = {}
_authorized_unknown_resumes: dict[str, "AuthorizedUnknownResume"] = {}
_runtime_tool_call_lock = RLock()
_cached_usage_lock = RLock()
_accounted_cached_operations: dict[str, set[str]] = {}
_provider_singleflight_lock = RLock()
_provider_singleflights: dict[str, Future[None]] = {}
_PROVIDER_RESPONSE_CONTRACT = "W1ProviderResponse/v1"
_compat_reservation_tokens: ContextVar[dict[str, tuple[str, ...]]] = ContextVar(
    "w1_compat_reservation_tokens", default={}
)

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


class ProviderCallRequiresHumanConfirmation(RuntimeError):
    """Fail-stop signal for a provider call whose billable outcome is unknown."""

    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(f"requires_human_confirmation:unknown_outcome:{idempotency_key}")


@dataclass(frozen=True)
class AuthorizedUnknownResume:
    """One immutable, durable approval set for a resumed provider boundary.

    The approval remains consent only until ``record_authorized_retry_intent``
    atomically replaces the unknown call with a retry intent.  Keeping this
    reference out of snapshots prevents a renderer or checkpoint from
    manufacturing a paid retry.
    """

    store: Any
    attempt_id: str
    owner_id: str
    fence_token: int
    tool_call_ids: frozenset[str]
    decision_keys: dict[str, str]


class CachedProviderResponse:
    """Minimal provider response reconstructed from a verified W1 artifact."""

    def __init__(
        self,
        content: Any,
        usage: dict[str, Any] | None = None,
        *,
        operation_key: str,
        artifact_receipt: dict[str, str],
    ) -> None:
        self.content = content
        self.usage_metadata = dict(usage or {})
        self.response_metadata: dict[str, Any] = {"w1_cache_hit": True}
        self.operation_key = operation_key
        self.artifact_receipt = artifact_receipt


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

    Concurrent callers own explicit tokens from ``reserve_call`` and pass them
    to ``record_usage`` or ``release_reservation``. Missing usage and unknown
    pricing exhaust a policy by default instead of allowing an unbounded run.
    """

    policy: BudgetPolicy
    model: str = ""
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    api_call_count: int = 0
    exhausted_reason: str = ""
    _reservations: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)
    _next_reservation_id: int = field(default=0, repr=False)
    _lock: RLock = field(default_factory=RLock, repr=False)

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

    def reserve_call(self, *, estimated_input_tokens: int = 0, estimated_output_tokens: int = 0, model: str = "") -> str | None:
        """Atomically reserve one provider call and return its settlement token."""
        with self._lock:
            if self.exhausted_reason:
                return None
            if model:
                self.model = model
            if self.policy.fail_on_unknown_pricing and self._pricing(model)[0] is None:
                self.exhausted_reason = self._pricing(model)[1] or "unknown_pricing"
                return None
            estimated = (max(0, int(estimated_input_tokens or 0)), max(0, int(estimated_output_tokens or 0)))
            reserved_input = sum(item[0] for item in self._reservations.values())
            reserved_output = sum(item[1] for item in self._reservations.values())
            reason = self._limit_reason(
                self.actual_input_tokens + reserved_input + estimated[0],
                self.actual_output_tokens + reserved_output + estimated[1],
                self.api_call_count + len(self._reservations) + 1,
                model,
            )
            if reason:
                # A competing in-flight reservation can finish or fail and
                # release capacity. Only permanently exhaust when this call
                # would exceed the budget without that transient capacity.
                base_reason = self._limit_reason(
                    self.actual_input_tokens + estimated[0],
                    self.actual_output_tokens + estimated[1],
                    self.api_call_count + 1,
                    model,
                )
                if base_reason:
                    self.exhausted_reason = base_reason
                return None
            self._next_reservation_id += 1
            token = f"reservation_{self._next_reservation_id}"
            self._reservations[token] = estimated
            return token

    def can_start_call(self, *, estimated_input_tokens: int = 0, estimated_output_tokens: int = 0, model: str = "") -> bool:
        """Compatibility boolean API; prefer ``reserve_call`` for concurrent I/O."""
        return self.reserve_call(
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            model=model,
        ) is not None

    def release_reservation(self, reservation_token: str | None = None) -> None:
        """Release the reservation identified by one provider caller."""
        with self._lock:
            token = reservation_token
            if token is None and len(self._reservations) == 1:
                token = next(iter(self._reservations))
            if token:
                self._reservations.pop(token, None)

    def record_usage(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        *,
        model: str = "",
        reservation_token: str | None = None,
    ) -> bool:
        """Record one completed provider call and fail closed when usage is absent."""
        with self._lock:
            if model:
                self.model = model
            if self.policy.fail_on_unknown_pricing and self._pricing(model)[0] is None:
                self.exhausted_reason = self._pricing(model)[1] or "unknown_pricing"
                return False
            token = reservation_token
            if token is None and len(self._reservations) == 1:
                token = next(iter(self._reservations))
            if token:
                self._reservations.pop(token, None)
            # The provider has returned, so this call happened even when its
            # token metadata is absent and the run must fail closed.
            self.api_call_count += 1
            if input_tokens is None or output_tokens is None:
                if self.policy.fail_on_missing_usage:
                    self.exhausted_reason = "missing_usage"
                    return False
                input_tokens, output_tokens = input_tokens or 0, output_tokens or 0
            self.actual_input_tokens += max(0, int(input_tokens))
            self.actual_output_tokens += max(0, int(output_tokens))
            reserved_input = sum(item[0] for item in self._reservations.values())
            reserved_output = sum(item[1] for item in self._reservations.values())
            reason = self._limit_reason(
                self.actual_input_tokens + reserved_input,
                self.actual_output_tokens + reserved_output,
                self.api_call_count + len(self._reservations),
                model,
            )
            if reason:
                self.exhausted_reason = reason
                return False
            return True

    def remaining(self) -> dict[str, float | int | None]:
        with self._lock:
            reserved_input = sum(item[0] for item in self._reservations.values())
            reserved_output = sum(item[1] for item in self._reservations.values())
            effective_input = self.actual_input_tokens + reserved_input
            effective_output = self.actual_output_tokens + reserved_output
            cost = self._cost(effective_input, effective_output)
            return {
                "cost_usd": None if self.policy.max_cost_usd is None or cost is None else max(0.0, round(self.policy.max_cost_usd - cost, 6)),
                "input_tokens": None if self.policy.max_input_tokens is None else max(0, self.policy.max_input_tokens - effective_input),
                "output_tokens": None if self.policy.max_output_tokens is None else max(0, self.policy.max_output_tokens - effective_output),
                "total_tokens": None if self.policy.max_total_tokens is None else max(0, self.policy.max_total_tokens - effective_input - effective_output),
                "calls": None if self.policy.max_calls is None else max(0, self.policy.max_calls - self.api_call_count - len(self._reservations)),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
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
    _runtime_bindings.pop(session_id, None)
    _authorized_unknown_resumes.pop(session_id, None)
    _accounted_cached_operations.pop(session_id, None)
    _cancel_requested.discard(session_id)
    bound = dict(_compat_reservation_tokens.get())
    if session_id in bound:
        bound.pop(session_id, None)
        _compat_reservation_tokens.set(bound)
    with _provider_singleflight_lock:
        for operation_key, flight in tuple(_provider_singleflights.items()):
            if flight.done():
                _provider_singleflights.pop(operation_key, None)


def set_active_call(session_id: str, delta: int) -> int:
    if not session_id:
        return 0
    ensure_session(session_id)
    _active_calls[session_id] = max(0, _active_calls.get(session_id, 0) + delta)
    return _active_calls[session_id]


def active_calls(session_id: str) -> int:
    return _active_calls.get(session_id, 0)


def append_provider_wait_heartbeat(
    session_id: str, *, model: str = "",
) -> dict[str, Any]:
    """Publish one durable liveness pulse only while provider I/O is active."""
    count = active_calls(session_id)
    if not session_id or count <= 0:
        return {}
    configured = _budget_ledgers.get(session_id)
    effective_model = model or (configured.model if configured is not None else "")
    ledger = (
        authoritative_usage_ledger(session_id, effective_model)
        if effective_model
        else {
            "actual_calls": 0,
            "budget_status": {"remaining": {}},
        }
    )
    return append_event(session_id, {
        "phase": "provider_call",
        "tool": "provider.chat.completions",
        "status": "heartbeat",
        "message": f"Waiting for {count} active provider call(s).",
        "completed": ledger.get("actual_calls", 0),
        "total": (
            ledger.get("budget_status", {})
            .get("remaining", {})
            .get("calls")
        ),
    })


def mark_cancel_requested(session_id: str) -> None:
    if session_id:
        ensure_session(session_id)
        _cancel_requested.add(session_id)


def clear_cancel_requested(session_id: str) -> None:
    if session_id:
        _cancel_requested.discard(session_id)


def cancel_requested(session_id: str) -> bool:
    return session_id in _cancel_requested


def configure_budget(session_id: str, policy: BudgetPolicy, *, model: str = "") -> BudgetLedger:
    """Attach a fail-closed budget policy to a session before its first call."""
    if not session_id:
        raise ValueError("session_id is required")
    ensure_session(session_id)
    existing = _budget_ledgers.get(session_id)
    if existing is not None:
        if existing.policy != policy or (model and existing.model and existing.model != model):
            raise ValueError("budget_policy_reconfiguration_rejected")
        if model and not existing.model:
            existing.model = model
        return existing
    ledger = BudgetLedger(policy=policy, model=model)
    _budget_ledgers[session_id] = ledger
    _accounted_cached_operations[session_id] = set()
    return ledger


def _bind_compat_reservation(session_id: str, reservation_token: str) -> None:
    bound = dict(_compat_reservation_tokens.get())
    bound[session_id] = (*bound.get(session_id, ()), reservation_token)
    _compat_reservation_tokens.set(bound)


def bind_runtime(session_id: str, store: Any, attempt_id: str, owner_id: str, fence_token: int) -> None:
    """Mirror legacy activity into the durable runtime event stream."""
    ensure_session(session_id)
    _runtime_bindings[session_id] = (store, attempt_id, owner_id, fence_token)


def configure_authorized_unknown_resume(
    session_id: str,
    *,
    source_attempt_id: str,
    tool_call_ids: list[str] | tuple[str, ...],
    decision_keys: list[str] | tuple[str, ...],
) -> None:
    """Bind one strictly validated unknown-outcome retry set to a session.

    This function does not consume a decision or create a provider intent.  It
    merely pins the source attempt and its durable consent until the next
    matching provider operation reaches its atomic pre-network boundary.
    """
    binding = _runtime_bindings.get(session_id)
    if binding is None:
        raise ValueError("unknown_retry_runtime_binding_missing")
    store, active_attempt_id, owner_id, active_fence_token = binding
    ids = [str(item) for item in tool_call_ids]
    keys = [str(item) for item in decision_keys]
    if (
        not ids
        or len(ids) != len(set(ids))
        or len(keys) != len(ids)
        or len(keys) != len(set(keys))
    ):
        raise ValueError("unknown_retry_authorization_shape_invalid")

    summaries = store.list_unknown_call_summaries(source_attempt_id)
    by_id = {str(item.get("tool_call_id")): item for item in summaries}
    if set(ids) != set(by_id):
        raise ValueError("unknown_retry_authorization_call_ids_mismatch")
    expected_keys = {
        call_id: str(summary.get("decision_key") or "")
        for call_id, summary in by_id.items()
    }
    if len(expected_keys) != len(set(expected_keys.values())) or set(keys) != set(expected_keys.values()) or any(
        summary.get("decision_state") != "authorize_retry_once"
        for summary in by_id.values()
    ):
        raise ValueError("unknown_retry_authorization_not_durable")

    if source_attempt_id == active_attempt_id:
        source_fence_token = active_fence_token
    else:
        source_attempt = store.get_attempt(source_attempt_id) or {}
        if source_attempt.get("status") == "cancelled":
            raise ValueError("unknown_retry_source_attempt_cancelled")
        # A stable source attempt has no active worker.  Lease it under the
        # recovered worker so RuntimeStore can atomically consume the original
        # authorization without allowing a child attempt to mutate parent data.
        source_lease = store.acquire_lease(source_attempt_id, owner_id, ttl_seconds=60)
        source_fence_token = int(source_lease["fence_token"])

    _authorized_unknown_resumes[session_id] = AuthorizedUnknownResume(
        store=store,
        attempt_id=source_attempt_id,
        owner_id=owner_id,
        fence_token=int(source_fence_token),
        tool_call_ids=frozenset(ids),
        decision_keys=expected_keys,
    )


def _unknown_resume_binding(session_id: str) -> tuple[Any, str, str, int] | None:
    configured = _authorized_unknown_resumes.get(session_id)
    if configured is None:
        return None
    return (
        configured.store,
        configured.attempt_id,
        configured.owner_id,
        configured.fence_token,
    )


def _unknown_retry_is_authorized(
    session_id: str,
    attempt_id: str,
    call: dict[str, Any],
) -> bool:
    configured = _authorized_unknown_resumes.get(session_id)
    if configured is not None and configured.attempt_id == attempt_id:
        call_id = str(call.get("tool_call_id") or "")
        expected_key = configured.decision_keys.get(call_id)
        return (
            call_id in configured.tool_call_ids
            and bool(expected_key)
            and expected_key == _retry_decision_key(_unknown_call_key(attempt_id, call))
            and _retry_is_authorized(configured.store, attempt_id, _unknown_call_key(attempt_id, call))
        )
    key = str(call.get("intent_payload", {}).get("idempotency_key", ""))
    binding = _runtime_bindings.get(session_id)
    return bool(binding and key and _retry_is_authorized(binding[0], attempt_id, key))


def _unknown_bindings(session_id: str) -> list[tuple[Any, str, str, int]]:
    binding = _runtime_bindings.get(session_id)
    if binding is None:
        return []
    bindings = [binding]
    source_binding = _unknown_resume_binding(session_id)
    if source_binding is not None and source_binding[1] != binding[1]:
        bindings.append(source_binding)
    return bindings


def provider_message_hash(messages: list[Any]) -> str:
    """Hash provider input without returning or persisting message content."""
    canonical = []
    for message in messages:
        canonical.append({
            "type": type(message).__name__,
            "content": getattr(message, "content", ""),
        })
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def provider_result_hash(response: Any) -> str:
    content = getattr(response, "content", "")
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _provider_operation_inputs(session_id: str, model: str, message_hash: str) -> dict[str, str] | None:
    binding = _runtime_bindings.get(session_id)
    if binding is None:
        return None
    store, attempt_id, _owner_id, _fence_token = binding
    attempt = store.get_attempt(attempt_id) or {}
    run = store.get_run(str(attempt.get("run_id") or "")) or {}
    config = dict(run.get("config") or {})
    context = dict(config.get("context") or {})
    version_inputs = {
        "profile": str(config.get("prompt_profile") or config.get("profile") or context.get("prompt_profile") or "balanced"),
        "config_version": str(config.get("config_version") or context.get("config_version") or "w1-provider-config-v1"),
        "prompt_version": str(config.get("prompt_version") or context.get("prompt_version") or "w1-prompts-v1"),
        "schema_version": str(config.get("schema_version") or context.get("schema_version") or "w1-schema-v1"),
        "tool_version": str(config.get("tool_version") or context.get("tool_version") or "w1-tools-v1"),
    }
    return {
        "lineage_id": str(run.get("lineage_id") or ""),
        "model": model,
        "message_hash": message_hash,
        "profile_hash": hashlib.sha256(version_inputs["profile"].encode("utf-8")).hexdigest(),
        "prompt_hash": hashlib.sha256(version_inputs["prompt_version"].encode("utf-8")).hexdigest(),
        "schema_hash": hashlib.sha256(version_inputs["schema_version"].encode("utf-8")).hexdigest(),
        "tool_hash": hashlib.sha256(version_inputs["tool_version"].encode("utf-8")).hexdigest(),
        "config_hash": hashlib.sha256(version_inputs["config_version"].encode("utf-8")).hexdigest(),
    }


def provider_operation_key(session_id: str, *, model: str, message_hash: str) -> str | None:
    """Return the sequence-independent identity for one W1 provider operation."""
    inputs = _provider_operation_inputs(session_id, model, message_hash)
    if inputs is None:
        return None
    return hashlib.sha256(_canonical_json({"contract": _PROVIDER_RESPONSE_CONTRACT, **inputs}).encode("utf-8")).hexdigest()


def begin_provider_singleflight(operation_key: str) -> tuple[bool, Future[None]]:
    """Elect one in-process caller without binding synchronization to an event loop."""
    with _provider_singleflight_lock:
        existing = _provider_singleflights.get(operation_key)
        if existing is not None:
            return False, existing
        flight: Future[None] = Future()
        _provider_singleflights[operation_key] = flight
        return True, flight


def finish_provider_singleflight(operation_key: str, flight: Future[None], error: BaseException | None = None) -> None:
    with _provider_singleflight_lock:
        if not flight.done():
            if error is None:
                flight.set_result(None)
            else:
                flight.set_exception(error)
        if _provider_singleflights.get(operation_key) is flight:
            _provider_singleflights.pop(operation_key, None)


def _provider_artifact_dir(store: Any, inputs: dict[str, str], operation_key: str) -> Path:
    lineage_id = inputs["lineage_id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", lineage_id):
        raise ValueError("invalid_provider_artifact_lineage")
    project_root = Path(store.project_root).resolve()
    directory = (
        project_root / "system" / "imports" / lineage_id
        / "provider_responses" / operation_key
    )
    return directory


def _provider_cache_path_is_safe(project_root: Path, directory: Path, artifact: Path | None = None) -> bool:
    provider_root = directory.parent
    paths = (provider_root, directory) if artifact is None else (provider_root, directory, artifact)
    try:
        return all(
            not path.is_symlink()
            and path.resolve(strict=False).is_relative_to(project_root)
            for path in paths
        )
    except OSError:
        return False


def _secure_provider_artifact_directory(project_root: Path, directory: Path) -> None:
    if not _provider_cache_path_is_safe(project_root, directory):
        raise RuntimeError("provider_cache_symlink_or_escape_rejected")
    provider_root = directory.parent
    provider_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not _provider_cache_path_is_safe(project_root, directory):
        raise RuntimeError("provider_cache_symlink_or_escape_rejected")
    os.chmod(provider_root, 0o700)
    directory.mkdir(mode=0o700, exist_ok=True)
    if not _provider_cache_path_is_safe(project_root, directory):
        raise RuntimeError("provider_cache_symlink_or_escape_rejected")
    os.chmod(directory, 0o700)


def _load_verified_provider_artifact(session_id: str, *, model: str, message_hash: str) -> CachedProviderResponse | None:
    binding = _runtime_bindings.get(session_id)
    inputs = _provider_operation_inputs(session_id, model, message_hash)
    operation_key = provider_operation_key(session_id, model=model, message_hash=message_hash)
    if binding is None or inputs is None or operation_key is None:
        return None
    directory = _provider_artifact_dir(binding[0], inputs, operation_key)
    project_root = Path(binding[0].project_root).resolve()
    if not _provider_cache_path_is_safe(project_root, directory):
        return None
    try:
        if (directory.parent.stat().st_mode & 0o777) != 0o700 or (directory.stat().st_mode & 0o777) != 0o700:
            return None
    except OSError:
        return None
    for path in sorted(directory.glob("*.json")):
        try:
            if not _provider_cache_path_is_safe(project_root, directory, path):
                continue
            if (path.stat().st_mode & 0o777) != 0o600:
                continue
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            artifact_hash = hashlib.sha256(raw).hexdigest()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if path.stem != artifact_hash or not isinstance(payload, dict):
            continue
        if payload.get("contract") != _PROVIDER_RESPONSE_CONTRACT or payload.get("operation_key") != operation_key:
            continue
        if payload.get("operation_inputs") != inputs:
            continue
        content = payload.get("response_content")
        if payload.get("response_hash") != hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest():
            continue
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            continue
        return CachedProviderResponse(
            content,
            usage,
            operation_key=operation_key,
            artifact_receipt={
                "operation_key": operation_key,
                "artifact_path": str(path.relative_to(project_root)),
                "artifact_hash": artifact_hash,
            },
        )
    return None


def persist_provider_response(
    session_id: str,
    *,
    model: str,
    message_hash: str,
    response: Any,
    input_tokens: int | None,
    output_tokens: int | None,
) -> dict[str, str] | None:
    """Atomically write the completed response before its runtime receipt is recorded."""
    binding = _runtime_bindings.get(session_id)
    inputs = _provider_operation_inputs(session_id, model, message_hash)
    operation_key = provider_operation_key(session_id, model=model, message_hash=message_hash)
    if binding is None or inputs is None or operation_key is None:
        return None
    content = getattr(response, "content", "")
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    payload = {
        "contract": _PROVIDER_RESPONSE_CONTRACT,
        "operation_key": operation_key,
        "operation_inputs": inputs,
        "model": model,
        "response_content": content,
        "response_hash": hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest(),
        "usage": usage,
        "safe_input_hash": message_hash,
        "safe_config_hash": inputs["config_hash"],
    }
    raw = _canonical_json(payload).encode("utf-8")
    artifact_hash = hashlib.sha256(raw).hexdigest()
    directory = _provider_artifact_dir(binding[0], inputs, operation_key)
    project_root = Path(binding[0].project_root).resolve()
    _secure_provider_artifact_directory(project_root, directory)
    destination = directory / f"{artifact_hash}.json"
    if not _provider_cache_path_is_safe(project_root, directory, destination):
        raise RuntimeError("provider_cache_symlink_or_escape_rejected")
    needs_write = not destination.exists() or destination.read_bytes() != raw
    if needs_write:
        fd, temporary_name = tempfile.mkstemp(prefix=".provider_response_", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            if not _provider_cache_path_is_safe(project_root, directory, destination):
                raise RuntimeError("provider_cache_symlink_or_escape_rejected")
            os.replace(temporary_name, destination)
            if not _provider_cache_path_is_safe(project_root, directory, destination):
                raise RuntimeError("provider_cache_symlink_or_escape_rejected")
            os.chmod(destination, 0o600)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
    else:
        os.chmod(destination, 0o600)
    return {
        "operation_key": operation_key,
        "artifact_path": str(destination.relative_to(project_root)),
        "artifact_hash": artifact_hash,
    }


def _retry_decision_key(idempotency_key: str) -> str:
    return f"retry_provider_call:{idempotency_key}"


def _retry_is_authorized(store: Any, attempt_id: str, idempotency_key: str) -> bool:
    expected = _retry_decision_key(idempotency_key)
    return any(
        decision.get("decision_key") == expected
        and decision.get("decision") == "authorize_retry_once"
        for decision in store.list_human_decisions(attempt_id)
    )


def _unknown_call_key(attempt_id: str, call: dict[str, Any]) -> str:
    key = str(call.get("intent_payload", {}).get("idempotency_key", ""))
    return key or hashlib.sha256(
        f"{attempt_id}:{call.get('tool_call_id', '')}".encode("utf-8")
    ).hexdigest()


def _block_for_unknown_call(
    session_id: str, store: Any, attempt_id: str, owner_id: str,
    fence_token: int, call: dict[str, Any],
) -> None:
    mark_cancel_requested(session_id)
    store.set_attempt_status(
        attempt_id,
        "waiting_human",
        owner_id=owner_id,
        fence_token=fence_token,
    )
    raise ProviderCallRequiresHumanConfirmation(_unknown_call_key(attempt_id, call))


def guard_pending_provider_unknown_outcomes(session_id: str) -> None:
    """Block cache and provider paths without consuming an unknown-call decision."""
    for store, attempt_id, owner_id, fence_token in _unknown_bindings(session_id):
        unknown_calls = [
            call for call in store.list_tool_calls(attempt_id)
            if call.get("status") == "unknown_outcome"
        ]
        for call in unknown_calls:
            if _unknown_retry_is_authorized(session_id, attempt_id, call):
                continue
            _block_for_unknown_call(
                session_id, store, attempt_id, owner_id, fence_token, call,
            )


def reconcile_authorized_unknown_from_cache(
    session_id: str, *, model: str, message_hash: str,
    artifact_receipt: dict[str, str],
) -> bool:
    """Consume only the authorized unknown exactly matched by a verified cache hit."""
    bindings = _unknown_bindings(session_id)
    if not bindings:
        return False
    with _runtime_tool_call_lock:
        guard_pending_provider_unknown_outcomes(session_id)
        matches: list[tuple[Any, str, str, int, dict[str, Any]]] = []
        for store, attempt_id, owner_id, fence_token in bindings:
            for call in store.list_tool_calls(attempt_id):
                if (
                    call.get("status") == "unknown_outcome"
                    and call.get("intent_payload", {}).get("model") == model
                    and call.get("intent_payload", {}).get("message_hash") == message_hash
                ):
                    matches.append((store, attempt_id, owner_id, fence_token, call))
        if not matches:
            return False
        if len(matches) != 1:
            _store, attempt_id, owner_id, fence_token, call = matches[0]
            _block_for_unknown_call(session_id, _store, attempt_id, owner_id, fence_token, call)
        store, attempt_id, owner_id, fence_token, matching = matches[0]
        key = _unknown_call_key(attempt_id, matching)
        store.resolve_authorized_unknown_with_artifact(
            attempt_id, matching["tool_call_id"], _retry_decision_key(key), artifact_receipt,
            owner_id=owner_id, fence_token=fence_token,
        )
        clear_cancel_requested(session_id)
        return True


def restore_durable_provider_history(session_id: str) -> dict[str, int]:
    """Restore paid usage and consume authorized unknowns backed by verified artifacts.

    A checkpoint resume can skip the node that originally requested a response.
    Reconcile its durable provider history before any downstream call so the
    human authorization and lifetime budget remain effective across restarts.
    """
    bindings = _unknown_bindings(session_id)
    if not bindings:
        return {"accounted": 0, "reconciled": 0}
    accounted = 0
    reconciled = 0
    for store, attempt_id, _owner_id, _fence_token in bindings:
        for call in store.list_tool_calls(attempt_id):
            if call.get("tool_name") != "provider.chat.completions":
                continue
            intent = call.get("intent_payload") or {}
            model = str(intent.get("model") or "")
            message_hash = str(intent.get("message_hash") or "")
            if not model or not message_hash:
                continue

            status = call.get("status")
            if status == "unknown_outcome":
                if not _unknown_retry_is_authorized(session_id, attempt_id, call):
                    continue
                cached = _load_verified_provider_artifact(
                    session_id, model=model, message_hash=message_hash,
                )
                if cached is None:
                    continue
                if reconcile_authorized_unknown_from_cache(
                    session_id, model=model, message_hash=message_hash,
                    artifact_receipt=cached.artifact_receipt,
                ):
                    reconciled += 1
                if not record_cached_call_usage_once(
                    session_id, cached.operation_key, cached.usage_metadata, model=model,
                ):
                    reason = authoritative_usage_ledger(session_id, model).get(
                        "budget_status", {}
                    ).get("reason", "budget_exhausted")
                    raise RuntimeError(
                        f"budget_exhausted: durable provider response denied ({reason})"
                    )
                accounted += 1
                continue

            if status == "retry_consumed":
                result = call.get("result_payload") or {}
                if result.get("outcome") != "resolved_from_verified_artifact":
                    continue
                cached = _load_verified_provider_artifact(
                    session_id, model=model, message_hash=message_hash,
                )
                if cached is None:
                    continue
                if not record_cached_call_usage_once(
                    session_id, cached.operation_key, cached.usage_metadata, model=model,
                ):
                    reason = authoritative_usage_ledger(session_id, model).get(
                        "budget_status", {}
                    ).get("reason", "budget_exhausted")
                    raise RuntimeError(
                        f"budget_exhausted: reconciled provider usage denied ({reason})"
                    )
                accounted += 1
                continue

            if status != "result":
                continue
            result = call.get("result_payload") or {}
            receipt = result.get("artifact_receipt") or {}
            operation_key = str(receipt.get("operation_key") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", operation_key):
                operation_key = provider_operation_key(
                    session_id, model=model, message_hash=message_hash,
                ) or ""
            if not operation_key:
                continue
            if not record_cached_call_usage_once(
                session_id,
                operation_key,
                {
                    "input_tokens": result.get("input_tokens"),
                    "output_tokens": result.get("output_tokens"),
                },
                model=model,
            ):
                reason = authoritative_usage_ledger(session_id, model).get(
                    "budget_status", {}
                ).get("reason", "budget_exhausted")
                raise RuntimeError(
                    f"budget_exhausted: durable provider usage denied ({reason})"
                )
            accounted += 1
    if reconciled:
        append_event(session_id, {
            "phase": "recovery",
            "tool": "provider_history",
            "status": "success",
            "message": (
                f"Recovered {reconciled} authorized provider result(s) from "
                "verified durable artifacts."
            ),
        })
    return {"accounted": accounted, "reconciled": reconciled}


def begin_provider_call(
    session_id: str,
    *,
    model: str,
    message_hash: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> dict[str, Any]:
    """Persist a redacted provider-call intent before network I/O."""
    binding = _runtime_bindings.get(session_id)
    if binding is None:
        fallback_key = hashlib.sha256(
            f"unmanaged:{session_id}:{model}:{message_hash}".encode("utf-8")
        ).hexdigest()
        return {"managed": False, "idempotency_key": fallback_key}

    store, attempt_id, owner_id, fence_token = binding
    with _runtime_tool_call_lock:
        # Budget reservation and cancellation are checked by the caller before
        # this point.  Only after those checks do we atomically consume the
        # exact durable approval which matches this provider input.
        guard_pending_provider_unknown_outcomes(session_id)
        matching_authorized: list[dict[str, Any]] = []
        retry_binding: tuple[Any, str, str, int] | None = None
        pending_authorized: list[tuple[Any, str, str, int, dict[str, Any]]] = []
        for candidate_binding in _unknown_bindings(session_id):
            candidate_store, candidate_attempt_id, candidate_owner_id, candidate_fence_token = candidate_binding
            candidate_unknown = [
                call for call in candidate_store.list_tool_calls(candidate_attempt_id)
                if call.get("status") == "unknown_outcome"
            ]
            pending_authorized.extend(
                (candidate_store, candidate_attempt_id, candidate_owner_id, candidate_fence_token, call)
                for call in candidate_unknown
            )
            matches = [
                item for item in candidate_unknown
                if item.get("intent_payload", {}).get("message_hash") == message_hash
                and item.get("intent_payload", {}).get("model") == model
                and _unknown_retry_is_authorized(session_id, candidate_attempt_id, item)
            ]
            if matches:
                matching_authorized.extend(matches)
                retry_binding = (
                    candidate_store, candidate_attempt_id,
                    candidate_owner_id, candidate_fence_token,
                )

        if pending_authorized and not matching_authorized:
            blocked_store, blocked_attempt_id, blocked_owner_id, blocked_fence_token, blocked_call = pending_authorized[0]
            _block_for_unknown_call(
                session_id, blocked_store, blocked_attempt_id,
                blocked_owner_id, blocked_fence_token, blocked_call,
            )
        if len(matching_authorized) > 1 or (
            matching_authorized and retry_binding is None
        ):
            call = matching_authorized[0]
            _block_for_unknown_call(session_id, store, attempt_id, owner_id, fence_token, call)
        if matching_authorized:
            store, attempt_id, owner_id, fence_token = retry_binding  # type: ignore[misc]
            store.heartbeat_lease(attempt_id, owner_id, fence_token, ttl_seconds=60)

        existing_calls = store.list_tool_calls(attempt_id)

        sequence = len(existing_calls) + 1
        idempotency_key = hashlib.sha256(
            f"{attempt_id}:{sequence}:{model}:{message_hash}".encode("utf-8")
        ).hexdigest()
        tool_call_id = f"w1_provider_{idempotency_key[:32]}"
        payload = {
            "message_hash": message_hash,
            "model": model,
            "estimated_input_tokens": max(0, int(estimated_input_tokens or 0)),
            "estimated_output_tokens": max(0, int(estimated_output_tokens or 0)),
            "sequence": sequence,
            "idempotency_key": idempotency_key,
        }
        matching_unknown = matching_authorized[0] if matching_authorized else None
        if matching_unknown is not None:
            unknown_key = str(matching_unknown["intent_payload"]["idempotency_key"])
            call = store.record_authorized_retry_intent(
                attempt_id,
                matching_unknown["tool_call_id"],
                _retry_decision_key(unknown_key),
                "provider.chat.completions",
                payload,
                tool_call_id=tool_call_id,
                owner_id=owner_id,
                fence_token=fence_token,
            )
            clear_cancel_requested(session_id)
        else:
            call = store.record_tool_intent(
                attempt_id,
                "provider.chat.completions",
                payload,
                tool_call_id=tool_call_id,
                owner_id=owner_id,
                fence_token=fence_token,
            )
        return {
            "managed": True,
            "store": store,
            "attempt_id": attempt_id,
            "tool_call_id": call["tool_call_id"],
            "idempotency_key": idempotency_key,
            "owner_id": owner_id,
            "fence_token": fence_token,
        }


def settle_provider_success(
    call: dict[str, Any], *, model: str, input_tokens: int | None,
    output_tokens: int | None, result_hash: str, artifact_receipt: dict[str, str] | None = None,
) -> None:
    if not call.get("managed"):
        return
    call["store"].record_tool_result(call["tool_call_id"], {
        "outcome": "success",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "result_hash": result_hash,
        "idempotency_key": call["idempotency_key"],
        **({"artifact_receipt": artifact_receipt} if artifact_receipt else {}),
    }, attempt_id=call["attempt_id"], owner_id=call["owner_id"], fence_token=call["fence_token"])


def settle_provider_failure(call: dict[str, Any], *, failure_type: str, status_code: int | None = None) -> None:
    if not call.get("managed"):
        return
    store = call["store"]
    payload = {
        "outcome": "failed",
        "failure_type": failure_type,
        "status_code": status_code,
        "idempotency_key": call["idempotency_key"],
    }
    if hasattr(store, "record_tool_failure"):
        store.record_tool_failure(
            call["tool_call_id"], payload, attempt_id=call["attempt_id"],
            owner_id=call["owner_id"], fence_token=call["fence_token"],
        )
    else:
        store._update_tool_call(
            call["tool_call_id"], "failed", payload=payload, reason=failure_type,
            attempt_id=call["attempt_id"], owner_id=call["owner_id"],
            fence_token=call["fence_token"],
        )


def settle_provider_unknown(session_id: str, call: dict[str, Any], *, reason: str) -> ProviderCallRequiresHumanConfirmation:
    idempotency_key = str(call.get("idempotency_key", "unmanaged"))
    if call.get("managed"):
        store = call["store"]
        store.record_tool_unknown_outcome(
            call["tool_call_id"], reason, attempt_id=call["attempt_id"],
            owner_id=call["owner_id"], fence_token=call["fence_token"],
        )
        store.set_attempt_status(
            call["attempt_id"], "waiting_human", owner_id=call["owner_id"],
            fence_token=call["fence_token"],
        )
    mark_cancel_requested(session_id)
    append_event(session_id, {
        "level": "warning",
        "phase": "provider_call",
        "tool": "provider.chat.completions",
        "status": "waiting_human",
        "message": "requires_human_confirmation:unknown_outcome",
    })
    return ProviderCallRequiresHumanConfirmation(idempotency_key)


def _take_compat_reservation(session_id: str) -> str | None:
    bound = dict(_compat_reservation_tokens.get())
    tokens = bound.get(session_id, ())
    if not tokens:
        return None
    token = tokens[-1]
    remaining = tokens[:-1]
    if remaining:
        bound[session_id] = remaining
    else:
        bound.pop(session_id, None)
    _compat_reservation_tokens.set(bound)
    return token


def reserve_call_budget(
    session_id: str,
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    model: str = "",
) -> str | None:
    """Reserve budget and return a caller-owned token; empty means unmanaged."""
    ledger = _budget_ledgers.get(session_id)
    if ledger is None:
        return ""
    token = ledger.reserve_call(
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        model=model,
    )
    if token is None and ledger.exhausted_reason:
        mark_cancel_requested(session_id)
        append_event(session_id, {
            "level": "warning",
            "phase": "token_ledger",
            "tool": "budget_preflight",
            "status": "cancelled",
            "message": f"budget_exhausted:{ledger.exhausted_reason}",
        })
    return token


def budget_allows_call(
    session_id: str,
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    model: str = "",
) -> bool:
    """Pre-call integration hook; false can mean transient reserved capacity."""
    token = reserve_call_budget(
        session_id,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        model=model,
    )
    if token:
        _bind_compat_reservation(session_id, token)
    return token is not None


def record_call_usage(
    session_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    model: str = "",
    reservation_token: str | None = None,
) -> bool:
    """Post-call integration hook. False stops the next call after a crossing."""
    if not session_id:
        return True
    ensure_session(session_id)
    ledger = _budget_ledgers.get(session_id)
    if ledger is None:
        add_token_usage(session_id, int(input_tokens or 0), int(output_tokens or 0))
        return True
    token = reservation_token if reservation_token is not None else _take_compat_reservation(session_id)
    allowed = ledger.record_usage(
        input_tokens,
        output_tokens,
        model=model,
        reservation_token=token,
    )
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


def mark_operation_usage_accounted(session_id: str, operation_key: str) -> None:
    if not session_id or not operation_key:
        return
    with _cached_usage_lock:
        _accounted_cached_operations.setdefault(session_id, set()).add(operation_key)


def record_cached_call_usage_once(
    session_id: str,
    operation_key: str,
    usage: dict[str, Any],
    *,
    model: str,
) -> bool:
    """Restore paid cached usage once without creating a call reservation."""
    with _cached_usage_lock:
        accounted = _accounted_cached_operations.setdefault(session_id, set())
        if operation_key in accounted:
            ledger = _budget_ledgers.get(session_id)
            return ledger is None or not bool(ledger.exhausted_reason)
        accounted.add(operation_key)
        return record_call_usage(
            session_id,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            model=model,
        )


def release_call_reservation(session_id: str, reservation_token: str | None = None) -> None:
    """Release the reservation held by a provider call that raised before response."""
    ledger = _budget_ledgers.get(session_id)
    if ledger is not None:
        token = reservation_token if reservation_token is not None else _take_compat_reservation(session_id)
        ledger.release_reservation(token)


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


def authoritative_usage_ledger(session_id: str, model: str = "") -> dict[str, Any]:
    """Return the one non-secret, durable usage record for a W1 run."""
    ledger = session_token_ledger(session_id, model=model)
    return {
        "schema_version": "w1_usage_ledger/v1",
        "model": model,
        "actual_input_tokens": int(ledger.get("actual_input_tokens", 0) or 0),
        "actual_output_tokens": int(ledger.get("actual_output_tokens", 0) or 0),
        "actual_total_tokens": int(ledger.get("actual_total_tokens", 0) or 0),
        "actual_calls": int(ledger.get("api_call_count", 0) or 0),
        # Keep the UI/session field as a compatibility alias for smoke tooling.
        "api_call_count": int(ledger.get("api_call_count", 0) or 0),
        "cost_usd": ledger.get("cost_usd"),
        "budget_status": {
            "exhausted": bool(ledger.get("budget_exhausted", False)),
            "reason": str(ledger.get("budget_exhausted_reason", "") or ""),
            "remaining": ledger.get("remaining_budget", {}),
        },
        "pricing": ledger.get("pricing"),
        "pricing_version": ledger.get("pricing_version", PRICING_VERSION),
    }


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
    binding = _runtime_bindings.get(session_id)
    if binding is not None:
        store, attempt_id, owner_id, fence_token = binding
        try:
            store.append_event(attempt_id, "w1_activity", entry, owner_id=owner_id, fence_token=fence_token)
        except LeaseLostError:
            # Preserve managed mode. The next provider intent will fence before I/O.
            mark_cancel_requested(session_id)
        except Exception:
            # A transient event-mirror failure must not downgrade provider calls.
            pass
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
