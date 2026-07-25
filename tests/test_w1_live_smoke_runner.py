import json
import asyncio
import hashlib

from tools.w1_live_smoke_10ch import (
    _artifact_secret_leaks,
    _normalize_terminal_status,
    _quality_probe,
    _quality_probe_failures,
    _run_live,
    _semantic_quality_metrics,
    _smoke_result_exit_code,
    _watch_streaming_updates,
    parse_args,
)


def _passing_probe():
    return {
        "canonical_chapter_count": 0,
        "canonical_manuscript_nodes_count": 0,
        "staged_acceptance_required": True,
        "staged_chapter_count": 10,
        "staged_manuscript_nodes_count": 20,
        "staged_scene_documents_count": 10,
        "proposal_write_receipt_counts": {"chapter": 10, "scene": 10},
        "duplicate_chapter_numbers": [],
        "blocked_count": 0,
        "empty_branch_ids": [],
        "review_status": "pass",
        "raw_source_evidence": {"failures": []},
        "usage_ledger": {"input_tokens": 100, "output_tokens": 50, "call_count": 2, "cost_usd": 0.01},
        "semantic_quality": {},
        "missing_required_artifacts": [],
    }


def test_smoke_runner_exit_code_passes_clean_result():
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": _passing_probe()}) == 0


def test_smoke_runner_exit_code_fails_hard_fail_even_without_errors():
    assert _smoke_result_exit_code({
        "terminal": {"current_node": "qa_review", "converge_status": "hard_fail"},
        "quality_probe": _passing_probe(),
    }) == 1


def test_smoke_runner_exit_code_fails_terminal_error_and_budget():
    assert _smoke_result_exit_code({"terminal": {"status": "error"}, "quality_probe": _passing_probe()}) == 1
    assert _smoke_result_exit_code({"terminal": {"status": "budget_exhausted"}, "quality_probe": _passing_probe()}) == 1
    assert _smoke_result_exit_code({"terminal": {"status": "timeout"}, "quality_probe": _passing_probe()}) == 1
    assert _smoke_result_exit_code({"terminal": {"status": "auth_failed"}, "quality_probe": _passing_probe()}) == 1


def test_smoke_runner_quality_probe_fails_product_gaps():
    probe = _passing_probe()
    probe.update({
        "staged_chapter_count": 9,
        "staged_manuscript_nodes_count": 0,
        "duplicate_chapter_numbers": [9],
        "blocked_count": 14,
        "empty_branch_ids": ["branch_empty"],
    })

    failures = _quality_probe_failures(probe)

    assert "staged_chapter_count_not_10" in failures
    assert "staged_manuscript_nodes_count_not_20" in failures
    assert "duplicate_chapter_numbers" in failures
    assert "blocked_proposals" in failures
    assert "empty_timeline_branches" in failures
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": probe}) == 1


