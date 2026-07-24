"""Tests for offline re-review of staged, unaccepted W1 packages."""
from __future__ import annotations

import json
import os
from pathlib import Path

from tools.w1_rereview_pending_package_semantics import (
    _prepare_staging_transaction,
    rereview_pending_package,
)


RUN_ID = "lineage_fixture"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _proposal(proposal_id: str, entity_type: str, entity_id: str, fields: dict, depends_on: list[str] | None = None) -> dict:
    return {
        "id": proposal_id, "source": "import", "source_workflow": "W1_import", "status": "pending",
        "dependsOn": depends_on or [], "operations": [{"op": "create", "entityType": entity_type, "entityId": entity_id, "fields": {**fields, "id": entity_id, "importRunId": RUN_ID}}],
    }


def _fixture(root: Path) -> tuple[Path, Path]:
    containers = [
        _proposal("p_locations", "world_container", "world_container_locations", {"name": "地理位置", "importCategoryKey": "locations"}),
        _proposal("p_org", "world_container", "world_container_organizations", {"name": "门派组织", "importCategoryKey": "organizations"}),
        _proposal("p_rules", "world_container", "world_container_rules", {"name": "修炼境界与制度", "importCategoryKey": "rules"}),
        _proposal("p_concepts", "world_container", "world_container_concepts", {"name": "概念与设定", "importCategoryKey": "concepts"}),
    ]
    character = _proposal("p_wang", "character", "char_wang", {"name": "王六", "aliases": ["王6"], "evidence_refs": []})
    worlds = [
        _proposal("p_hq", "world_item", "world_hq", {"name": "七玄门总堂", "category": "organization", "type": "organization", "containerId": "world_container_organizations", "parentId": "world_container_organizations", "categoryPath": ["世界模型", "门派组织", "七玄门总堂"], "description": "七玄门总部，位于落日峰。"}, ["world_container_organizations"]),
        _proposal("p_watch", "world_item", "world_watch", {"name": "十三个哨卡", "category": "rule", "type": "rule", "containerId": "world_container_rules", "parentId": "world_container_rules", "categoryPath": ["世界模型", "修炼境界与制度", "十三个哨卡"], "description": "唯一通道上的防御体系。"}, ["world_container_rules"]),
        _proposal("p_guard", "world_item", "world_guard", {"name": "护法", "category": "rule", "type": "rule", "containerId": "world_container_rules", "parentId": "world_container_rules", "categoryPath": ["世界模型", "修炼境界与制度", "护法"], "description": "七玄门内的高级身份。"}, ["world_container_rules"]),
        _proposal("p_spouse", "world_item", "world_spouse", {"name": "续弦夫人", "category": "concept", "type": "concept", "containerId": "world_container_concepts", "parentId": "world_container_concepts", "categoryPath": ["世界模型", "概念与设定", "续弦夫人"], "description": "马副门主的续弦夫人。"}, ["world_container_concepts"]),
        _proposal("p_title", "world_item", "world_title", {"name": "正门主王6", "category": "organization", "type": "organization", "containerId": "world_container_organizations", "parentId": "world_container_organizations", "categoryPath": ["世界模型", "门派组织", "正门主王6"], "description": "人物称谓。"}, ["world_container_organizations"]),
    ]
    event = _proposal("p_event", "timeline_event", "event_1", {"title": "护法出场", "branchId": "branch_1", "locationIds": ["world_watch"], "linkedWorldItemIds": ["world_guard", "world_hq"], "linkedSceneIds": [], "participantCharacterIds": [], "sharedBranchIds": []}, ["branch_1"])
    branch = _proposal("p_branch", "timeline_branch", "branch_1", {"name": "主线"})
    inbox_path = root / "system/inbox.json"
    _write(inbox_path, [*containers, character, *worlds, event, branch])
    graph_path = root / "system/imports" / RUN_ID / "proposal_graph.json"
    _write(graph_path, {"importRunId": RUN_ID, "legacy": True})
    return inbox_path, graph_path


