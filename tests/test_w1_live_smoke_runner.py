from tools.w1_live_smoke_10ch import _quality_probe_failures, _smoke_result_exit_code


def _passing_probe():
    return {
        "chapter_count": 10,
        "manuscript_nodes_count": 20,
        "duplicate_chapter_numbers": [],
        "blocked_count": 0,
        "empty_branch_ids": [],
        "review_status": "pass",
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
