"""Behavior tests for run_harness.py CLI and dry-run output."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS_DIR = Path(__file__).parent.parent / "benchmark_results" / "v2_planner_dry_run"
_HARNESS_PATH = _HARNESS_DIR / "run_harness.py"

# Import harness functions directly; this also injects repo/sidecar onto sys.path.
sys.path.insert(0, str(_HARNESS_DIR))
import run_harness


class TestHarnessCLI:
    def test_dry_run_exits_zero(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--output-dir", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_no_write_creates_no_output_dir(self, tmp_path):
        out = tmp_path / "out"
        result = subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--no-write", "--output-dir", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not out.exists(), "output dir must not be created when --no-write is set"

    def test_case_flag_runs_exactly_one_case(self, tmp_path):
        out = tmp_path / "out"
        result = subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--case", "case_2_50ch_zh_deep",
             "--output-dir", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        metrics = json.loads((out / "benchmark_metrics.json").read_text())
        assert len(metrics["cases"]) == 1
        assert metrics["cases"][0]["id"] == "case_2_50ch_zh_deep"

    def test_metrics_has_dry_run_flags(self, tmp_path):
        out = tmp_path / "out"
        subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--output-dir", str(out)],
            check=True, capture_output=True,
        )
        metrics = json.loads((out / "benchmark_metrics.json").read_text())
        assert metrics["dry_run"] is True
        assert metrics["live_model_calls"] is False

    def test_secret_scan_passes_on_generated_outputs(self, tmp_path):
        out = tmp_path / "out"
        subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--output-dir", str(out)],
            check=True, capture_output=True,
        )
        scan = run_harness._scan_output_files(out)
        assert scan["passed"], f"Secret found in output files: {scan['hits']}"

    def test_quality_summary_fields_present(self, tmp_path):
        out = tmp_path / "out"
        subprocess.run(
            [sys.executable, str(_HARNESS_PATH), "--case", "case_1_10ch_zh_deep",
             "--output-dir", str(out)],
            check=True, capture_output=True,
        )
        metrics = json.loads((out / "benchmark_metrics.json").read_text())
        case_summary = metrics["cases"][0]["quality_summary"]
        for key in (
            "verdict",
            "warning_count",
            "hard_failure_count",
            "selected_suggested_actions",
            "token_cost_ledger",
        ):
            assert key in case_summary
        assert case_summary["hard_failure_count"] == 0
        assert case_summary["token_cost_ledger"]["live_model_calls"] is False
        assert "quality_summary" in metrics
