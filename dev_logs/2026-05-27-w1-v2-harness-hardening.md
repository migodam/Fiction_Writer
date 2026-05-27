# W1 V2 Harness Hardening

**Date:** 2026-05-27
**Branch:** `codex/w1-orchestrated-import-quality`

---

## Changes

### `benchmark_results/v2_planner_dry_run/run_harness.py`

- **CLI args** (`--output-dir`, `--no-write`, `--json-only`, `--case`): `--output-dir` overrides the default `runs/<ts>/` path; `--no-write` runs the matrix without writing any files; `--json-only` skips `benchmark_report.md`; `--case <id>` runs exactly one case.
- **Exit code 2** for unknown `--case` argument (prints valid IDs to stderr).
- **`run_manifest.json`**: written alongside benchmark output; includes `branch`, `head_commit` (via `git rev-parse`; gracefully `null` if not in a git repo), `dry_run: true`, `harness_schema_version: "1"`.
- **`harness_schema_version: "1"`** added to `benchmark_metrics.json`.
- **`_build_metrics(cases)`**: pure function split out of `_write_reports`; allows `--no-write` to compute and print results without touching disk.
- **`_write_reports(metrics, output_dir, json_only)`**: now takes the prebuilt metrics dict; also writes `run_manifest.json`.
- **Output file secret scan** (`_scan_output_file`, `_scan_output_files`): scans `benchmark_metrics.json` and `benchmark_report.md` line-by-line after writing. Lines matching `_PATTERN_DOC_LINE_RE` are skipped to avoid three known false positives: the `"pattern":` JSON key, the `Pattern checked:` markdown line, and the `DEEPSEEK_API_KEY=<key>` placeholder in the Gated Live Smoke notice.
- **Live smoke stub**: docstring updated with exact env gates, poll interval, stop-on-402 rule, and cost estimate.

### `tests/test_w1_v2_harness.py` (new)

5 tests in `TestHarnessCLI`:
- `test_dry_run_exits_zero` — full run returns exit 0
- `test_no_write_creates_no_output_dir` — `--no-write` leaves no files even when `--output-dir` is set
- `test_case_flag_runs_exactly_one_case` — `--case case_2_50ch_zh_deep` yields exactly 1 case in metrics
- `test_metrics_has_dry_run_flags` — `dry_run=true` and `live_model_calls=false` in generated JSON
- `test_secret_scan_passes_on_generated_outputs` — `_scan_output_files()` returns `passed=True` on generated files

---

## Command Examples

```bash
# Full dry run (default output to runs/<ts>/)
python benchmark_results/v2_planner_dry_run/run_harness.py

# Single case
python benchmark_results/v2_planner_dry_run/run_harness.py --case case_2_50ch_zh_deep

# Memory-only (no files written)
python benchmark_results/v2_planner_dry_run/run_harness.py --no-write

# Custom output dir
python benchmark_results/v2_planner_dry_run/run_harness.py --output-dir /tmp/harness_out

# JSON only (skip markdown report)
python benchmark_results/v2_planner_dry_run/run_harness.py --json-only

# Unknown case — exits 2
python benchmark_results/v2_planner_dry_run/run_harness.py --case bad_id; echo $?  # → 2
```

---

## Test Results

```
tests/test_w1_v2_harness.py              5 passed
tests/test_w1_orchestrator_artifacts.py  }
tests/test_w1_supervisor_policy.py       } 117 passed (0.41s)
tests/test_w1_granularity.py             }
```

Codex integration note: removed the harness-level insertion of `<repo>/sidecar` into `sys.path`.
Keeping only the repo root prevents `tests/test_w1_import_diagnostics.py` from resolving
`from tools import ...` to `sidecar/tools` when the harness module is imported in the same
pytest process.

Final combined W1 regression:

```
tests/test_w1_planner_proposal.py
tests/test_w1_orchestrator_artifacts.py
tests/test_w1_import_plan_validator.py
tests/test_w1_source_profile.py
tests/test_w1_v2_harness.py
tests/test_w1_granularity.py
tests/test_w1_supervisor_policy.py
tests/test_w1_supervisor_tools.py
tests/test_w1_extraction_variants.py
tests/test_w1_import_compiler.py
tests/test_w1_prompt_windows.py
tests/test_w1_import_diagnostics.py
→ 344 passed (4.25s)
```

---

## Unchanged

- All planner/granularity/policy logic
- `MATRIX`, `_make_chunks`, `_build_state`, `_secret_scan`, `_secret_scan_all`
- `run_gated_live_smoke()` — still a documented stub, not implemented
- No sidecar product code changed
- Old benchmark run directories preserved
