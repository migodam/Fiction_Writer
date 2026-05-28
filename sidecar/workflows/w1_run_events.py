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


def clear_session(session_id: str) -> None:
    _events.pop(session_id, None)
    _started_at.pop(session_id, None)
    _last_activity_at.pop(session_id, None)
    _active_calls.pop(session_id, None)
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