def test_semantic_gate_rejects_20260713_013817_reviewer_shape_and_accepts_clean_staged_projection():
    # This is the relevant nested reviewer-report shape from the offline live smoke
    # artifact. The low thin-card finding remains advisory, while the semantic
    # findings make a completed runner exit non-zero.
    old_inbox = [{"operations": [
        {"entityType": "character", "entityId": "char_a", "fields": {"id": "char_a", "name": "韩立"}},
        {"entityType": "character", "entityId": "char_b", "fields": {"id": "char_b", "name": "韩立"}},
        *[
            {"entityType": "timeline_event", "entityId": f"event_{index}", "fields": {"timelineClass": "canonical_event", "branchId": "branch_import_main"}}
            for index in range(11)
        ],
    ]}]
    old_review = {"status": "warning", "reviewer_reports": {
        "quality": {"findings": [
            {"finding_id": "character_duplicate_name_韩立", "check_name": "character_duplicate_name", "entity_refs": ["char_a", "char_b"]},
            {"finding_id": "branch_over_budget_branch_import_main", "check_name": "branch_over_budget", "entity_refs": ["event_0"]},
            {"finding_id": "manuscript_empty_manuscript", "check_name": "manuscript_empty", "entity_refs": []},
            {"finding_id": "character_thin_card_char_a", "check_name": "character_thin_card", "entity_refs": ["char_a"]},
        ]},
        "fact": {"findings": [
            {"finding_id": "evidence_missing_char_a", "check_name": "evidence_missing", "entity_refs": ["char_a"]},
        ]},
    }}
    old_semantic = _semantic_quality_metrics(
        old_inbox, old_review, {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}}, "zh", 10, {},
    )
    old_probe = _passing_probe()
    old_probe["semantic_quality"] = old_semantic

    old_failures = _quality_probe_failures(old_probe)

    assert {"duplicate_canonical_character_names", "unresolved_evidence_missing", "branch_density_over_budget"} <= set(old_failures)
    assert "manuscript_empty" not in old_failures
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": old_probe}) == 1

    clean_semantic = _semantic_quality_metrics(
        [], {"reviewer_reports": {"quality": {"findings": [{"check_name": "character_thin_card"}]}}},
        {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}}, "zh", 10, {},
    )
    clean_probe = _passing_probe()
    clean_probe["semantic_quality"] = clean_semantic

    assert _quality_probe_failures(clean_probe) == []
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": clean_probe}) == 0


def test_semantic_gate_enforces_tags_relationships_world_usage_and_identity_exception():
    inbox = [{"operations": [
        {"entityType": "character", "entityId": "wang_1", "fields": {"id": "wang_1", "name": "王二", "identityDisambiguator": "铁匠"}},
        {"entityType": "character", "entityId": "wang_2", "fields": {"id": "wang_2", "name": "王二", "identityDisambiguator": "药童"}},
        {"entityType": "character_tag", "fields": {"name": "Main Cast"}},
        {"entityType": "relationship", "entityId": "rel_1", "fields": {"type": "解惑", "category": "mentor_disciple"}},
        {"entityType": "world_item", "fields": {"name": "人物关系图"}},
    ]}]
    semantic = _semantic_quality_metrics(
        inbox,
        {"reviewer_reports": {"quality": {"findings": [{"check_name": "world_module_pollution"}]}}},
        {"budget_status": {"exhausted": True, "remaining": {"calls": -1}}},
        "zh",
        0,
        {"canonical_events": [{"branchId": "branch_main"} for _ in range(11)]},
    )
    probe = _passing_probe()
    probe["semantic_quality"] = semantic

    failures = _quality_probe_failures(probe)

    assert "duplicate_canonical_character_names" not in failures
    assert {"branch_density_over_budget", "illegal_or_english_tags", "invalid_relationship_types", "world_module_contamination", "usage_ledger_exhausted", "usage_ledger_over_cap"} <= set(failures)


def test_semantic_gate_rejects_high_evidence_profile_gaps_and_world_organization_misplacements():
    inbox = [{"operations": [
        {"entityType": "character", "entityId": "char_hero", "fields": {
            "id": "char_hero", "name": "韩立", "role": "protagonist", "notes": ["有明确的童年证据"],
            "background": "", "experience": [],
        }},
        {"entityType": "world_item", "entityId": "world_person", "fields": {
            "name": "韩立", "category": "organization",
        }},
        {"entityType": "world_item", "entityId": "world_event", "fields": {
            "name": "七玄门内门测试", "category": "organization",
        }},
    ]}]
    semantic = _semantic_quality_metrics(
        inbox,
        {"reviewer_reports": {"fact": {"findings": [
            {"check_name": "evidence_entity_mismatch", "severity": "high"},
            {"check_name": "evidence_unusable", "severity": "medium"},
        ]}}},
        {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}},
        "zh",
        10,
        {"canonical_events": [{"title": "七玄门内门测试", "branchId": "branch_main"}]},
    )
    probe = _passing_probe()
    probe["semantic_quality"] = semantic

    failures = _quality_probe_failures(probe)

    assert {
        "high_evidence_entity_mismatch",
        "evidence_unusable",
        "major_character_supported_profile_gaps",
        "person_as_world_organization",
        "event_as_world_organization",
    } <= set(failures)


