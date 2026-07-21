import hashlib
import json
from pathlib import Path

from tools.w1_repair_completed_attempt import repair_attempt


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_completed_attempt_repair_is_offline_atomic_and_keeps_proposals_pending(tmp_path):
    project = tmp_path / "project"
    run_dir = project / "system" / "imports" / "lineage_test" / "attempts" / "attempt_test"
    raw_source = "韩立出生在山村，后来跟随三叔离家前往七玄门。"
    source_hash = hashlib.sha256(raw_source.encode("utf-8")).hexdigest()
    substring_hash = source_hash
    span = {
        "raw_source_hash": source_hash,
        "absolute_start": 0,
        "absolute_end": len(raw_source),
        "substring_hash": substring_hash,
    }
    (run_dir / "raw_source.txt").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "raw_source.txt").write_text(raw_source, encoding="utf-8")
    _write(run_dir / "manifest.json", {"source_hash": source_hash})
    _write(run_dir / "checkpoint.json", {
        "attempt_id": "attempt_test",
        "total_chunks": 10,
        "committed_chunk_ids": list(range(10)),
    })
    _write(run_dir / "project_structure_digest.json", {})
    _write(run_dir / "staged_manuscript_projection.json", {
        "chapters": [{"id": f"chapter_{index}"} for index in range(10)],
    })
    _write(run_dir / "timeline_architecture.json", {
        "root_branch_id": "branch_main",
        "branches": [
            {"id": "branch_main", "mode": "root"},
            {"id": "branch_empty", "mode": "forked"},
        ],
        "canonical_events": [{"event_id": "event_leave", "branchId": "branch_main"}],
    })
    _write(run_dir / "review_report.json", {"warnings": [], "errors": []})
    _write(run_dir / "evidence_cards.json", [
        {
            "id": "evc_han",
            "kind": "character",
            "candidate_ids": ["char_han"],
            "candidate_names": ["韩立"],
            "source_segment_id": "seg_0",
            "source_span": span,
            "summary": "韩立出生在山村",
            "raw": {
                "canonical_id": "char_han",
                "canonical_name": "韩立",
                "importance": "core",
                "role_in_story": "主角，山村少年",
                "notes": ["[chunk 0] 跟随三叔离家前往七玄门"],
            },
        },
        {
            "id": "evc_leave",
            "kind": "event",
            "candidate_ids": ["event_leave"],
            "candidate_names": ["韩立离家"],
            "source_segment_id": "seg_0",
            "source_span": span,
            "summary": "韩立跟随三叔离家",
            "raw": {"event_id": "event_leave"},
        },
    ])
    inbox_path = project / "system" / "inbox.json"
    _write(inbox_path, [
        {
            "id": "prop_han",
            "status": "pending",
            "operations": [{
                "entityType": "character",
                "entityId": "char_han",
                "fields": {"name": "韩立", "background": "", "experience": [], "notes": []},
            }],
        },
        {
            "id": "prop_leave",
            "status": "pending",
            "operations": [{
                "entityType": "timeline_event",
                "entityId": "event_leave",
                "fields": {"title": "韩立离家", "branchId": "branch_main"},
            }],
        },
    ])

    dry_run = repair_attempt(project, run_dir, apply=False)
    assert dry_run["provider_calls"] == 0
    assert dry_run["character_proposals_updated"] == 1
    assert dry_run["event_proposals_updated"] == 1
    assert _read_statuses(inbox_path) == ["pending", "pending"]

    result = repair_attempt(project, run_dir, apply=True)
    repaired = json.loads(inbox_path.read_text(encoding="utf-8"))
    character = repaired[0]["operations"][0]["fields"]
    event = repaired[1]["operations"][0]["fields"]
    assert character["background"] == "主角"
    assert character["experience"]
    assert character["evidenceRefs"] == ["evc_han"]
    assert event["evidenceRefs"] == ["evc_leave"]
    assert _read_statuses(inbox_path) == ["pending", "pending"]
    assert result["timeline_branches_removed"] == 1
    assert (Path(result["backup_dir"]) / "receipt.json").is_file()


def _read_statuses(path: Path) -> list[str]:
    return [item["status"] for item in json.loads(path.read_text(encoding="utf-8"))]
