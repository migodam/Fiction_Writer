import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.w1_import_diagnostics import ImportSource, analyze_import, main


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_project(tmp_path: Path, *, dirty: bool) -> Path:
    project = tmp_path / ("dirty_import_project" if dirty else "clean_import_project")
    import_dir = project / "system" / "imports" / "import_test"
    manuscript_dir = project / "writing" / "manuscript"
    import_dir.mkdir(parents=True)
    manuscript_dir.mkdir(parents=True)

    chapter_count = 9 if dirty else 10
    chapters = []
    nodes = []
    for index in range(chapter_count):
        chapter_number = 2 if dirty and index in {1, 2} else index + 1
        chapter_id = f"chap_{index + 1}"
        scene_id = f"scene_{index + 1}"
        scene_node_id = f"mn_{scene_id}"
        title = f"第{chapter_number}章"
        content = "" if dirty and index == 0 else f"{title} 韩立在七玄门修炼长春功。"
        chapters.append(
            {
                "id": chapter_id,
                "title": title,
                "chapterNumber": chapter_number,
                "manuscript_content": content,
            }
        )
        nodes.append(
            {
                "id": f"mn_{chapter_id}",
                "title": title,
                "type": "chapter_outline",
                "parentId": None,
                "linkedChapterId": chapter_id,
                "linkedSceneId": None,
                "depth": 0,
                "orderIndex": index,
            }
        )
        nodes.append(
            {
                "id": scene_node_id,
                "title": "章节正文",
                "type": "scene_outline",
                "parentId": f"mn_{chapter_id}",
                "linkedChapterId": chapter_id,
                "linkedSceneId": scene_id,
                "depth": 1,
                "orderIndex": 0,
            }
        )
        (manuscript_dir / f"{scene_node_id}.md").write_text(content, encoding="utf-8")

    _write_json(project / "manuscript.json", {"chapters": chapters})
    _write_json(manuscript_dir / "nodes.json", nodes)

    timeline = {
        "branches": [
            {"id": "branch_main", "name": "主线"},
            {"id": "branch_training", "name": "修炼线"},
            *([{"id": "branch_empty", "name": "空分支"}] if dirty else []),
        ],
        "canonical_events": [
            {"id": f"ev_{index}", "title": f"事件 {index}", "branchId": "branch_main" if index % 2 == 0 else "branch_training"}
            for index in range(6)
        ],
        "discarded_duplicates": [],
    }
    _write_json(import_dir / "timeline_architecture.json", timeline)
    _write_json(import_dir / "manifest.json", {"prompt_profile": "deep", "model": "offline-test", "segments": []})

    world_operation = {
        "op": "create",
        "entity_type": "world_item",
        "entity_id": "wi_koujue" if dirty else "wi_changchungong",
        "data": {
            "name": "人物关系图" if dirty else "长春功",
            "category": "system" if dirty else "cultivation_method",
            "container_key": "systems" if dirty else "cultivation_methods",
            "categoryPath": ["世界模型", "修炼境界与制度", "人物关系图"] if dirty else ["世界模型", "功法与术法", "长春功"],
            "description": "无名口诀被放进制度容器。" if dirty else "一种基础功法。",
        },
    }
    proposals = [
        {
            "id": "proposal_world",
            "operations": [world_operation],
            **({"status": "blocked", "blockedReason": "schema mismatch"} if dirty else {}),
        }
    ]
    if dirty:
        proposals.append(
            {
                "id": "proposal_repair",
                "source": "quality_reviewer",
                "data": {"reviewerRunId": "reviewer_test"},
                "operations": [],
            }
        )
    _write_json(project / "system" / "inbox.json", proposals)
    _write_json(
        import_dir / "review_report.json",
        {
            "status": "warning" if dirty else "pass",
            "blocked_ids": ["proposal_world"] if dirty else [],
            "reviewer_reports": {
                "quality": {"local_repair_actions": [{"action_type": "reclassify"}]}
            } if dirty else {},
        },
    )
    _write_json(
        import_dir / "usage_ledger.json",
        {
            "actual_calls": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cost_usd": 0.01,
            "budget_status": {"exhausted": False, "remaining": {"calls": 9}},
        },
    )
    if dirty:
        _write_json(import_dir / "reviewer_repair_proposals.json", [{"id": "proposal_repair"}])
    return project


def test_artifact_quality_passes_clean_ten_chapter_fixture(tmp_path):
    project = _make_project(tmp_path, dirty=False)

    metrics = analyze_import(ImportSource(project, "import_test"))

    quality = metrics["artifact_quality"]
    assert quality["manuscript_projection"]["chapter_node_count"] == 10
    assert quality["manuscript_projection"]["scene_nodes_with_content"] == 10
    assert quality["chapters"]["duplicate_chapter_number_count"] == 0
    assert quality["timeline_branches"]["empty_branch_count"] == 0
    assert quality["world_quality"]["cultivation_misclassification_count"] == 0
    assert not any(metrics["import_test6_symptom_flags"].values())


def test_artifact_quality_flags_dirty_smoke_fixture(tmp_path):
    project = _make_project(tmp_path, dirty=True)

    metrics = analyze_import(ImportSource(project, "import_test"))
    flags = metrics["import_test6_symptom_flags"]
    quality = metrics["artifact_quality"]

    assert flags["smoke_chapter_count_not_10"]
    assert flags["manuscript_projection_missing_or_empty"]
    assert flags["duplicate_chapter_numbers_present"]
    assert flags["empty_timeline_branches_present"]
    assert flags["world_module_contamination_present"]
    assert flags["world_cultivation_misclassification_present"]
    assert quality["reviewer_repair"]["reviewer_repair_artifacts_present"]
    assert quality["reviewer_repair"]["blocked_proposal_count"] == 1


def test_artifact_quality_threshold_exit_fails_dirty_fixture(tmp_path):
    project = _make_project(tmp_path, dirty=True)

    exit_code = main([str(project), "--import-run-id", "import_test", "--format", "json", "--fail-on-threshold"])

    assert exit_code == 1