def test_semantic_gate_keeps_expected_timeline_discards_informational():
    semantic = _semantic_quality_metrics(
        [],
        {"reviewer_reports": {}},
        {"budget_status": {"exhausted": False, "remaining": {"calls": 1}}},
        "zh",
        10,
        {"discarded_duplicates": [{"timelineClass": "discarded_duplicate"}], "scene_beats": [{"title": "过场"}]},
    )
    probe = _passing_probe()
    probe["semantic_quality"] = semantic

    assert _quality_probe_failures(probe) == []
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": probe}) == 0


def test_smoke_runner_defaults_are_bounded_and_accept_only_v4_models():
    args = parse_args([])

    assert args.model == "deepseek-v4-flash"
    assert args.max_cost_usd == 3.0
    assert args.max_calls > 0
    assert args.max_total_tokens > 0


def test_missing_required_artifacts_hard_fails():
    probe = _passing_probe()
    probe["missing_required_artifacts"] = ["manifest.json"]

    assert "missing_required_artifacts" in _quality_probe_failures(probe)
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": probe}) == 1


def test_staged_projection_is_the_acceptance_gate_and_canonical_writes_fail(tmp_path):
    project = tmp_path / "project"
    artifact_dir = project / "system" / "imports" / "run_1"
    artifact_dir.mkdir(parents=True)
    raw_source = "chapter one\nchapter two"
    raw_hash = hashlib.sha256(raw_source.encode("utf-8")).hexdigest()
    span = {
        "raw_source_hash": raw_hash,
        "absolute_start": 0,
        "absolute_end": len(raw_source),
        "substring_hash": raw_hash,
    }
    (artifact_dir / "raw_source.txt").write_text(raw_source, encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps({"source_hash": raw_hash, "segments": [{"source_span": span}]}), encoding="utf-8")
    (artifact_dir / "review_report.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    (artifact_dir / "judge_artifact.json").write_text(json.dumps({}), encoding="utf-8")
    receipt_records = [{"entity_type": "chapter"}] * 10 + [{"entity_type": "scene"}] * 10
    (artifact_dir / "proposal_write_receipts.json").write_text(json.dumps({
        "proposal_counts": {"chapter": 10, "scene": 10},
        "receipts": receipt_records,
    }), encoding="utf-8")
    (artifact_dir / "staged_manuscript_projection.json").write_text(json.dumps({
        "acceptance_required": True,
        "chapters": [{"source_span": span}] * 10,
        "nodes": [{}] * 20,
        "scene_documents": [{"source_span": span}] * 10,
    }), encoding="utf-8")
    for name in ("prompt_windows.json", "evidence_cards.json", "cross_validation.json", "timeline_architecture.json"):
        (artifact_dir / name).write_text("{}", encoding="utf-8")
    (project / "system").mkdir(exist_ok=True)
    (project / "system" / "inbox.json").write_text("[]", encoding="utf-8")
    (project / "writing" / "manuscript").mkdir(parents=True)
    (project / "writing" / "manuscript" / "nodes.json").write_text("[]", encoding="utf-8")

    probe = _quality_probe(project)
    failures = _quality_probe_failures(probe)

    assert probe["canonical_chapter_count"] == 0
    assert probe["staged_chapter_count"] == 10
    assert probe["staged_manuscript_nodes_count"] == 20
    assert probe["staged_scene_documents_count"] == 10
    assert "canonical_chapters_written_before_acceptance" not in failures
    assert "staged_chapter_count_not_10" not in failures
    assert "raw_source_evidence_invalid" not in failures
    assert "usage_ledger_missing" in failures

    (project / "manuscript.json").write_text(json.dumps({"chapters": [{"title": "第一章"}]}), encoding="utf-8")
    assert "canonical_chapters_written_before_acceptance" in _quality_probe_failures(_quality_probe(project))


def test_usage_ledger_requires_real_token_call_and_cost_values():
    probe = _passing_probe()
    probe["usage_ledger"] = None
    assert "usage_ledger_missing" in _quality_probe_failures(probe)


def test_quality_probe_extracts_complete_usage_ledger_from_production_artifact(tmp_path):
    project = tmp_path / "project"
    artifact_dir = project / "system" / "imports" / "run_ledger"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "usage_ledger.json").write_text(json.dumps({
        "actual_input_tokens": 321, "actual_output_tokens": 123, "api_call_count": 4, "cost_usd": 0.045,
    }), encoding="utf-8")

    ledger = _quality_probe(project)["usage_ledger"]

    assert ledger == {
        "source": "usage_ledger",
        "path": "$",
        "input_tokens": 321,
        "output_tokens": 123,
        "call_count": 4,
        "cost_usd": 0.045,
    }


