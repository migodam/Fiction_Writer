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
    assert metrics["import_test6_symptom_flags"]["scene_beats_or_discards_present"] is True


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
