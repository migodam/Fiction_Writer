from __future__ import annotations

import json
from pathlib import Path

from tools import w1_import_diagnostics


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_project(tmp_path: Path, *, import_run_id: str = "import_a", event_count: int = 2) -> Path:
    project = tmp_path / import_run_id
    run_dir = project / "system" / "imports" / import_run_id
    _write_json(
        project / "system" / "inbox.json",
        [
            {
                "id": "prop_char",
                "operations": [
                    {
                        "op": "create",
                        "entityType": "character",
                        "entityId": "char_hero",
                        "fields": {
                            "id": "char_hero",
                            "name": "Hero",
                            "summary": "\n".join(f"Repeated summary line {idx}" for idx in range(10)),
                            "traits": [
                                "brave",
                                "Brave",
                                "勇敢",
                                "cautious 谨慎",
                                "very long trait phrase that should be treated as noisy",
                            ],
                            "tagIds": ["tag_main"],
                        },
                    }
                ],
            },
            {
                "id": "prop_event",
                "operations": [
                    {
                        "op": "create",
                        "entityType": "timeline_event",
                        "entityId": "event_pending",
                        "fields": {
                            "id": "event_pending",
                            "title": "Hero leaves home",
                            "branchId": "branch_main",
                            "orderIndex": 99,
                        },
                    }
                ],
            },
        ],
    )
    _write_json(
        project / "entities" / "character-tags.json",
        [{"id": "tag_main", "name": "Main Cast", "characterIds": ["char_existing"]}],
    )
    _write_json(
        project / "entities" / "timeline" / "branches.json",
        [{"id": "branch_main", "name": "Main"}, {"id": "branch_side", "name": "Side"}],
    )
    _write_json(
        run_dir / "manifest.json",
        {
            "import_run_id": import_run_id,
            "prompt_profile": "fast",
            "model": "test-model",
            "segment_count": 1,
            "segments": [{"char_count": 123}],
        },
    )
    canonical_events = [
        {
            "event_id": f"event_{idx}",
            "title": "Hero leaves home" if idx < 2 else f"Event {idx}",
            "branchId": "branch_main" if idx < event_count - 1 else "branch_side",
            "orderIndex": idx,
        }
        for idx in range(event_count)
    ]
    _write_json(
        run_dir / "timeline_architecture.json",
        {
            "import_run_id": import_run_id,
            "root_branch_id": "branch_main",
            "branches": [{"id": "branch_main"}, {"id": "branch_side"}],
            "canonical_events": canonical_events,
            "discarded_duplicates": [
                {"event_id": "event_scene", "title": "Scene beat", "timelineClass": "scene_beat"}
            ],
        },
    )
    _write_json(
        run_dir / "review_report.json",
        {
            "import_run_id": import_run_id,
            "status": "warning",
            "warnings": ["synthetic warning"],
            "errors": [],
            "proposal_counts": {"character": 1, "timeline_event": event_count, "scene": 1},
            "failed_chunks": [],
            "blocked_ids": [],
            "low_confidence_items": [],
        },
    )
    return project


def test_analyze_import_reports_quality_symptoms(tmp_path):
    project = _make_project(tmp_path, event_count=30)

    metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(project, "import_a")
    )

    assert metrics["proposal_counts_by_entity_type"] == {"character": 1, "timeline_event": 1}
    assert metrics["character_count"]["pending_character_proposals"] == 1
    assert metrics["group_distribution"]["character_record_tag_refs"]["Main Cast"] == 1
    assert metrics["summary_lengths"]["outlier_count"] == 1
    assert metrics["trait_quality"]["duplicate_traits"] == 1
    assert metrics["trait_quality"]["mixed_language_trait_count"] == 1
    assert metrics["timeline"]["event_duplicate_cluster_count"] == 1
    assert metrics["timeline"]["discard_count"] == 1
    assert metrics["timeline"]["branch_density"]["branches_over_budget"]["branch_main"] == 29
    assert metrics["import_test6_symptom_flags"]["overlong_character_summaries"] is True
    assert metrics["informational_flags"]["scene_beats_or_discards_present"] is True