def test_quality_probe_rejects_invalid_usage_ledger_numeric_types(tmp_path):
    artifact_dir = tmp_path / "project" / "system" / "imports" / "run_ledger"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "usage_ledger.json").write_text(json.dumps({
        "actual_input_tokens": 321.0,
        "actual_output_tokens": 123,
        "api_call_count": -1,
        "cost_usd": -0.045,
    }), encoding="utf-8")

    assert _quality_probe(tmp_path / "project")["usage_ledger"] is None


def test_quality_probe_binds_to_expected_import_run_not_newest_old_ledger(tmp_path):
    project = tmp_path / "project"
    old_run = project / "system" / "imports" / "old_run"
    expected_run = project / "system" / "imports" / "expected_run"
    old_run.mkdir(parents=True)
    expected_run.mkdir(parents=True)
    (old_run / "usage_ledger.json").write_text(json.dumps({
        "actual_input_tokens": 321, "actual_output_tokens": 123, "actual_calls": 4, "cost_usd": 0.045,
    }), encoding="utf-8")
    (expected_run / "manifest.json").write_text(json.dumps({"import_run_id": "expected_run"}), encoding="utf-8")

    probe = _quality_probe(project, expected_import_run_id="expected_run")

    assert probe["latest_import_dir"].endswith("expected_run")
    assert probe["usage_ledger"] is None
    assert "usage_ledger_missing" in _quality_probe_failures(probe)


def test_quality_probe_prefers_canonical_lineage_attempt_directory_over_legacy_run_id(tmp_path):
    project = tmp_path / "project"
    lineage_id = "lineage_current"
    attempt_id = "attempt_current"
    canonical = project / "system" / "imports" / lineage_id / "attempts" / attempt_id
    legacy = project / "system" / "imports" / "live_smoke_legacy"
    canonical.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (canonical / "manifest.json").write_text(json.dumps({
        "lineage_id": lineage_id,
        "attempt_id": attempt_id,
        "import_run_id": "legacy_name_must_not_select_this",
    }), encoding="utf-8")
    (legacy / "usage_ledger.json").write_text(json.dumps({
        "actual_input_tokens": 321,
        "actual_output_tokens": 123,
        "actual_calls": 4,
        "cost_usd": 0.045,
    }), encoding="utf-8")

    probe = _quality_probe(
        project,
        expected_lineage_id=lineage_id,
        expected_attempt_id=attempt_id,
        expected_import_run_id="live_smoke_legacy",
    )

    assert probe["latest_import_dir"].endswith(
        "lineage_current/attempts/attempt_current",
    )
    assert probe["artifact_lineage_id"] == lineage_id
    assert probe["artifact_attempt_id"] == attempt_id
    assert probe["usage_ledger"] is None


def test_quality_probe_rejects_wrong_canonical_attempt_without_falling_back(tmp_path):
    project = tmp_path / "project"
    valid = project / "system" / "imports" / "lineage_1" / "attempts" / "attempt_1"
    valid.mkdir(parents=True)
    (valid / "manifest.json").write_text("{}", encoding="utf-8")

    probe = _quality_probe(
        project,
        expected_lineage_id="lineage_1",
        expected_attempt_id="attempt_other",
    )

    assert probe["latest_import_dir"] is None
    assert "manifest.json" in probe["missing_required_artifacts"]


