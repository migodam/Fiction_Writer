"""
Tests for sidecar/supervisor/organizer.py — W1 Content Organizer.

All tests are synchronous, zero-mock, zero-LLM.
Each test builds a minimal OrganizerInput inline and asserts on OrganizerOutput.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sidecar.supervisor.organizer import organize_project_content, OrganizerInput
import sidecar.workflows.w1_import as w1_import


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**overrides) -> OrganizerInput:
    base: OrganizerInput = {
        "characters": {},
        "events": [],
        "relationships": [],
        "world_candidates": {},
        "manuscript_notes": [],
        "timeline_architecture": {},
        "project_digest": {},
        "source_language": "zh",
    }
    base.update(overrides)
    return base


def _world_candidate(category: str = "concept", description: str = "", confidence: float = 0.8) -> dict:
    return {"category": category, "description": description, "confidence": confidence, "attributes": []}


# ---------------------------------------------------------------------------
# Test 1 — sect name routes to organization, not excluded
# ---------------------------------------------------------------------------


def test_sect_name_routes_to_organization():
    inp = _make_input(world_candidates={
        "七玄门": _world_candidate(category="organization"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 1, "七玄门 should survive as a world item"
    item = out["world_items"][0]
    assert item["name"] == "七玄门"
    assert item["category"] == "organization"
    assert item["container_key"] == "organizations"

    excluded_names = [e["name"] for e in out["excluded_items"]]
    assert "七玄门" not in excluded_names, "七玄门 must not be excluded"


# ---------------------------------------------------------------------------
# Test 2 — cultivation method routes correctly
# ---------------------------------------------------------------------------


def test_cultivation_method_routes_correctly():
    inp = _make_input(world_candidates={
        "长春功": _world_candidate(category="cultivation_method"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 1
    item = out["world_items"][0]
    assert item["name"] == "长春功"
    assert item["category"] == "cultivation_method"
    assert item["container_key"] == "cultivation_methods"


# ---------------------------------------------------------------------------
# Test 3 — identity rank excluded (记名弟子 is not a cultivation method)
# ---------------------------------------------------------------------------


def test_identity_rank_excluded_from_cultivation_method():
    inp = _make_input(world_candidates={
        "记名弟子": _world_candidate(category="cultivation_method"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 0, "记名弟子 must not appear as a world item"
    assert len(out["excluded_items"]) == 1
    excl = out["excluded_items"][0]
    assert excl["name"] == "记名弟子"
    assert excl["reason"] == "identity_rank"


def test_inner_sect_disciple_excluded():
    inp = _make_input(world_candidates={
        "内门弟子": _world_candidate(category="cultivation_method"),
        "外门弟子": _world_candidate(category="rule"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 0
    reasons = {e["name"]: e["reason"] for e in out["excluded_items"]}
    assert reasons["内门弟子"] == "identity_rank"
    assert reasons["外门弟子"] == "identity_rank"


# ---------------------------------------------------------------------------
# Test 4 — person name excluded from world items
# ---------------------------------------------------------------------------


def test_person_name_excluded_from_world():
    inp = _make_input(
        characters={"char_001": {"name": "韩立", "role": "protagonist"}},
        world_candidates={"韩立": _world_candidate(category="concept")},
    )
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 0, "韩立 is a character name and must not be a world item"
    assert len(out["excluded_items"]) == 1
    excl = out["excluded_items"][0]
    assert excl["name"] == "韩立"
    assert excl["reason"] == "person_name"
    assert excl["suggested_module"] == "character"


# ---------------------------------------------------------------------------
# Test 5 — relationship graph string excluded
# ---------------------------------------------------------------------------


def test_relationship_graph_excluded():
    inp = _make_input(world_candidates={
        "人物关系图": _world_candidate(category="concept"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 0
    assert len(out["excluded_items"]) == 1
    excl = out["excluded_items"][0]
    assert excl["name"] == "人物关系图"
    assert excl["reason"] == "module_contamination"
    assert excl["suggested_module"] == "relationship"


def test_timeline_string_excluded():
    inp = _make_input(world_candidates={
        "事件时间线": _world_candidate(category="concept"),
    })
    out = organize_project_content(inp)

    assert len(out["excluded_items"]) == 1
    assert out["excluded_items"][0]["reason"] == "module_contamination"
    assert out["excluded_items"][0]["suggested_module"] == "timeline"


# ---------------------------------------------------------------------------
# Test 6 — empty containers removed when all candidates excluded
# ---------------------------------------------------------------------------


def test_empty_containers_removed():
    inp = _make_input(world_candidates={
        "人物关系图": _world_candidate(category="concept"),
        "韩立": _world_candidate(category="concept"),
    }, characters={"c1": {"name": "韩立"}})
    out = organize_project_content(inp)

    assert out["world_items"] == []
    assert out["world_containers"] == [], "No surviving items means no containers"
    assert out["proposal_packages"] == [], "No surviving items means no packages"


# ---------------------------------------------------------------------------
# Test 7 — categoryPath and parentId present on world item proposals
# ---------------------------------------------------------------------------


def test_category_path_and_parent_id_present():
    inp = _make_input(world_candidates={
        "七玄门": _world_candidate(category="organization"),
        "神手谷": _world_candidate(category="location"),
        "长春功": _world_candidate(category="cultivation_method"),
    })
    out = organize_project_content(inp)

    assert len(out["world_items"]) == 3
    for item in out["world_items"]:
        assert "categoryPath" in item, f"categoryPath missing on {item['name']}"
        assert len(item["categoryPath"]) >= 2, (
            f"categoryPath must have at least 2 segments for {item['name']}, "
            f"got {item['categoryPath']}"
        )
        assert item["name"] in item["categoryPath"], (
            f"Item name must be last segment of categoryPath for {item['name']}"
        )
        assert "parentId" in item, f"parentId key missing on {item['name']}"


# ---------------------------------------------------------------------------
# Test 8 — all excluded items have non-empty reason
# ---------------------------------------------------------------------------


def test_all_excluded_items_have_non_empty_reason():
    inp = _make_input(
        characters={"c1": {"name": "韩立"}},
        world_candidates={
            "人物关系图": _world_candidate(category="concept"),
            "韩立": _world_candidate(category="concept"),
            "记名弟子": _world_candidate(category="cultivation_method"),
            "护法": _world_candidate(category="cultivation_method"),
        },
    )
    out = organize_project_content(inp)

    assert len(out["excluded_items"]) >= 3, "Expected at least 3 exclusions"
    for excl in out["excluded_items"]:
        assert excl["reason"], f"reason must be non-empty for excluded item '{excl['name']}'"
        assert excl["suggested_module"], (
            f"suggested_module must be non-empty for excluded item '{excl['name']}'"
        )


# ---------------------------------------------------------------------------
# Test 9 — proposal packages group items by container key
# ---------------------------------------------------------------------------


def test_proposal_packages_group_by_container():
    inp = _make_input(world_candidates={
        "七玄门": _world_candidate(category="organization"),
        "青牛门": _world_candidate(category="organization"),
        "神手谷": _world_candidate(category="location"),
    })
    out = organize_project_content(inp)

    assert len(out["proposal_packages"]) == 2  # organizations + locations
    pkg_keys = {p["container_key"] for p in out["proposal_packages"]}
    assert "organizations" in pkg_keys
    assert "locations" in pkg_keys

    org_pkg = next(p for p in out["proposal_packages"] if p["container_key"] == "organizations")
    assert len(org_pkg["items"]) == 2
    assert org_pkg["label"] == "门派组织"


# ---------------------------------------------------------------------------
# Test 10 — role rank title misrouted to cultivation_method is excluded
# ---------------------------------------------------------------------------


def test_role_rank_misrouted_to_cultivation_method_excluded():
    inp = _make_input(world_candidates={
        "护法": _world_candidate(category="cultivation_method"),
        "堂主": _world_candidate(category="cultivation_method"),
    })
    out = organize_project_content(inp)

    excluded_names = {e["name"] for e in out["excluded_items"]}
    assert "护法" in excluded_names
    assert "堂主" in excluded_names
    for excl in out["excluded_items"]:
        assert excl["reason"] == "role_rank"


# ---------------------------------------------------------------------------
# Test 11 — 长春功 gets correct cultivation_method categoryPath
# ---------------------------------------------------------------------------


def test_cultivation_method_category_path_content():
    inp = _make_input(world_candidates={
        "长春功": _world_candidate(category="cultivation_method"),
    })
    out = organize_project_content(inp)
    item = out["world_items"][0]
    assert item["categoryPath"] == ["世界模型", "功法与术法", "长春功"], (
        f"Expected cultivation_method path, got {item['categoryPath']}"
    )


# ---------------------------------------------------------------------------
# Test 12 — 七玄门 gets correct organization categoryPath
# ---------------------------------------------------------------------------


def test_organization_category_path_content():
    inp = _make_input(world_candidates={
        "七玄门": _world_candidate(category="organization"),
    })
    out = organize_project_content(inp)
    item = out["world_items"][0]
    assert item["categoryPath"] == ["世界模型", "门派组织", "七玄门"], (
        f"Expected organization path, got {item['categoryPath']}"
    )


# ---------------------------------------------------------------------------
# Test 13 — 神手谷 gets correct location categoryPath
# ---------------------------------------------------------------------------


def test_location_category_path_content():
    inp = _make_input(world_candidates={
        "神手谷": _world_candidate(category="location"),
    })
    out = organize_project_content(inp)
    item = out["world_items"][0]
    assert item["categoryPath"] == ["世界模型", "地理位置", "神手谷"], (
        f"Expected location path, got {item['categoryPath']}"
    )


# ---------------------------------------------------------------------------
# Test 14 — node_organize_project filters exclusions and enriches survivors
# ---------------------------------------------------------------------------


def test_node_organize_project_filters_and_enriches():
    state = {
        "source_language": "zh",
        "relationships": [],
        "timeline_architecture": {},
        "entity_registry": {
            "characters": {},
            "events": {},
            "world": {
                "事件时间线": "concept",
                "神手谷": "location",
            },
            "world_detailed": {
                "事件时间线": {"category": "concept", "description": "Meta timeline entry"},
                "神手谷": {"category": "location", "description": "A mountain valley"},
            },
        },
    }
    result = asyncio.run(w1_import.node_organize_project(state))
    registry = result["entity_registry"]

    # Both structures must exclude the contamination item
    assert "事件时间线" not in registry["world_detailed"], \
        "Contamination item must be absent from world_detailed"
    assert "事件时间线" not in registry["world"], \
        "Contamination item must be absent from world"

    # Valid world item must survive in both structures
    assert "神手谷" in registry["world_detailed"], "Valid item must survive in world_detailed"
    assert "神手谷" in registry["world"], "Valid item must survive in world"

    # Organizer categoryPath must be stored in world_detailed
    item = registry["world_detailed"]["神手谷"]
    assert "categoryPath" in item, "Organizer must enrich surviving items with categoryPath"
    assert item["categoryPath"] == ["世界模型", "地理位置", "神手谷"], \
        f"Expected organizer path with name appended, got {item['categoryPath']}"


# ---------------------------------------------------------------------------
# Test 15 — Full acceptance matrix: exclusions + correct routings + ambiguous 堂 suffix
# ---------------------------------------------------------------------------


def test_organizer_full_acceptance_matrix():
    """Verifies the complete routing acceptance matrix from the W2 task spec."""
    inp = _make_input(
        characters={"char_1": {"name": "韩立"}, "char_2": {"name": "王护法"}},
        world_candidates={
            # Must be excluded (identity/role ranks)
            "记名弟子": _world_candidate(category="cultivation_method"),
            "内门弟子": _world_candidate(category="cultivation_method"),
            "外门弟子": _world_candidate(category="rule"),
            # Must be excluded (person names)
            "韩立": _world_candidate(category="concept"),
            "王护法": _world_candidate(category="concept"),
            # Must survive with correct routing
            "长春功": _world_candidate(category="cultivation_method"),
            "七玄门": _world_candidate(category="organization"),
            "神手谷": _world_candidate(category="location"),
            # Ambiguous 堂 suffix: must survive as location or organization (not excluded)
            "七玄堂": _world_candidate(category="location"),
            "供奉堂": _world_candidate(category="organization"),
        },
    )
    out = organize_project_content(inp)

    excluded_names = {e["name"] for e in out["excluded_items"]}
    assert "记名弟子" in excluded_names, "记名弟子 must be excluded"
    assert "内门弟子" in excluded_names, "内门弟子 must be excluded"
    assert "外门弟子" in excluded_names, "外门弟子 must be excluded"
    assert "韩立" in excluded_names, "Person name 韩立 must be excluded"
    assert "王护法" in excluded_names, "Person name 王护法 must be excluded"

    surviving = {item["name"]: item for item in out["world_items"]}
    assert "长春功" in surviving, "长春功 must survive"
    assert surviving["长春功"]["container_key"] == "cultivation_methods", \
        f"长春功 must route to cultivation_methods, got {surviving['长春功']['container_key']}"
    assert "七玄门" in surviving, "七玄门 must survive"
    assert surviving["七玄门"]["container_key"] == "organizations", \
        f"七玄门 must route to organizations, got {surviving['七玄门']['container_key']}"
    assert "神手谷" in surviving, "神手谷 must survive"
    assert surviving["神手谷"]["container_key"] == "locations", \
        f"神手谷 must route to locations, got {surviving['神手谷']['container_key']}"

    # Ambiguous 堂 suffix: must survive (not be excluded) as location or organization
    assert "七玄堂" in surviving, "七玄堂 must survive as location/organization — not excluded"
    assert surviving["七玄堂"]["container_key"] in ("locations", "organizations"), \
        f"七玄堂 container_key must be locations or organizations, got {surviving['七玄堂']['container_key']}"
    assert "供奉堂" in surviving, "供奉堂 must survive as location/organization — not excluded"
    assert surviving["供奉堂"]["container_key"] in ("locations", "organizations"), \
        f"供奉堂 container_key must be locations or organizations, got {surviving['供奉堂']['container_key']}"