def test_compare_metrics_supports_two_import_runs(tmp_path):
    primary = _make_project(tmp_path, import_run_id="import_primary", event_count=8)
    comparison = _make_project(tmp_path, import_run_id="import_comparison", event_count=3)

    primary_metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(primary, "import_primary")
    )
    comparison_metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(comparison, "import_comparison")
    )

    deltas = w1_import_diagnostics.compare_metrics(primary_metrics, comparison_metrics)

    assert deltas["canonical_event_count"] == {"primary": 8, "comparison": 3, "delta": 5}


def test_cli_exit_codes_default_and_threshold(tmp_path, capsys):
    project = _make_project(tmp_path, event_count=30)

    default_code = w1_import_diagnostics.main([str(project), "--import-run-id", "import_a", "--format", "markdown"])
    threshold_code = w1_import_diagnostics.main(
        [str(project), "--import-run-id", "import_a", "--fail-on-threshold", "--format", "markdown"]
    )
    malformed_code = w1_import_diagnostics.main([str(project / "missing"), "--format", "json"])

    captured = capsys.readouterr()
    assert default_code == 0
    assert threshold_code == 1
    assert malformed_code == 2
    assert "W1 Import Diagnostics: import_a" in captured.out
    assert "does not exist" in captured.err


def test_attempt_aware_diagnostics_selects_attempt_split_layout_and_blocks_pass_conflict(tmp_path):
    project = tmp_path / "project"
    attempt = project / "system" / "imports" / "lineage_demo" / "attempts" / "attempt_demo"
    _write_json(project / "system" / "inbox.json", [])
    _write_json(project / "project.json", {"metadata": {"locale": "zh-CN"}})
    _write_json(attempt / "manifest.json", {"import_run_id": "lineage_demo", "segments": [{}, {}]})
    _write_json(attempt / "checkpoint.json", {"total_chunks": 2, "committed_chunk_ids": [0, 1]})
    _write_json(attempt / "review_report.json", {"status": "pass"})
    _write_json(attempt / "timeline_architecture.json", {"branches": [], "canonical_events": []})
    _write_json(attempt / "chunks" / "chunk_1_failures.json", {
        "chunk_id": 1,
        "failures": [{"label": "character", "error": "lease is missing, expired, or fenced"}],
    })
    for index in range(2):
        _write_json(project / "writing" / "chapters" / f"chapter_{index}.json", {"id": f"chapter_{index}", "orderIndex": index})
        _write_json(project / "writing" / "scenes" / f"scene_{index}.meta.json", {"id": f"scene_{index}"})
        (project / "writing" / "scenes" / f"scene_{index}.md").write_text("正文", encoding="utf-8")
    _write_json(project / "writing" / "manuscript" / "nodes.json", [])

    metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(project, lineage_id="lineage_demo", attempt_id="attempt_demo")
    )

    assert metrics["artifact_scope"] == {
        "layout": "attempt",
        "lineage_id": "lineage_demo",
        "attempt_id": "attempt_demo",
        "artifact_dir": str(attempt),
    }
    assert metrics["artifact_quality"]["chapters"]["total_chapter_count"] == 2
    assert metrics["artifact_quality"]["canonical_split_layout"]["scene_content_count"] == 2
    durable = metrics["artifact_quality"]["durable_failures"]
    assert durable["failed_chunk_ids"] == [1]
    assert durable["domain_coverage"]["character"]["failed_chunks"] == [1]
    assert metrics["import_test6_symptom_flags"]["durable_failure_artifacts_present"]
    assert metrics["import_test6_symptom_flags"]["review_pass_conflicts_durable_failures"]