def test_terminal_normalization_accepts_done_passed_and_preserves_safety_gates():
    assert _normalize_terminal_status({
        "current_node": "done",
        "converge_status": "passed",
    }, unknown_provider_calls=False)["status"] == "completed"
    assert _normalize_terminal_status({
        "current_node": "done",
        "converge_status": "passed",
    }, unknown_provider_calls=True)["status"] == "waiting_human"
    assert _normalize_terminal_status({
        "current_node": "done",
        "converge_status": "passed",
        "errors": ["provider failed"],
    }, unknown_provider_calls=False)["status"] == "error"


def test_secret_scan_catches_generated_artifact_leakage_without_real_key(tmp_path):
    (tmp_path / "run_config.safe.json").write_text(json.dumps({"api_key": "***"}), encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "bad.json").write_text(json.dumps({"authorization": "sk-test-not-a-real-key"}), encoding="utf-8")

    assert _artifact_secret_leaks(tmp_path) == ["nested/bad.json"]


def test_watchdog_times_out_silent_stream_and_cancels_producer(tmp_path):
    cancelled = False

    async def silent_stream():
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
            yield {}
        finally:
            cancelled = True

    updates, terminal = asyncio.run(
        _watch_streaming_updates(
            silent_stream(),
            tmp_path,
            timeout_seconds=0.03,
            heartbeat_seconds=0.005,
        )
    )

    assert updates == []
    assert terminal["status"] == "timeout"
    assert cancelled


def test_watchdog_writes_heartbeat_file_for_a_silent_stream(tmp_path):
    async def silent_stream():
        await asyncio.Event().wait()
        yield {}

    asyncio.run(
        _watch_streaming_updates(
            silent_stream(),
            tmp_path,
            timeout_seconds=0.03,
            heartbeat_seconds=0.005,
        )
    )

    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["elapsed"] >= 0
    assert heartbeat["last_update_age"] >= 0
    assert heartbeat["last_node"] is None
    assert heartbeat["update_count"] == 0


def test_watchdog_marks_silent_stream_stalled_before_wall_clock_timeout(tmp_path):
    cancelled = False

    async def silent_stream():
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
            yield {}
        finally:
            cancelled = True

    _, terminal = asyncio.run(
        _watch_streaming_updates(
            silent_stream(),
            tmp_path,
            timeout_seconds=1,
            heartbeat_seconds=0.005,
            stalled_seconds=0.03,
            cleanup_timeout_seconds=0.1,
        )
    )

    assert terminal["status"] == "stalled"
    assert terminal["watchdog_events"][0]["event_type"] == "stream_stalled"
    assert cancelled
    events = json.loads((tmp_path / "watchdog_events.json").read_text(encoding="utf-8"))
    assert events[0]["event_type"] == "stream_stalled"
    assert _smoke_result_exit_code({"terminal": terminal, "quality_probe": _passing_probe()}) == 1


def test_watchdog_collects_normal_updates_and_tracks_latest_node(tmp_path):
    async def normal_stream():
        yield {"progress": 10, "current_node": "segment"}
        await asyncio.sleep(0)
        yield {"progress": 100, "current_tool": "proposal_write"}

    updates, terminal = asyncio.run(
        _watch_streaming_updates(
            normal_stream(),
            tmp_path,
            timeout_seconds=1,
            heartbeat_seconds=0.005,
        )
    )

    assert [update["progress"] for update in updates] == [10, 100]
    assert terminal["current_tool"] == "proposal_write"
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["last_node"] == "proposal_write"
    assert heartbeat["update_count"] == 2