def test_dry_run_reports_exact_changes_without_touching_staging_files(tmp_path: Path):
    inbox_path, graph_path = _fixture(tmp_path)
    before_inbox, before_graph = inbox_path.read_bytes(), graph_path.read_bytes()

    report = rereview_pending_package(tmp_path)

    assert report["status"] == "dry_run"
    assert inbox_path.read_bytes() == before_inbox
    assert graph_path.read_bytes() == before_graph
    decisions = {item["entityId"]: item for item in report["decisions"]}
    assert decisions["world_hq"]["after"]["containerId"] == "world_container_locations"
    assert decisions["world_watch"]["after"]["category"] == "location"
    assert decisions["world_guard"]["reason"] == "role_rank"
    assert decisions["world_spouse"]["reason"] == "person_or_relationship_phrase"
    assert decisions["world_title"]["action"] == "review_hold"
    assert report["prunedWorldReferences"] == 0
    assert len(report["candidateDecisions"]) == 5
    assert all("review" in decision for decision in report["candidateDecisions"])
    guard_review = next(item["review"] for item in report["candidateDecisions"] if item["entityId"] == "world_guard")
    assert guard_review["organizerExclusion"]["reason"] == "role_rank"


def test_apply_backs_up_staging_rebuilds_graph_and_never_writes_canonical_entities(tmp_path: Path):
    inbox_path, graph_path = _fixture(tmp_path)

    report = rereview_pending_package(tmp_path, apply=True)

    assert report["status"] == "applied"
    inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in inbox}
    hq = by_id["p_hq"]["operations"][0]["fields"]
    assert hq["containerId"] == "world_container_locations"
    assert hq["folderId"] == "world_container_locations"
    assert by_id["p_hq"]["dependsOn"] == ["world_container_locations"]
    assert by_id["p_guard"]["status"] == "pending"
    assert by_id["p_spouse"]["status"] == "pending"
    assert by_id["p_title"]["status"] == "pending"
    assert "role_rank" in by_id["p_guard"]["lastBlockReason"]
    assert by_id["p_guard"]["data"]["semanticReview"]["organizerExclusion"]["reason"] == "role_rank"
    assert by_id["p_spouse"]["data"]["semanticReview"]["ledger"]["status"] == "quarantined"
    character = by_id["p_wang"]["operations"][0]["fields"]
    assert "正门主王6" in character["aliases"]
    event = by_id["p_event"]["operations"][0]["fields"]
    assert event["locationIds"] == ["world_watch"]
    assert event["linkedWorldItemIds"] == ["world_guard", "world_hq"]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert graph["blockingErrors"] == []
    assert graph["producers"]["world_item"]["world_guard"] == "p_guard"
    receipt = json.loads((tmp_path / report["migrationRoot"] / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["phase"] == "completed"
    assert (tmp_path / report["migrationRoot"] / "backup/system/inbox.json").is_file()
    assert not (tmp_path / "entities").exists()


def test_reviewer_hold_matches_the_frontend_proposal_and_workbench_contract():
    model_source = (REPO_ROOT / "src/ui-react/models/project.ts").read_text(encoding="utf-8")
    workbench_source = (REPO_ROOT / "src/ui-react/components/WorkbenchWorkspace.tsx").read_text(encoding="utf-8")

    assert "export type ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'archived';" in model_source
    assert "lastBlockReason?: string;" in model_source
    assert "proposals.filter((p) => p.status === 'pending' || !p.status)" in workbench_source
    assert "const isBlocked = Boolean(pkg.blockedReason);" in workbench_source


def test_prepared_two_file_transaction_recovers_after_first_target_was_replaced(tmp_path: Path):
    inbox_path, graph_path = _fixture(tmp_path)
    next_inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
    next_inbox[0]["title"] = "recovered inbox"
    next_graph = {"importRunId": RUN_ID, "recovered": True}
    migration_root = tmp_path / "system/migrations/w1-pending-semantic-rereview/interrupted"

    _prepare_staging_transaction(
        tmp_path,
        migration_root,
        import_run_id=RUN_ID,
        writes=[(inbox_path, next_inbox), (graph_path, next_graph)],
        report={"status": "fixture"},
    )
    receipt = json.loads((migration_root / "receipt.json").read_text(encoding="utf-8"))
    first_write = receipt["plannedWrites"][0]
    os.replace(tmp_path / first_write["stagedPath"], tmp_path / first_write["path"])

    report = rereview_pending_package(tmp_path)

    assert report["recoveredTransactions"] == [
        "system/migrations/w1-pending-semantic-rereview/interrupted:completed"
    ]
    assert json.loads(inbox_path.read_text(encoding="utf-8"))[0]["title"] == "recovered inbox"
    assert json.loads(graph_path.read_text(encoding="utf-8")) == next_graph
    completed = json.loads((migration_root / "receipt.json").read_text(encoding="utf-8"))
    assert completed["phase"] == "completed"
    assert len(completed["written"]) == 2