def test_cli_accepts_project_path_alias_and_positional_regression_is_covered(tmp_path, capsys):
    project = _make_project(tmp_path, event_count=2)

    code = w1_import_diagnostics.main([
        "--project-path", str(project), "--import-run-id", "import_a", "--format", "json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["diagnostics"]["import_run_id"] == "import_a"


def test_staged_projection_uses_receipts_without_canonical_writes(tmp_path):
    project = tmp_path / "staged"
    run_dir = project / "system" / "imports" / "run_staged"
    _write_json(project / "system" / "inbox.json", [])
    _write_json(project / "project.json", {"metadata": {"locale": "zh-CN"}})
    _write_json(run_dir / "manifest.json", {"source_language": "zh"})
    _write_json(run_dir / "review_report.json", {"proposal_counts": {}, "reviewer_reports": {}})
    _write_json(run_dir / "timeline_architecture.json", {"branches": [], "canonical_events": []})
    _write_json(
        run_dir / "staged_manuscript_projection.json",
        {
            "acceptance_required": True,
            "chapters": [{"id": f"chapter_{index}"} for index in range(10)],
            "nodes": [
                {"id": f"chapter_node_{index}", "type": "chapter_outline"}
                for index in range(10)
            ] + [
                {"id": f"scene_node_{index}", "type": "scene_outline"}
                for index in range(10)
            ],
            "scene_documents": [{"id": f"scene_{index}", "content": "正文"} for index in range(10)],
        },
    )
    _write_json(run_dir / "proposal_write_receipts.json", {"proposal_counts": {"chapter": 10, "scene": 10}})
    _write_json(run_dir / "usage_ledger.json", {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}})

    metrics = w1_import_diagnostics.analyze_import(w1_import_diagnostics.ImportSource(project, "run_staged"))

    projection = metrics["artifact_quality"]["manuscript_projection"]
    flags = metrics["import_test6_symptom_flags"]
    assert projection["source"] == "staged"
    assert (projection["chapter_count"], projection["node_count"], projection["scene_document_count"]) == (10, 20, 10)
    assert not flags["smoke_chapter_count_not_10"]
    assert not flags["smoke_manuscript_node_count_not_20"]
    assert not flags["canonical_manuscript_written_before_acceptance"]
    assert not flags["staged_projection_receipt_mismatch"]


def test_semantic_hard_flags_use_final_proposals_and_reviewer_findings(tmp_path):
    project = _make_project(tmp_path)
    run_dir = project / "system" / "imports" / "import_a"
    _write_json(project / "project.json", {"metadata": {"locale": "zh-CN"}})
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    inbox.extend([
        {"id": "duplicate", "operations": [{"entityType": "character", "fields": {"id": "char_hero_2", "name": "Hero"}}]},
        {"id": "bad-tag", "operations": [{"entityType": "character_tag", "fields": {"name": "Main Cast"}}]},
        {"id": "bad-relation", "operations": [{"entityType": "relationship", "fields": {"id": "rel_1", "type": "解惑", "category": "mentor_disciple"}}]},
    ])
    _write_json(project / "system" / "inbox.json", inbox)
    report = json.loads((run_dir / "review_report.json").read_text(encoding="utf-8"))
    report["reviewer_reports"] = {
        "fact": {"findings": [{"check_name": "evidence_missing"}]},
        "quality": {"findings": [{"check_name": "branch_over_budget"}]},
    }
    _write_json(run_dir / "review_report.json", report)
    _write_json(run_dir / "usage_ledger.json", {"budget_status": {"exhausted": True, "remaining": {"calls": -1}}})

    flags = w1_import_diagnostics.analyze_import(w1_import_diagnostics.ImportSource(project, "import_a"))["import_test6_symptom_flags"]

    assert flags["duplicate_canonical_character_names"]
    assert flags["unresolved_evidence_missing"]
    assert flags["illegal_or_english_tags_present"]
    assert flags["invalid_relationship_types_present"]
    assert flags["branch_density_over_budget"]
    assert flags["usage_ledger_exhausted"]
    assert flags["usage_ledger_over_cap"]


def test_semantic_quality_accepts_current_chinese_relationship_ontology() -> None:
    operations = [
        {
            "entityType": "relationship",
            "entityId": f"rel_{ontology_type}",
            "fields": {"id": f"rel_{ontology_type}", "type": label, "ontologyType": ontology_type},
        }
        for label, ontology_type in [
            ("亲属关系", "family"), ("恋爱关系", "romantic"), ("竞争关系", "rivalry"),
            ("师徒关系", "mentor_disciple"), ("结拜关系", "sworn_brothers"),
            ("政治关系", "political"), ("敌对关系", "conflict"), ("盟友关系", "alliance"),
            ("朋友关系", "friendship"), ("组织隶属", "organization"),
        ]
    ]

    metrics = w1_import_diagnostics._semantic_quality_metrics(operations, {}, "zh", {})

    assert metrics["invalid_relationships"] == []


def test_world_quality_rejects_dangling_container_references(tmp_path):
    project = _make_project(tmp_path)
    run_dir = project / "system" / "imports" / "import_a"
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    inbox.extend([
        {
            "id": "world-container",
            "operations": [{
                "entityType": "world_container",
                "entityId": "cont_import_organizations",
                "fields": {"id": "cont_import_organizations", "importCategoryKey": "organizations"},
            }],
        },
        {
            "id": "world-item",
            "operations": [{
                "entityType": "world_item",
                "entityId": "world_sect",
                "fields": {
                    "id": "world_sect",
                    "name": "七玄门",
                    "containerId": "world_container_organizations",
                    "parentId": "world_container_organizations",
                },
            }],
        },
    ])
    _write_json(project / "system" / "inbox.json", inbox)
    _write_json(run_dir / "usage_ledger.json", {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}})

    metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(project, "import_a")
    )

    world_quality = metrics["artifact_quality"]["world_quality"]
    assert world_quality["dangling_container_reference_count"] == 2
    assert metrics["import_test6_symptom_flags"]["world_container_references_missing"]