def test_watchdog_does_not_stall_slow_provider_with_durable_activity(tmp_path):
    activity = {"sequence": 0}

    async def slow_provider_stream():
        await asyncio.sleep(0.09)
        yield {"progress": 100, "current_tool": "proposal_write"}

    def durable_probe(after_sequence=0):
        if activity["sequence"] <= after_sequence:
            return {
                "sequence": activity["sequence"],
                "events": [],
                "active_api_calls": 1,
            }
        return {
            "sequence": activity["sequence"],
            "events": [{
                "sequence": activity["sequence"],
                "event_type": "w1_activity",
                "payload": {
                    "status": "heartbeat",
                    "tool": "provider.chat.completions",
                    "active_api_calls": 1,
                },
            }],
            "active_api_calls": 1,
        }

    def provider_heartbeat():
        activity["sequence"] += 1

    updates, terminal = asyncio.run(
        _watch_streaming_updates(
            slow_provider_stream(),
            tmp_path,
            timeout_seconds=0.5,
            heartbeat_seconds=0.01,
            stalled_seconds=0.025,
            activity_probe=durable_probe,
            on_heartbeat=provider_heartbeat,
        )
    )

    assert updates[-1]["current_tool"] == "proposal_write"
    assert terminal.get("status") != "stalled"
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["durable_event_sequence"] > 0
    assert heartbeat["active_api_calls"] == 1


def test_runner_persists_timeout_final_result_for_a_silent_stream(tmp_path, monkeypatch):
    from sidecar.workflows import w1_import

    async def silent_stream(*_args, **_kwargs):
        await asyncio.Event().wait()
        yield {}

    monkeypatch.setattr(w1_import, "run_streaming", silent_stream)
    args = parse_args([])
    args.timeout_seconds = 0.03
    args.heartbeat_seconds = 0.005

    result = asyncio.run(_run_live(args, tmp_path / "project", tmp_path / "output"))

    assert result["terminal"]["status"] == "timeout"
    final_result = json.loads((tmp_path / "output" / "final_result.json").read_text(encoding="utf-8"))
    assert final_result["terminal"]["status"] == "timeout"


def test_runner_stops_truly_silent_work_and_releases_workflow_lock(tmp_path, monkeypatch):
    from sidecar.utils.lock import acquire_lock
    from sidecar.workflows import w1_import

    source = tmp_path / "source.txt"
    source.write_text("第一章\n韩立入门。", encoding="utf-8")

    async def silent_stream(project_path, _config):
        await acquire_lock(project_path, "W1")
        await asyncio.Event().wait()
        yield {}

    monkeypatch.setattr(w1_import, "run_streaming", silent_stream)
    args = parse_args(["--source", str(source)])
    args.timeout_seconds = 0.2
    args.heartbeat_seconds = 0.01
    args.stalled_seconds = 0.03
    args.cleanup_timeout_seconds = 0.1
    project = tmp_path / "project"

    result = asyncio.run(_run_live(args, project, tmp_path / "output"))

    assert result["terminal"]["status"] == "stalled"
    assert result["runtime"]["attempt"]["status"] == "interrupted"
    assert result["runtime"]["unknown_calls"] == []
    assert result["runtime"]["lease_released"] is True
    assert result["runtime"]["cleanup_complete"] is True
    assert not (project / "workflow.lock").exists()


def test_runner_uses_product_runtime_identity_harness_and_server_budget(tmp_path, monkeypatch):
    from sidecar.workflows import w1_import

    source = tmp_path / "source.txt"
    source.write_text("第一章\n韩立入门。", encoding="utf-8")
    captured = {}

    async def complete_at_gate(_project_path, config):
        captured.update(config)
        yield {
            "status": "done",
            "progress": 1.0,
            "current_node": "proposal_gate",
            "converge_status": "awaiting_acceptance",
        }

    monkeypatch.setattr(w1_import, "run_streaming", complete_at_gate)
    args = parse_args(["--source", str(source)])

    result = asyncio.run(
        _run_live(args, tmp_path / "project", tmp_path / "output"),
    )

    assert captured["execution_mode"] == "supervisor"
    assert captured["harness_observer"] is True
    assert captured["session_id"] == captured["attempt_id"]
    assert captured["runtime_store"] is not None
    assert captured["runtime_fence_token"] >= 1
    assert captured["budget_policy"]["max_cost_usd"] == 3.0
    assert captured["budget_policy"]["max_calls"] == 100
    assert result["runtime"]["attempt"]["status"] == "waiting_human"
    run_config = captured["runtime_store"].get_run(
        result["runtime"]["run_id"],
    )["config"]
    assert run_config["budget_config"]["max_cost_usd"] == 3.0
    assert "api_key" not in json.dumps(run_config)


