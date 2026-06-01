"""In-memory W1 import activity feed.

This feed is separate from chunk extraction logs. It exists so long-running
supervisor imports can show the user what the AI is doing before a chunk/window
finishes and before proposals are written.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_events: dict[str, list[dict[str, Any]]] = {}
_started_at: dict[str, datetime] = {}
_last_activity_at: dict[str, datetime] = {}
_active_calls: dict[str, int] = {}
_cancel_requested: set[str] = set()
_token_ledger: dict[str, dict[str, int]] = {}

# Per-million-token USD prices for known model name substrings (longest match wins).
# Values are intentional public pricing references, not credentials.
_DEFAULT_PRICE_TABLE: dict[str, dict[str, float]] = {
    "deepseek-chat":    {"input_usd_per_1m": 0.27,  "output_usd_per_1m": 1.10},
    "deepseek-v3":      {"input_usd_per_1m": 0.27,  "output_usd_per_1m": 1.10},
    "deepseek-r1":      {"input_usd_per_1m": 0.55,  "output_usd_per_1m": 2.19},
    "gpt-4o":           {"input_usd_per_1m": 2.50,  "output_usd_per_1m": 10.00},
    "gpt-4.1":          {"input_usd_per_1m": 2.00,  "output_usd_per_1m": 8.00},
    "gpt-4o-mini":      {"input_usd_per_1m": 0.15,  "output_usd_per_1m": 0.60},
    "claude-3-5":       {"input_usd_per_1m": 3.00,  "output_usd_per_1m": 15.00},
    "claude-3-7":       {"input_usd_per_1m": 3.00,  "output_usd_per_1m": 15.00},
}

_SECRET_KEYS = {"api_key", "apikey", "authorization", "token", "password", "secret"}


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


def add_token_usage(session_id: str, input_tokens: int, output_tokens: int) -> None:
    """Accumulate actual LLM usage for this session. Never call with secret values."""
    if not session_id:
        return
    ensure_session(session_id)
    ledger = _token_ledger[session_id]
    ledger["actual_input_tokens"] += max(0, int(input_tokens or 0))
    ledger["actual_output_tokens"] += max(0, int(output_tokens or 0))
    ledger["actual_total_tokens"] = ledger["actual_input_tokens"] + ledger["actual_output_tokens"]
    ledger["api_call_count"] += 1


def _cost_for_model(model: str, input_tokens: int, output_tokens: int) -> tuple[float | None, str | None]:
    """Return (cost_usd, None) if model matches price table, else (None, reason)."""
    model_lower = (model or "").lower()
    for key, prices in sorted(_DEFAULT_PRICE_TABLE.items(), key=lambda kv: len(kv[0]), reverse=True):
        if key in model_lower:
            cost = (
                input_tokens * prices["input_usd_per_1m"] / 1_000_000
                + output_tokens * prices["output_usd_per_1m"] / 1_000_000
            )
            return round(cost, 6), None
    return None, f"No price configured for model: {model or 'unknown'}"


def session_token_ledger(session_id: str, model: str = "", estimated_input_tokens: int = 0) -> dict:
    """Return the current token ledger for UI display. Contains no secrets."""
    if not session_id:
        return {}
    ensure_session(session_id)
    ledger = dict(_token_ledger[session_id])
    ledger["estimated_input_tokens"] = max(0, int(estimated_input_tokens or 0))
    cost_usd, cost_reason = _cost_for_model(
        model,
        ledger.get("actual_input_tokens", 0),
        ledger.get("actual_output_tokens", 0),
    )
    if cost_usd is not None:
        ledger["cost_usd"] = cost_usd
    else:
        ledger["cost_unavailable_reason"] = cost_reason or "cost unavailable"
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