def test_pending_proposal_block_markers_are_threshold_failures(tmp_path):
    project = _make_project(tmp_path)
    run_dir = project / "system" / "imports" / "import_a"
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    inbox[0]["status"] = "pending"
    inbox[0]["lastBlockReason"] = "Import package blocked by an obsolete dependency."
    _write_json(project / "system" / "inbox.json", inbox)
    _write_json(run_dir / "usage_ledger.json", {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}})

    metrics = w1_import_diagnostics.analyze_import(
        w1_import_diagnostics.ImportSource(project, "import_a")
    )

    assert metrics["artifact_quality"]["reviewer_repair"]["stale_block_marker_count"] == 1
    assert metrics["import_test6_symptom_flags"]["pending_proposals_have_block_markers"]


def test_semantic_evidence_profile_and_world_organization_gates(tmp_path):
    project = _make_project(tmp_path)
    run_dir = project / "system" / "imports" / "import_a"
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    hero = inbox[0]["operations"][0]["fields"]
    hero.update({
        "role": "protagonist",
        "notes": ["Source note establishes the hero's childhood."],
        "background": "",
        "experience": [],
    })
    inbox.append({"id": "world-misplacements", "operations": [
        {"entityType": "world_item", "fields": {"id": "world_person", "name": "Hero", "category": "organization"}},
        {"entityType": "world_item", "fields": {"id": "world_event", "name": "Entry test", "category": "organization"}},
    ]})
    _write_json(project / "system" / "inbox.json", inbox)
    _write_json(run_dir / "timeline_architecture.json", {
        "canonical_events": [{"title": "Entry test", "branchId": "branch_main"}],
        "discarded_duplicates": [{"timelineClass": "discarded_duplicate"}],
    })
    report = json.loads((run_dir / "review_report.json").read_text(encoding="utf-8"))
    report["reviewer_reports"] = {"fact": {"findings": [
        {"check_name": "evidence_entity_mismatch", "severity": "high"},
        {"check_name": "evidence_unusable", "severity": "medium"},
    ]}}
    _write_json(run_dir / "review_report.json", report)

    metrics = w1_import_diagnostics.analyze_import(w1_import_diagnostics.ImportSource(project, "import_a"))
    flags = metrics["import_test6_symptom_flags"]

    assert flags["high_evidence_entity_mismatch"]
    assert flags["evidence_unusable"]
    assert flags["major_character_supported_profile_gaps"]
    assert flags["person_as_world_organization"]
    assert flags["event_as_world_organization"]
    assert metrics["informational_flags"]["scene_beats_or_discards_present"]


