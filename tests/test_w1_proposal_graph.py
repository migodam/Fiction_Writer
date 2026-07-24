import json

from sidecar.shared.proposal_graph import compile_import_run_package, compile_proposal_graph


def proposal(proposal_id, entity_type, entity_id, fields=None, **extra):
    return {
        "id": proposal_id,
        "operations": [{"op": "create", "entityType": entity_type, "entityId": entity_id, "fields": fields or {}}],
        **extra,
    }


def test_character_missing_event_backlink_is_dropped_not_blocking():
    result = compile_proposal_graph([
        proposal("char", "character", "hero", {"linkedEventIds": ["event_missing"]}),
    ])

    assert result["atomic"] is True
    assert result["normalizedProposals"][0]["operations"][0]["fields"]["linkedEventIds"] == []
    assert result["droppedRefs"] == [{
        "proposalId": "char", "entityType": "character", "field": "linkedEventIds",
        "targetType": "timeline_event", "targetId": "event_missing",
    }]


def test_empty_optional_scalar_is_not_reported_as_a_dangling_edge():
    result = compile_proposal_graph([
        proposal("branch", "timeline_branch", "main", {
            "parentBranchId": None,
            "forkEventId": None,
            "mergeEventId": "",
        }),
    ])

    assert result["atomic"] is True
    assert result["droppedRefs"] == []


def test_merged_event_ids_build_loser_remaps_and_rewrite_other_references():
    result = compile_proposal_graph([
        proposal("branch", "timeline_branch", "main"),
        proposal("new", "timeline_event", "event_new", {"branchId": "main", "mergedEventIds": ["event_old"]}),
        proposal("char", "character", "hero", {"linkedEventIds": ["event_old"]}),
    ])

    event_fields = next(item for item in result["normalizedProposals"] if item["id"] == "new")["operations"][0]["fields"]
    character_fields = next(item for item in result["normalizedProposals"] if item["id"] == "char")["operations"][0]["fields"]
    assert result["atomic"] is True
    assert event_fields["mergedEventIds"] == ["event_old"]
    assert character_fields["linkedEventIds"] == ["event_new"]
    assert result["remaps"] == {"timeline_event": {"event_old": "event_new"}}


def test_required_branch_reference_blocks_the_batch():
    result = compile_proposal_graph([proposal("event", "timeline_event", "event_1", {"branchId": "missing"})])

    assert result["atomic"] is False
    assert any(error["code"] == "missing_required_reference" for error in result["blockingErrors"])


def test_duplicate_typed_create_producer_blocks_the_batch():
    result = compile_proposal_graph([
        proposal("first", "character", "hero"),
        proposal("second", "character", "hero"),
    ])

    assert result["atomic"] is False
    assert result["blockingErrors"][0]["code"] == "duplicate_producer"


def test_order_is_deterministic_when_input_is_shuffled():
    proposals = [
        proposal("event", "timeline_event", "event_1", {"branchId": "main"}),
        proposal("branch", "timeline_branch", "main"),
        proposal("char", "character", "hero", {"linkedEventIds": ["event_1"]}),
    ]

    first = compile_proposal_graph(proposals)
    second = compile_proposal_graph(list(reversed(proposals)))
    assert first["orderedProposalIds"] == second["orderedProposalIds"] == ["branch", "event", "char"]
    assert first["edges"] == second["edges"]


def test_fields_id_is_used_as_the_producer_identity():
    result = compile_proposal_graph([
        proposal("container", "world_container", None, {"id": "container_1"}),
        proposal("item", "world_item", None, {"id": "item_1", "containerId": "container_1"}),
    ])

    assert result["atomic"] is True
    assert result["producers"]["world_container"]["container_1"] == "container"
    assert result["orderedProposalIds"] == ["container", "item"]


def test_mismatched_explicit_producer_ids_block_the_batch():
    result = compile_proposal_graph([
        {
            "id": "container",
            "targetEntityId": "target_container",
            "operations": [{
                "op": "create",
                "entityType": "world_container",
                "entityId": "operation_container",
                "fields": {"id": "field_container"},
            }],
        },
    ])

    assert result["atomic"] is False
    mismatch = next(error for error in result["blockingErrors"] if error["code"] == "producer_id_mismatch")
    assert mismatch["ids"] == ["operation_container", "field_container", "target_container"]


def test_compiler_metadata_and_execution_plan_are_deterministic():
    proposals = [
        proposal("event", "timeline_event", "event_1", {"branchId": "main"}),
        proposal("branch", "timeline_branch", "main"),
    ]

    first = compile_proposal_graph(proposals)
    second = compile_proposal_graph(list(reversed(proposals)))

    assert first["contractVersion"] == "w1-package-graph-v2"
    assert first["executionPlan"] == [{"phase": "apply", "proposalIds": ["branch", "event"]}]
    assert first["executionPlan"] == second["executionPlan"]
    for proposal_record in first["normalizedProposals"]:
        metadata = proposal_record["packageCompiler"]
        assert metadata == {
            "contractVersion": "w1-package-graph-v2",
            "order": {"branch": 0, "event": 1}[proposal_record["id"]],
            "proposalCount": 2,
            "orderedProposalIds": ["branch", "event"],
        }


