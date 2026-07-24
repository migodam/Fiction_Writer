"""Direct W1 graph regression coverage for staged semantic relocation."""
from __future__ import annotations

import asyncio

from sidecar.workflows.w1_import import build_graph, node_organize_project


def test_direct_organizer_relocates_title_person_before_world_filtering() -> None:
    """A mixed title/person World candidate enriches its character, never World."""
    state = {
        "source_language": "zh",
        "relationships": [],
        "timeline_architecture": {},
        "entity_registry": {
            "characters": {
                "char_wang": {
                    "name": "王六",
                    "aliases": ["王6"],
                    "evidence_refs": ["evidence_existing"],
                },
            },
            "events": {},
            "world": {
                "正门主王六": "organization",
                "正门": "organization",
                "七玄门": "organization",
            },
            "world_detailed": {
                "world_wang": {
                    "entity_id": "world_wang",
                    "name": "正门主王六",
                    "category": "organization",
                    "confidence": 0.95,
                    "evidence_refs": ["evidence_wang"],
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

    result = asyncio.run(node_organize_project(state))
    registry = result["entity_registry"]
    wang = registry["characters"]["char_wang"]

    assert "world_wang" not in registry["world_detailed"]
    assert "正门主王六" not in registry["world"]
    assert wang["aliases"] == ["王6", "正门主王六"]
    assert wang["role"] == "正门主"
    assert wang["evidence_refs"] == ["evidence_existing", "evidence_wang"]
    assert result["applied_relocation_plan_ids"] == ["relocate_world_wang_to_char_wang"]

    # An ambiguous gate is held for reviewer/human routing instead of leaking
    # into the organizations folder, while well-supported 七玄门 still survives.
    assert "world_gate" not in registry["world_detailed"]
    assert "正门" not in registry["world"]
    assert "world_sect" in registry["world_detailed"]
    assert registry["world_detailed"]["world_sect"]["name"] == "七玄门"
    assert registry["world_detailed"]["world_sect"]["containerId"] == "world_container_organizations"
    assert any(item["raw_name"] == "正门" for item in result["quarantine_candidates"])
    assert result["candidate_ledger"]
    assert result["relocation_plans"][0]["source_candidate_id"] == "world_wang"

    # The direct LangGraph schema retains this review state for the later
    # reviewer/proposal nodes instead of silently dropping unknown updates.
    graph = build_graph(None)
    assert {
        "organizer_output",
        "candidate_ledger",
        "quarantine_candidates",
        "relocation_plans",
        "applied_relocation_plan_ids",
    }.issubset(graph.channels)