def test_runner_marks_done_passed_attempt_and_run_completed(tmp_path, monkeypatch):
    from sidecar.workflows import w1_import

    source = tmp_path / "source.txt"
    source.write_text("第一章\n韩立入门。", encoding="utf-8")

    async def done_passed(_project_path, _config):
        yield {
            "current_node": "done",
            "converge_status": "passed",
        }

    monkeypatch.setattr(w1_import, "run_streaming", done_passed)
    result = asyncio.run(_run_live(
        parse_args(["--source", str(source)]),
        tmp_path / "project",
        tmp_path / "output",
    ))

    assert result["terminal"]["status"] == "completed"
    assert result["runtime"]["attempt"]["status"] == "completed"
    assert result["runtime"]["run"]["status"] == "completed"


def test_runner_cancel_marks_provider_intent_unknown_and_cleans_lock(tmp_path, monkeypatch):
    from sidecar.utils.lock import acquire_lock
    from sidecar.workflows import w1_import
    from sidecar.workflows.w1_run_events import append_event, set_active_call

    source = tmp_path / "source.txt"
    source.write_text("第一章\n韩立入门。", encoding="utf-8")
    project = tmp_path / "project"
    output = tmp_path / "output"

    class SlowProvider:
        model_name = "deepseek-v4-flash"

        async def ainvoke(self, _messages):
            await asyncio.Event().wait()

    async def provider_stream(project_path, config):
        await acquire_lock(project_path, "W1")
        session_id = config["session_id"]
        append_event(session_id, {
            "phase": "extracting",
            "tool": "extract_window",
            "status": "start",
            "message": "Starting fake provider call.",
        })
        set_active_call(session_id, 1)
        try:
            await w1_import._ainvoke_with_budget(
                SlowProvider(),
                [{"role": "user", "content": "fixture"}],
                session_id=session_id,
                estimated_input_tokens=10,
                estimated_output_tokens=10,
            )
        finally:
            set_active_call(session_id, -1)
        yield {"progress": 1.0, "current_node": "done"}

    monkeypatch.setattr(w1_import, "run_streaming", provider_stream)
    args = parse_args(["--source", str(source)])
    args.timeout_seconds = 0.08
    args.heartbeat_seconds = 0.01
    args.stalled_seconds = 0.025
    args.cleanup_timeout_seconds = 0.1

    result = asyncio.run(_run_live(args, project, output))

    assert result["terminal"]["status"] == "timeout"
    assert result["runtime"]["attempt"]["status"] == "waiting_human"
    assert result["runtime"]["unknown_calls"]
    assert result["runtime"]["unknown_calls"][0]["status"] == "unknown_outcome"
    assert result["runtime"]["active_intents"] == []
    assert result["runtime"]["lease_released"] is True
    assert result["runtime"]["cleanup_complete"] is True
    assert not (project / "workflow.lock").exists()
    assert result["runtime"]["last_activity"]["sequence"] > 0
    assert result["runtime"]["usage"]["actual_calls"] == 0


def test_runner_redacts_exception_text_before_persisting_final_result(tmp_path, monkeypatch):
    from sidecar.workflows import w1_import

    async def failing_stream(*_args, **_kwargs):
        raise RuntimeError("provider rejected sk-test-secret-token")
        yield {}

    monkeypatch.setattr(w1_import, "run_streaming", failing_stream)
    args = parse_args([])

    result = asyncio.run(_run_live(args, tmp_path / "project", tmp_path / "output"))
    final_result_path = tmp_path / "output" / "final_result.json"

    assert "sk-test-secret-token" not in final_result_path.read_text(encoding="utf-8")
    assert "sk-test-secret-token" not in json.dumps(result)
    assert "final_result.json" not in _artifact_secret_leaks(tmp_path / "output")