def test_optional_cycle_is_legal_and_has_stable_order():
    result = compile_proposal_graph([
        proposal("a", "character", "a", {"linkedEventIds": ["event_b"]}),
        proposal("b", "timeline_event", "event_b", {"branchId": "main", "participantCharacterIds": ["a"]}),
        proposal("branch", "timeline_branch", "main"),
    ])

    assert result["atomic"] is True
    assert result["orderedProposalIds"] == ["branch", "a", "b"]


def test_existing_ids_resolve_required_refs_and_entity_depends_on():
    result = compile_proposal_graph([
        proposal("event", "timeline_event", "event_1", {"branchId": "canonical_branch"}, dependsOn=["canonical_branch"]),
    ], existing_ids={"timeline_branch": {"canonical_branch"}})

    assert result["atomic"] is True
    assert result["edges"] == []
    assert any(item["code"] == "canonical_depends_on_ignored" for item in result["diagnostics"])


def test_production_schema_references_cover_nested_branch_scene_world_and_chapter():
    result = compile_proposal_graph([
        proposal("tag", "character_tag", "tag_1"),
        proposal("char", "character", "hero", {"tagIds": ["tag_1"]}),
        proposal("chapter", "chapter", "chapter_1", {"sceneIds": ["scene_1"]}),
        proposal("scene", "scene", "scene_1", {"chapterId": "chapter_1", "povCharacterId": "hero", "linkedCharacterIds": ["hero"]}),
        proposal("container", "world_container", "container_1"),
        proposal("world", "world_item", "world_1", {"containerId": "container_1", "parentId": "container_1"}),
        proposal("branch", "timeline_branch", "main", {"mergeTargetBranchId": "merge", "startAnchor": {"eventId": "event_1"}, "endAnchor": {"eventId": "event_1"}}),
        proposal("merge", "timeline_branch", "merge"),
        proposal("event", "timeline_event", "event_1", {"branchId": "main", "sharedBranchIds": ["merge"]}),
        proposal("relationship", "relationship", "rel_1", {"sourceId": "hero", "targetId": "hero"}),
    ])

    assert result["atomic"] is True
    assert not result["droppedRefs"]


def test_import_run_package_rewrites_only_the_package_clears_stale_blocks_and_writes_artifact(tmp_path):
    inbox_path = tmp_path / "system" / "inbox.json"
    inbox_path.parent.mkdir(parents=True)
    unrelated = proposal("outside", "character", "outside", {"linkedEventIds": ["not_touched"]}, source_workflow="other")
    package_branch = proposal("branch", "timeline_branch", "main", {"importRunId": "run_1"}, source_workflow="W1_import", lastBlockReason="old", lastBlockedAt="yesterday", blockedReason="old")
    package_event = proposal("event", "timeline_event", "event_1", {"branchId": "main", "importRunId": "run_1"}, source_workflow="W1_import", dependsOn=["main"])
    inbox_path.write_text(json.dumps([unrelated, package_branch, package_event]), encoding="utf-8")

    result = compile_import_run_package(tmp_path, "run_1")
    written = json.loads(inbox_path.read_text(encoding="utf-8"))
    artifact = json.loads((tmp_path / "system" / "imports" / "run_1" / "proposal_graph.json").read_text(encoding="utf-8"))

    assert result["atomic"] is True and result["inboxUpdated"] is True
    assert written[0] == unrelated
    assert all(key not in written[1] for key in ("lastBlockReason", "lastBlockedAt", "blockedReason"))
    assert artifact["atomic"] is True
    assert artifact["orderedProposalIds"] == ["branch", "event"]


def test_import_run_package_can_fail_closed_before_workbench_review(tmp_path):
    inbox_path = tmp_path / "system" / "inbox.json"
    inbox_path.parent.mkdir(parents=True)
    unrelated = proposal("outside", "character", "outside", source_workflow="other")
    broken = proposal(
        "broken", "timeline_event", "event_broken",
        {"branchId": "missing", "importRunId": "run_broken"},
        source_workflow="W1_import",
    )
    inbox_path.write_text(json.dumps([unrelated, broken]), encoding="utf-8")

    result = compile_import_run_package(
        tmp_path, "run_broken", remove_invalid_package=True,
    )

    assert result["atomic"] is False
    assert result["packageRemoved"] is True
    assert json.loads(inbox_path.read_text(encoding="utf-8")) == [unrelated]


def test_fail_closed_cleanup_does_not_remove_non_w1_proposal_reusing_run_id(tmp_path):
    inbox_path = tmp_path / "system" / "inbox.json"
    inbox_path.parent.mkdir(parents=True)
    unrelated = proposal(
        "outside", "character", "outside", {"importRunId": "run_shared"},
        source_workflow="W2_manuscript_sync",
    )
    broken = proposal(
        "broken", "timeline_event", "event_broken",
        {"branchId": "missing", "importRunId": "run_shared"},
        source_workflow="W1_import",
    )
    inbox_path.write_text(json.dumps([unrelated, broken]), encoding="utf-8")

    result = compile_import_run_package(
        tmp_path, "run_shared", remove_invalid_package=True,
    )

    assert result["packageRemoved"] is True
    assert json.loads(inbox_path.read_text(encoding="utf-8")) == [unrelated]
