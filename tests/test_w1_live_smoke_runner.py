import json

from tools.w1_live_smoke_10ch import _artifact_secret_leaks, _quality_probe_failures, _smoke_result_exit_code, parse_args


def _passing_probe():
    return {
        "chapter_count": 10,
        "manuscript_nodes_count": 20,
        "duplicate_chapter_numbers": [],
        "blocked_count": 0,
        "empty_branch_ids": [],
        "review_status": "pass",
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
        "chapter_count": 9,
        "manuscript_nodes_count": 0,
        "duplicate_chapter_numbers": [9],
        "blocked_count": 14,
        "empty_branch_ids": ["branch_empty"],
    })

    failures = _quality_probe_failures(probe)

    assert "chapter_count_not_10" in failures
    assert "manuscript_nodes_empty" in failures
    assert "duplicate_chapter_numbers" in failures
    assert "blocked_proposals" in failures
    assert "empty_timeline_branches" in failures
    assert _smoke_result_exit_code({"terminal": {"current_node": "done"}, "quality_probe": probe}) == 1


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


def test_secret_scan_catches_generated_artifact_leakage_without_real_key(tmp_path):
    (tmp_path / "run_config.safe.json").write_text(json.dumps({"api_key": "***"}), encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "bad.json").write_text(json.dumps({"authorization": "sk-test-not-a-real-key"}), encoding="utf-8")

    assert _artifact_secret_leaks(tmp_path) == ["nested/bad.json"]
