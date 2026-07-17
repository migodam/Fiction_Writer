from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
import re


class MemoryLayer(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass(frozen=True)
class MemoryItem:
    layer: MemoryLayer
    content: str
    provenance: str
    confidence: float
    expires_at: datetime | None = None


class MemoryPolicy:
    _SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s]+")
    _REDACTABLE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")

    def __init__(self, ttl_by_layer: dict[MemoryLayer, timedelta]) -> None:
        self.ttl_by_layer = ttl_by_layer

    @classmethod
    def default(cls) -> "MemoryPolicy":
        return cls({
            MemoryLayer.WORKING: timedelta(hours=1),
            MemoryLayer.EPISODIC: timedelta(days=30),
            MemoryLayer.SEMANTIC: timedelta(days=365),
            MemoryLayer.PROCEDURAL: timedelta(days=365),
        })

    def prepare(self, item: MemoryItem, now: datetime | None = None) -> MemoryItem:
        if not item.provenance:
            raise ValueError("memory provenance is required")
        if not 0 <= item.confidence <= 1:
            raise ValueError("memory confidence must be between 0 and 1")
        if self._SECRET.search(item.content):
            raise ValueError("memory content contains a secret")
        now = now or datetime.now(tz=item.expires_at.tzinfo if item.expires_at else None)
        redacted = self._REDACTABLE.sub("[REDACTED]", item.content)
        return replace(item, content=redacted, expires_at=item.expires_at or now + self.ttl_by_layer[item.layer])

    @staticmethod
    def is_expired(item: MemoryItem, now: datetime) -> bool:
        return item.expires_at is not None and now >= item.expires_at
