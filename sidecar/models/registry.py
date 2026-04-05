from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class CharacterEntry(TypedDict):
    character_id: str
    name: str
    aliases: List[str]
    role: Optional[str]
    status: str


class EventEntry(TypedDict):
    event_id: str
    title: str
    chapter_ids: List[str]
    participants: List[str]
    summary: str


class WorldEntryRef(TypedDict):
    entity_id: str
    entity_type: str
    label: str
    notes: Optional[str]


class EntityRegistry(TypedDict):
    characters: Dict[str, CharacterEntry]
    events: Dict[str, EventEntry]
    world: Dict[str, WorldEntryRef]


class ImportCharacterEntry(TypedDict):
    canonical_id: str
    canonical_name: str
    aliases: List[str]
    first_seen_chunk: int
    notes: List[str]
    confidence: float


class ImportEntityRegistry(TypedDict):
    characters: Dict[str, ImportCharacterEntry]
    events: Dict[str, dict]
    world: Dict[str, str]