def test_expected_timeline_discards_are_informational_not_threshold_failures(tmp_path):
    project = _make_project(tmp_path, event_count=2)
    run_dir = project / "system" / "imports" / "import_a"
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    inbox[0]["operations"][0]["fields"].update({"summary": "A concise hero card.", "traits": ["brave"]})
    _write_json(project / "system" / "inbox.json", inbox)
    _write_json(run_dir / "timeline_architecture.json", {
        "branches": [{"id": "branch_main"}],
        "canonical_events": [{"title": "Hero leaves home", "branchId": "branch_main", "orderIndex": 0}],
        "discarded_duplicates": [{"timelineClass": "discarded_duplicate"}],
    })
    report = json.loads((run_dir / "review_report.json").read_text(encoding="utf-8"))
    report["proposal_counts"] = {"character": 1, "timeline_event": 1}
    _write_json(run_dir / "review_report.json", report)
    _write_json(run_dir / "staged_manuscript_projection.json", {
        "acceptance_required": True,
        "chapters": [{"id": f"chapter_{index}"} for index in range(10)],
        "nodes": [{"id": f"chapter_{index}", "type": "chapter_outline"} for index in range(10)]
        + [{"id": f"scene_{index}", "type": "scene_outline"} for index in range(10)],
        "scene_documents": [{"id": f"scene_{index}", "content": "正文"} for index in range(10)],
    })
    _write_json(run_dir / "proposal_write_receipts.json", {"proposal_counts": {"chapter": 10, "scene": 10}})
    _write_json(run_dir / "usage_ledger.json", {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}})

    metrics = w1_import_diagnostics.analyze_import(w1_import_diagnostics.ImportSource(project, "import_a"))

    assert metrics["informational_flags"]["scene_beats_or_discards_present"]
    assert not any(metrics["import_test6_symptom_flags"].values())
    assert w1_import_diagnostics.main([str(project), "--import-run-id", "import_a", "--fail-on-threshold", "--format", "json"]) == 0


def test_proposal_reference_closure_is_typed_and_package_scoped(tmp_path):
    project = _make_project(tmp_path)
    _write_json(project / "entities" / "timeline" / "event_existing.json", {"id": "event_existing"})
    inbox = json.loads((project / "system" / "inbox.json").read_text(encoding="utf-8"))
    inbox.extend([
        {"id": "pkg_ok", "operations": [
            {"op": "create", "entityType": "character", "entityId": "char_new", "fields": {"id": "char_new", "eventIds": ["event_new"], "linkedEventIds": ["event_existing"]}},
            {"op": "create", "entityType": "timeline_event", "entityId": "event_new", "fields": {"id": "event_new", "participantCharacterIds": ["char_new"]}},
            {"op": "create", "entityType": "world_container", "entityId": "container_ok", "fields": {"id": "container_ok"}},
            {"op": "create", "entityType": "world_item", "entityId": "world_parent", "fields": {"id": "world_parent", "containerId": "container_ok"}},
            {"op": "create", "entityType": "world_item", "entityId": "world_child", "fields": {"id": "world_child", "containerId": "container_ok", "parentId": "world_parent"}},
        ]},
        {"id": "pkg_bad", "operations": [
            {"op": "update", "entityType": "scene", "entityId": "scene_old", "fields": {"chapterId": "chapter_missing", "linkedEventIds": ["event_missing"]}},
            {"op": "create", "entityType": "world_item", "entityId": "world_new", "fields": {"id": "world_new", "containerId": "container_missing"}},
        ]},
    ])
    _write_json(project / "system" / "inbox.json", inbox)
    metrics = w1_import_diagnostics.analyze_import(w1_import_diagnostics.ImportSource(project, "import_a"))
    closure = metrics["artifact_quality"]["proposal_reference_closure"]
    assert closure["reference_counts_by_target_type"]["event"] >= 2
    assert closure["dangling_reference_count"] == 3
    assert metrics["import_test6_symptom_flags"]["dangling_proposal_references"]
