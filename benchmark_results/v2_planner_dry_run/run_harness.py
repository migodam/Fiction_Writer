#!/usr/bin/env python3
"""W1 V2 Planner Dry-Run Validation Harness.

Runs the 5-case zero-cost matrix against the deterministic V2 orchestrator
planner chain and writes a machine-readable JSON report + markdown summary.

Usage:
    python benchmark_results/v2_planner_dry_run/run_harness.py

No API key required. No live model calls. Safe to re-run at any time.

Exit codes:
    0  All cases PASS
    1  One or more cases FAIL

Gated live smoke (10-ch deep run):
    Set LIVE_SMOKE_APPROVED=1 and DEEPSEEK_API_KEY=<key> to enable.
    This section will NOT run unless both are set.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path so sidecar imports work from any CWD
_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "sidecar"))

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

# Matrix: (id, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars)
MATRIX = [
    ("case_1_10ch_zh_deep",     10, "zh", "deep",     "fine_short_story", "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_FINE,     W1_EXTRACT_EVENTS_DEEP_DENSE,   15),
    ("case_2_50ch_zh_deep",     50, "zh", "deep",     "coarse_webnovel",  "coarse_webnovel",  W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 50),
    ("case_3_40ch_en_deep",     40, "en", "deep",     "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 40),
    ("case_4_20ch_en_balanced", 20, "en", "balanced", "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 24),
    ("case_5_10ch_en_fast",     10, "en", "fast",     "coarse_webnovel",  "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_ARC,      5),
]


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


def run_matrix():
    results = []
    for case_id, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars in MATRIX:
        state = _build_state(n, lang, profile)
        prompts = _select_extraction_prompts(state)
        manifest = _selected_extraction_prompt_manifest(state)

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


def _write_reports(cases, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).isoformat()
    total = len(cases)
    passed = sum(1 for c in cases if c["passed"])
    failed = total - passed

    metrics = {
        "harness": "v2_planner_dry_run",
        "timestamp": ts,
        "dry_run": True,
        "live_model_calls": False,
        "cases": cases,
        "secret_scan": _secret_scan_all(cases),
        "summary": {"total": total, "passed": passed, "failed": failed},
    }
    (output_dir / "benchmark_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
    )

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
        "## Case 5 — Fast Profile Divergence",
        "| Field | Value |",
        "|-------|-------|",
        f"| `source_profile.recommended_granularity_profile` | `{cases[4]['actual']['source_profile_type']}` (descriptive) |",
        f"| `import_granularity_profile.profile_name` | `{cases[4]['actual']['granularity_profile_name']}` (execution policy) |",
        "",
        "source_profile reports fine_short_story (≤15 chapters); import_granularity_profile forces coarse_webnovel (fast profile override). This divergence is **intentional**: the profiler is descriptive, the planner is prescriptive.",
        "",
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
    return metrics


def run_gated_live_smoke():
    """Gated live smoke — 10-chapter deep run via sidecar API.

    REQUIREMENTS (both must be set):
        LIVE_SMOKE_APPROVED=1
        DEEPSEEK_API_KEY=<key>

    This function reads the API key from env and never writes it to disk.
    It stops immediately on HTTP 402 (insufficient balance).
    Maximum runtime: 30 minutes.
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
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent / "runs" / ts

    print(f"W1 V2 Planner Dry-Run Harness — {ts}")
    print("Mode: DRY RUN — no live model calls\n")

    cases = run_matrix()
    metrics = _write_reports(cases, output_dir)

    for c in cases:
        status = "PASS" if c["passed"] else f"FAIL [{', '.join(c['failed_assertions'])}]"
        print(f"  {c['id']}: {status}")

    total = metrics["summary"]["total"]
    passed = metrics["summary"]["passed"]
    failed = metrics["summary"]["failed"]
    print(f"\nSecret scan: {'CLEAN' if metrics['secret_scan']['passed'] else 'FOUND SECRETS'}")
    print(f"Summary: {passed}/{total} passed\n")
    print(f"Reports written to: {output_dir}")

    run_gated_live_smoke()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
