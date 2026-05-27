#!/usr/bin/env python3
"""W1 V2 Planner Dry-Run Validation Harness.

Runs the 5-case zero-cost matrix against the deterministic V2 orchestrator
planner chain and writes a machine-readable JSON report + markdown summary.

Usage:
    python benchmark_results/v2_planner_dry_run/run_harness.py [OPTIONS]

Options:
    --output-dir PATH   Override default runs/<ts> output directory
    --no-write          Run matrix and print results without writing any files
    --json-only         Write benchmark_metrics.json only, skip benchmark_report.md
    --case CASE_ID      Run only this case_id (e.g. case_2_50ch_zh_deep)

No API key required. No live model calls. Safe to re-run at any time.

Exit codes:
    0  All cases PASS
    1  One or more cases FAIL
    2  Configuration / argument error

Gated live smoke (10-ch deep run):
    Set LIVE_SMOKE_APPROVED=1 and DEEPSEEK_API_KEY=<key> to enable.
    This section will NOT run unless both are set.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path so sidecar imports work from any CWD
_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))

from sidecar.models.state import (
    analyze_source_profile,
    plan_converge_target,
    plan_import_pipeline,
    plan_tool_operating_spec,
    select_granularity_profile,
    validate_import_plan,
)
from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    W1_EXTRACT_CHARACTERS_DEEP_FINE,
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    W1_EXTRACT_EVENTS_DEEP_DENSE,
)
from sidecar.supervisor.tools import (
    _select_extraction_prompts,
    _selected_extraction_prompt_manifest,
)

_SECRET_RE = re.compile(r"sk-|DEEPSEEK_API_KEY|Bearer |api\.deepseek", re.IGNORECASE)
_PATTERN_DOC_LINE_RE = re.compile(
    r'(Pattern checked:|"pattern"\s*:|DEEPSEEK_API_KEY=<)',
    re.IGNORECASE,
)

# Matrix: (id, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars)
MATRIX = [
    ("case_1_10ch_zh_deep",     10, "zh", "deep",     "fine_short_story", "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_FINE,     W1_EXTRACT_EVENTS_DEEP_DENSE,   15),
    ("case_2_50ch_zh_deep",     50, "zh", "deep",     "coarse_webnovel",  "coarse_webnovel",  W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 50),
    ("case_3_40ch_en_deep",     40, "en", "deep",     "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 40),
    ("case_4_20ch_en_balanced", 20, "en", "balanced", "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 24),
    ("case_5_10ch_en_fast",     10, "en", "fast",     "coarse_webnovel",  "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_ARC,      5),
]


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="W1 V2 Planner Dry-Run Validation Harness")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Override default runs/<ts> output directory")
    p.add_argument("--no-write", action="store_true",
                   help="Run matrix and print results without writing any files")
    p.add_argument("--json-only", action="store_true",
                   help="Write benchmark_metrics.json only, skip benchmark_report.md")
    p.add_argument("--case", default=None,
                   help="Run only this case_id (e.g. case_2_50ch_zh_deep)")
    return p.parse_args(argv)


def _make_chunks(n, chars_each=1000):
    return [{"chunk_id": i, "content": "x" * chars_each, "chapter_hint": f"Ch{i+1}", "entity_mentions": []} for i in range(n)]


def _build_state(n, lang, profile):
    chunks = _make_chunks(n)
    source_profile = analyze_source_profile(chunks, lang, profile)
    spec = plan_tool_operating_spec(profile, lang, n, use_supervisor=True)
    granularity = select_granularity_profile(n, lang, profile)
    target = plan_converge_target(spec, lang, n, granularity_profile=granularity)
    import_plan = plan_import_pipeline(granularity, spec, source_language=lang, prompt_profile=profile, chapter_count=n)
    is_valid, errors = validate_import_plan(import_plan)
    return {
        "chunks": chunks,
        "source_language": lang,
        "prompt_profile": profile,
        "source_profile": source_profile,
        "tool_operating_spec": spec,
        "import_granularity_profile": granularity,
        "converge_target": target,
        "import_plan": import_plan,
        "import_plan_validation": {"ok": is_valid, "errors": errors},
    }


def _secret_scan(payload_dict):
    serialized = json.dumps(payload_dict, ensure_ascii=False)
    return _SECRET_RE.search(serialized) is None


def run_matrix(matrix=None):
    if matrix is None:
        matrix = MATRIX
    from sidecar.supervisor.quality import evaluate_import_quality
    results = []
    for case_id, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars in matrix:
        state = _build_state(n, lang, profile)
        prompts = _select_extraction_prompts(state)
        manifest = _selected_extraction_prompt_manifest(state)
        rubric = evaluate_import_quality(state)

        assertions = {
            "granularity_profile_name": state["import_granularity_profile"]["profile_name"] == exp_gran,
            "source_profile_type":      state["source_profile"]["recommended_granularity_profile"] == exp_src,
            "expected_min_characters":  state["converge_target"]["expected_min_characters"] == exp_min_chars,
            "import_plan_valid":        state["import_plan_validation"]["ok"] is True,
            "window_strategy":          state["import_plan"]["window_strategy"]["strategy"] == "supervised_chapter_batching",
            "char_prompt_variant":      prompts["character"] is exp_char,
            "event_prompt_variant":     prompts["event"] is exp_event,
            "plan_tools_nonempty":      len(state["import_plan"]["tools"]) > 0,
            "all_tools_enabled":        all(t.get("enabled") is True for t in state["import_plan"]["tools"]),
            "safety_gates_set":         (
                state["import_plan"]["safety"].get("proposal_gate_required") is True
                and state["import_plan"]["safety"].get("schema_validated_plan") is True
                and state["import_plan"]["safety"].get("llm_planner_can_propose_only") is True
                and state["import_plan"]["cost_policy"].get("stop_on_api_402") is True
            ),
            "no_api_key_in_artifacts":  all(
                _secret_scan(state[k])
                for k in ("source_profile", "import_plan", "converge_target", "import_granularity_profile")
            ),
            "quality_rubric_no_hard_fail": rubric["verdict"] != "fail",
        }

        passed = all(assertions.values())
        failed_assertions = [k for k, v in assertions.items() if not v]

        results.append({
            "id": case_id,
            "n": n, "lang": lang, "profile": profile,
            "actual": {
                "granularity_profile_name": state["import_granularity_profile"]["profile_name"],
                "source_profile_type": state["source_profile"]["recommended_granularity_profile"],
                "expected_min_characters": state["converge_target"]["expected_min_characters"],
                "char_prompt_constant": manifest["character"]["prompt_constant"],
                "event_prompt_constant": manifest["event"]["prompt_constant"],
            },
            "expected": {
                "granularity_profile_name": exp_gran,
                "source_profile_type": exp_src,
                "expected_min_characters": exp_min_chars,
            },
            "assertions": assertions,
            "failed_assertions": failed_assertions,
            "passed": passed,
            "quality_rubric": rubric,
        })
    return results


def _secret_scan_all(cases):
    patterns_found = []
    for case in cases:
        for key in ("granularity_profile_name", "source_profile_type"):
            text = json.dumps(case.get("actual", {}))
            if _SECRET_RE.search(text):
                patterns_found.append(case["id"])
    return {"passed": len(patterns_found) == 0, "pattern": _SECRET_RE.pattern, "hits": patterns_found}


def _get_git_info() -> dict:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(_REPO), text=True, stderr=subprocess.DEVNULL,
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO), text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return {"branch": branch, "head_commit": commit}
    except Exception:
        return {"branch": None, "head_commit": None}


def _build_metrics(cases, ts: str = None) -> dict:
    if ts is None:
        ts = datetime.now(tz=timezone.utc).isoformat()
    total = len(cases)
    passed_count = sum(1 for c in cases if c["passed"])
    return {
        "harness": "v2_planner_dry_run",
        "harness_schema_version": "1",
        "timestamp": ts,
        "dry_run": True,
        "live_model_calls": False,
        "cases": cases,
        "secret_scan": _secret_scan_all(cases),
        "summary": {"total": total, "passed": passed_count, "failed": total - passed_count},
    }


def _scan_output_file(path: Path) -> list:
    """Scan a generated output file for secrets.

    Lines that document the scan pattern itself ('Pattern checked:' or the JSON
    "pattern" key) are skipped to avoid false positives.
    """
    hits = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _PATTERN_DOC_LINE_RE.search(line):
            continue
        if _SECRET_RE.search(line):
            hits.append(f"{path.name}:{i}")
    return hits


def _scan_output_files(output_dir: Path) -> dict:
    """Post-write secret scan on generated benchmark output files."""
    hits = []
    for fname in ("benchmark_metrics.json", "benchmark_report.md"):
        fpath = output_dir / fname
        if fpath.exists():
            hits.extend(_scan_output_file(fpath))
    return {"passed": len(hits) == 0, "hits": hits}


def _write_reports(metrics: dict, output_dir: Path, json_only: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    git_info = _get_git_info()
    manifest = {
        "harness": "v2_planner_dry_run",
        "harness_schema_version": "1",
        "timestamp": metrics["timestamp"],
        "dry_run": True,
        "branch": git_info["branch"],
        "head_commit": git_info["head_commit"],
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    (output_dir / "benchmark_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
    )
    if json_only:
        return

    cases = metrics["cases"]
    ts = metrics["timestamp"]
    total = metrics["summary"]["total"]
    passed = metrics["summary"]["passed"]
    lines = [
        f"# W1 V2 Planner Dry-Run Report — {ts[:19]}",
        "",
        "Mode: **DRY RUN — no live model calls**",
        "",
        "| Case | n | lang | profile | Granularity | Source Type | Min Chars | Plan OK | Char Prompt | Event Prompt | Status |",
        "|------|---|------|---------|-------------|-------------|-----------|---------|-------------|--------------|--------|",
    ]
    for c in cases:
        a = c["actual"]
        e = c["expected"]
        status = "✅ PASS" if c["passed"] else f"❌ FAIL ({', '.join(c['failed_assertions'])})"
        gran_ok = "✓" if a["granularity_profile_name"] == e["granularity_profile_name"] else f"✗ got {a['granularity_profile_name']}"
        src_ok  = "✓" if a["source_profile_type"] == e["source_profile_type"] else f"✗ got {a['source_profile_type']}"
        mc_ok   = f"{a['expected_min_characters']} {'✓' if a['expected_min_characters'] == e['expected_min_characters'] else '✗'}"
        lines.append(
            f"| {c['id']} | {c['n']} | {c['lang']} | {c['profile']} "
            f"| {gran_ok} | {src_ok} | {mc_ok} "
            f"| {'✓' if c['assertions']['import_plan_valid'] else '✗'} "
            f"| {a['char_prompt_constant']} "
            f"| {a['event_prompt_constant']} "
            f"| {status} |"
        )
    lines += [
        "",
        f"**Summary:** {passed}/{total} passed",
        "",
    ]
    case5 = next((c for c in cases if c["id"] == "case_5_10ch_en_fast"), None)
    if case5:
        lines += [
            "## Case 5 — Fast Profile Divergence",
            "| Field | Value |",
            "|-------|-------|",
            f"| `source_profile.recommended_granularity_profile` | `{case5['actual']['source_profile_type']}` (descriptive) |",
            f"| `import_granularity_profile.profile_name` | `{case5['actual']['granularity_profile_name']}` (execution policy) |",
            "",
            "source_profile reports fine_short_story (≤15 chapters); import_granularity_profile forces coarse_webnovel (fast profile override). This divergence is **intentional**: the profiler is descriptive, the planner is prescriptive.",
            "",
        ]
    lines += [
        "## Secret Scan",
        f"Pattern checked: `{_SECRET_RE.pattern}`",
        f"Result: {'✅ CLEAN' if metrics['secret_scan']['passed'] else '❌ FOUND: ' + str(metrics['secret_scan']['hits'])}",
        "",
        "---",
        "## Gated Live Smoke",
        "Set `LIVE_SMOKE_APPROVED=1` and `DEEPSEEK_API_KEY=<key>` to enable a 10-chapter live run.",
        "This section did **not** run. No API calls were made.",
    ]
    (output_dir / "benchmark_report.md").write_text("\n".join(lines))


def run_gated_live_smoke():
    """Gated live smoke — 10-chapter deep run via sidecar API.

    REQUIREMENTS (all must be set before this section will run):
        LIVE_SMOKE_APPROVED=1   — explicit user approval per session
        DEEPSEEK_API_KEY=<key>  — read from env, never written to disk

    Behavior when enabled:
        - POST to /workflow/w1/start with use_supervisor=True, prompt_profile=deep,
          10-chapter test manuscript, source_language=en
        - Poll /workflow/w1/status every 30s
        - Stop immediately on HTTP 402 (insufficient balance) — do not retry
        - Stop on status=done or status=error
        - Maximum runtime: 30 minutes
        - Write live_smoke_result.json to output_dir

    This function is intentionally left as a documented stub.
    Do NOT implement or enable without explicit user approval.
    Cost: ~$0.10–0.30 per run (DeepSeek V4 Pro, 10-chapter deep).
    """
    if os.environ.get("LIVE_SMOKE_APPROVED") != "1":
        print("[GATED_LIVE_SMOKE] Skipped — set LIVE_SMOKE_APPROVED=1 to enable.")
        return None
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("[GATED_LIVE_SMOKE] Skipped — DEEPSEEK_API_KEY not set.")
        return None

    # Live smoke requires user approval after plan review.
    # Implementation: POST to /workflow/w1/start, poll /workflow/w1/status every 30s,
    # stop on 402 or done/error. Max 30 min. Write live_smoke_result.json.
    # This block is intentionally left as a documented stub — do NOT implement
    # without explicit user approval.
    print("[GATED_LIVE_SMOKE] LIVE_SMOKE_APPROVED is set but live smoke is not yet implemented.")
    print("[GATED_LIVE_SMOKE] Awaiting explicit user approval before this section runs.")
    return None


def main():
    args = _parse_args()

    valid_ids = {c[0] for c in MATRIX}
    if args.case and args.case not in valid_ids:
        print(f"Error: unknown --case '{args.case}'. Valid: {sorted(valid_ids)}", file=sys.stderr)
        return 2

    ts_label = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir if args.output_dir else Path(__file__).parent / "runs" / ts_label

    print(f"W1 V2 Planner Dry-Run Harness — {ts_label}")
    print("Mode: DRY RUN — no live model calls\n")

    matrix = [c for c in MATRIX if args.case is None or c[0] == args.case]
    cases = run_matrix(matrix)
    metrics = _build_metrics(cases)

    for c in cases:
        status = "PASS" if c["passed"] else f"FAIL [{', '.join(c['failed_assertions'])}]"
        print(f"  {c['id']}: {status}")

    total = metrics["summary"]["total"]
    passed = metrics["summary"]["passed"]
    failed = metrics["summary"]["failed"]
    print(f"\nSecret scan: {'CLEAN' if metrics['secret_scan']['passed'] else 'FOUND SECRETS'}")
    print(f"Summary: {passed}/{total} passed\n")

    if not args.no_write:
        _write_reports(metrics, output_dir, json_only=args.json_only)
        scan_result = _scan_output_files(output_dir)
        if not scan_result["passed"]:
            print(f"WARNING: Secret found in output files: {scan_result['hits']}", file=sys.stderr)
        else:
            print("Output file scan: CLEAN")
        print(f"Reports written to: {output_dir}")

    run_gated_live_smoke()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
