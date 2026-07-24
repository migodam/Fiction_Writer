"""Supervisor staging regression for deterministic World-to-Character relocation."""
from __future__ import annotations

import asyncio

from sidecar.supervisor.policy import _organize_staged_world_candidates


def test_supervisor_organizer_relocates_before_rebuilding_world_survivors() -> None:
    state = {
        "source_language": "zh",
        "relationships": [],
        "timeline_architecture": {},
        "project_structure_digest": {},
        "entity_registry": {
            "characters": {
                "char_wang": {
                    "name": "王六",
                    "aliases": ["王6"],
                    "evidence_refs": ["existing_evidence"],
                },
            },
            "events": {},
            "world": {
                "正门主王六": "organization",
                "正门": "organization",
                "七玄门": "organization",
            },
            # The live registry permits stable IDs as keys; the helper must
            # classify the display name in each entry, not these storage keys.
            "world_detailed": {
                "world_wang": {
                    "entity_id": "world_wang",
                    "name": "正门主王六",
                    "category": "organization",
                    "confidence": 0.95,
                    "evidence_refs": ["title_evidence"],
                },
                "world_gate": {
                    "entity_id": "world_gate",
                    "name": "正门",
                    "category": "organization",
                    "confidence": 0.95,
                },
                "world_sect": {
                    "entity_id": "world_sect",
                    "name": "七玄门",
                    "category": "organization",
                    "confidence": 0.95,
                    "description": "修仙门派组织。",
                },
            },
        },
    }

    result = asyncio.run(_organize_staged_world_candidates(state))
    registry = result["entity_registry"]
    wang = registry["characters"]["char_wang"]

    assert "正门主王六" not in registry["world"]
    assert "正门主王六" not in registry["world_detailed"]
    assert wang["aliases"] == ["王6", "正门主王六"]
    assert wang["role"] == "正门主"
    assert wang["evidence_refs"] == ["existing_evidence", "title_evidence"]

    assert "正门" not in registry["world"]
    assert "正门" not in registry["world_detailed"]
    assert "七玄门" in registry["world_detailed"]
    assert registry["world_detailed"]["七玄门"]["containerId"] == "world_container_organizations"
    assert any(item["raw_name"] == "正门" for item in result["quarantine_candidates"])
    assert result["candidate_ledger"]
    assert result["relocation_plans"][0]["source_candidate_id"] == "world_wang"
    assert result["applied_relocation_plan_ids"] == ["relocate_world_wang_to_char_wang"]
