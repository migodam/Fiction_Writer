"""
W1 Orchestrated Import Quality V2 Benchmark Runner
Branch: codex/w1-orchestrated-import-quality
Timestamp: 20260525_083823

Usage:
    python run_benchmark.py

Reads run_config.json in the same directory.
Writes all output under raw_logs/, copied_artifacts/, and root report files.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).parent
RUN_CONFIG = json.loads((SCRIPT_DIR / "run_config.json").read_text())
SIDECAR_URL = RUN_CONFIG["sidecar_url"]
POLL_INTERVAL = 30
TIMEOUT_SECONDS = 7200

BENCH_PROJECT = RUN_CONFIG["project_path"]
SOURCE_FILE = RUN_CONFIG["source_file_path"]
RESULTS_DIR = SCRIPT_DIR

SIDECAR_ROOT = pathlib.Path("/Volumes/migodam's-external-brain/Development/Narrative_IDE")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _dump(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Step 3: Health check / sidecar start ─────────────────────────────────────

def ensure_sidecar() -> None:
    print("Checking sidecar health …")
    for _ in range(3):
        try:
            _get(f"{SIDECAR_URL}/health")
            print("  Sidecar already up.")
            return
        except Exception:
            pass
        time.sleep(3)

    print("  Starting sidecar …")
    subprocess.Popen(
        [str(SIDECAR_ROOT / "sidecar/.venv/bin/python"), "-m", "uvicorn",
         "sidecar.main:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=str(SIDECAR_ROOT),
        stdout=open(str(RESULTS_DIR / "raw_logs/sidecar_stdout.txt"), "w"),
        stderr=open(str(RESULTS_DIR / "raw_logs/sidecar_stderr.txt"), "w"),
    )
    for i in range(15):
        time.sleep(1)
        try:
            _get(f"{SIDECAR_URL}/health")
            print(f"  Sidecar up after {i+1}s.")
            return
        except Exception:
            pass
    raise RuntimeError("Sidecar did not start within 15s")


# ── Step 4: Start import and poll ─────────────────────────────────────────────

def run_import() -> dict:
    api_key = RUN_CONFIG.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("ERROR: DEEPSEEK_API_KEY not set and not in run_config.json")

    payload = {
        "project_path": BENCH_PROJECT,
        "source_file_path": SOURCE_FILE,
        "import_mode": RUN_CONFIG["import_mode"],
        "prompt_profile": RUN_CONFIG["prompt_profile"],
        "model": RUN_CONFIG["model"],
        "endpoint": RUN_CONFIG["endpoint"],
        "use_supervisor": RUN_CONFIG["use_supervisor"],
        "use_orchestrator": RUN_CONFIG["use_orchestrator"],
        "api_key": api_key,
    }

    print(f"\nPOSTing to {SIDECAR_URL}/workflow/w1/start …")
    resp = _post(f"{SIDECAR_URL}/workflow/w1/start", payload)
    session_id = resp["session_id"]
    print(f"  session_id: {session_id}")
    _dump(RESULTS_DIR / "raw_logs/start_response.json", resp)

    start_time = time.time()
    poll_n = 0
    final_status: dict = {}

    while True:
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT_SECONDS:
            print(f"\nTIMEOUT after {_fmt(elapsed)}")
            final_status["timeout"] = True
            final_status["duration_seconds"] = elapsed
            break

        time.sleep(POLL_INTERVAL)
        poll_n += 1

        try:
            status = _get(f"{SIDECAR_URL}/workflow/w1/status?session_id={session_id}")
            _dump(RESULTS_DIR / f"raw_logs/poll_{poll_n:04d}.json", status)
        except Exception as exc:
            print(f"  poll #{poll_n} error: {exc}")
            continue

        try:
            sup_status = _get(f"{SIDECAR_URL}/workflow/w1/supervisor_status?session_id={session_id}")
            _dump(RESULTS_DIR / f"raw_logs/supervisor_poll_{poll_n:04d}.json", sup_status)
        except Exception:
            sup_status = {}

        phase = status.get("orchestrator_phase", "")
        tool = status.get("current_tool", "")
        judge_score = status.get("judge_score")
        converge = status.get("converge_status", "")
        progress = status.get("progress", 0.0)

        print(
            f"[{_fmt(elapsed)}] poll #{poll_n}: "
            f"status={status.get('status')} progress={progress:.0%} "
            f"phase={phase!r} tool={tool!r} "
            f"judge={judge_score} converge={converge!r}"
        )

        run_status = status.get("status", "")
        if run_status in ("done", "error", "cancelled"):
            final_status = {**status, "duration_seconds": elapsed, "session_id": session_id}
            break

    _dump(RESULTS_DIR / "raw_logs/final_status.json", final_status)
    print(f"\nImport finished: status={final_status.get('status')} duration={_fmt(final_status.get('duration_seconds', 0))}")
    return final_status


# ── Step 5: Collect artifacts ──────────────────────────────────────────────────

def collect_artifacts() -> tuple[str, dict]:
    imports_dir = pathlib.Path(BENCH_PROJECT) / "system" / "imports"
    import_run_id = ""
    if imports_dir.exists():
        dirs = sorted(imports_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if dirs:
            import_run_id = dirs[0].name

    print(f"\nimport_run_id: {import_run_id!r}")
    artifact_dir = imports_dir / import_run_id if import_run_id else pathlib.Path("/dev/null/missing")

    FILES = {
        "manifest.json":             artifact_dir / "manifest.json",
        "prompt_windows.json":       artifact_dir / "prompt_windows.json",
        "tool_operating_spec.json":  artifact_dir / "tool_operating_spec.json",
        "judge_artifact.json":       artifact_dir / "judge_artifact.json",
        "supervisor_decisions.json": artifact_dir / "supervisor_decisions.json",
        "window_metrics.json":       artifact_dir / "window_metrics.json",
        "cross_validation.json":     artifact_dir / "cross_validation.json",
        "timeline_architecture.json":artifact_dir / "timeline_architecture.json",
        "review_report.json":        artifact_dir / "review_report.json",
        "inbox.json":                pathlib.Path(BENCH_PROJECT) / "system" / "inbox.json",
        "manuscript.json":           pathlib.Path(BENCH_PROJECT) / "manuscript.json",
    }

    artifact_index = {"import_run_id": import_run_id, "files": {}}
    out_dir = RESULTS_DIR / "copied_artifacts"

    for name, src in FILES.items():
        exists = src.exists()
        size = src.stat().st_size if exists else 0
        artifact_index["files"][name] = {"source": str(src), "exists": exists, "size_bytes": size}
        if exists:
            shutil.copy2(src, out_dir / name)
            print(f"  copied {name} ({size:,} bytes)")
        else:
            print(f"  MISSING {name}")

    _dump(RESULTS_DIR / "artifact_index.json", artifact_index)
    return import_run_id, artifact_index


# ── Step 6: Diagnostics ───────────────────────────────────────────────────────

def run_diagnostics(import_run_id: str) -> int:
    if not import_run_id:
        print("\nSkipping diagnostics — no import_run_id")
        return -1

    diag_py = SIDECAR_ROOT / "tools/w1_import_diagnostics.py"
    if not diag_py.exists():
        print(f"\nDiagnostics tool not found at {diag_py}")
        return -1

    log_path = RESULTS_DIR / "raw_logs/diagnostics_output.txt"
    print(f"\nRunning diagnostics → {log_path}")
    result = subprocess.run(
        [str(SIDECAR_ROOT / "sidecar/.venv/bin/python"), str(diag_py),
         BENCH_PROJECT, "--import-run-id", import_run_id, "--format", "both"],
        capture_output=True, text=True,
    )
    log_path.write_text(result.stdout + "\n--- STDERR ---\n" + result.stderr)
    print(f"  diagnostics exit code: {result.returncode}")
    return result.returncode


# ── Step 7: Analyze artifacts ─────────────────────────────────────────────────

def load_artifact(name: str) -> dict | list:
    p = RESULTS_DIR / "copied_artifacts" / name
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _has_latin(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]{4,}", str(s)))


def analyze(final_status: dict, import_run_id: str) -> dict:
    inbox = load_artifact("inbox.json")
    manuscript = load_artifact("manuscript.json")
    timeline_arch = load_artifact("timeline_architecture.json")
    judge_artifact = load_artifact("judge_artifact.json")
    cross_val = load_artifact("cross_validation.json")

    proposals = inbox if isinstance(inbox, list) else inbox.get("proposals", [])

    # ── Characters ───────────────────────────────────────────────────────────
    char_proposals = [p for p in proposals if p.get("type") == "character"]
    char_count = len(char_proposals)

    key_chars = {"韩立": False, "墨大夫": False, "厉飞雨": False, "张铁": False}
    org_in_chars: list[str] = []
    mixed_fields: list[str] = []

    groupkey_dist: dict[str, int] = {}
    for cp in char_proposals:
        data = cp.get("data", cp)
        name = data.get("name", "") or data.get("name_cn", "")
        for k in key_chars:
            if k in str(name) or k in str(data.get("aliases", "")):
                key_chars[k] = True
        imp = str(data.get("importance", "")).lower()
        role = str(data.get("role_in_story", "")).lower()
        if imp == "organization" or "organization" in role or "门" in role:
            org_in_chars.append(name)
        gk = data.get("groupKey", "unknown")
        groupkey_dist[gk] = groupkey_dist.get(gk, 0) + 1
        for field_name in ("name", "aliases", "summary", "personality_traits"):
            val = data.get(field_name, "")
            for item in (val if isinstance(val, list) else [val]):
                if _has_latin(str(item)):
                    mixed_fields.append(f"{name}.{field_name}={str(item)[:40]}")
                    break

    # ── Timeline ─────────────────────────────────────────────────────────────
    ta = timeline_arch if isinstance(timeline_arch, dict) else {}
    branches = ta.get("branches", ta.get("branch_list", []))
    canonical_events = ta.get("canonical_events", [])
    discarded = ta.get("discarded_duplicates", ta.get("discard_log", []))
    branch_count = len(branches)
    canonical_event_count = len(canonical_events)
    discarded_count = len(discarded)

    main_branch_id = ""
    for b in branches:
        bid = b.get("branchId") or b.get("id", "")
        if "main" in bid.lower() or b.get("parentBranchId") is None:
            main_branch_id = bid
            break

    main_events = [e for e in canonical_events if e.get("branchId") == main_branch_id or e.get("branch") == main_branch_id]
    side_events = [e for e in canonical_events if e not in main_events]
    main_event_count = len(main_events)
    side_event_count = len(side_events)

    # ── World ─────────────────────────────────────────────────────────────────
    container_proposals = [p for p in proposals if p.get("type") in ("world_container", "worldContainer")]
    item_proposals      = [p for p in proposals if p.get("type") in ("world_item", "worldItem")]

    containers_by_cat: dict[str, int] = {}
    for cp in container_proposals:
        d = cp.get("data", cp)
        cat = d.get("category", d.get("type", "unknown"))
        containers_by_cat[cat] = containers_by_cat.get(cat, 0) + 1

    items_by_cat: dict[str, int] = {}
    for ip in item_proposals:
        d = ip.get("data", ip)
        cat = d.get("category", d.get("type", "unknown"))
        items_by_cat[cat] = items_by_cat.get(cat, 0) + 1

    qixuanmen_category = ""
    for p in proposals:
        d = p.get("data", p)
        nm = str(d.get("name", "")) + str(d.get("name_cn", ""))
        if "七玄门" in nm:
            qixuanmen_category = d.get("category", p.get("type", "unknown"))
            break

    # ── Chapters/manuscript ───────────────────────────────────────────────────
    if isinstance(manuscript, dict):
        chapters = manuscript.get("chapters", [])
    else:
        chapters = []
    chapter_count = len(chapters)
    orders = [c.get("order", c.get("index", c.get("chapterNumber", None))) for c in chapters]
    numeric_orders = [o for o in orders if isinstance(o, (int, float))]
    chapters_ordered = numeric_orders == sorted(numeric_orders) if numeric_orders else None
    manuscript_preserved = all(bool(c.get("content") or c.get("sourceText") or c.get("text") or c.get("source_text")) for c in chapters) if chapters else False

    # ── Judge ─────────────────────────────────────────────────────────────────
    ja = judge_artifact if isinstance(judge_artifact, dict) else {}
    judge_score = ja.get("score", final_status.get("judge_score"))
    judge_passed = ja.get("passed", False)
    failed_gates = ja.get("failed_gates", [])
    thematic_reruns = ja.get("thematic_rerun_requests", [])
    converge_status = ja.get("converge_status", final_status.get("converge_status", ""))
    judge_iteration = ja.get("iteration", 0)

    # ── Language ─────────────────────────────────────────────────────────────
    source_lang = "zh"

    # ── Previous failure comparison ──────────────────────────────────────────
    def symptom(label: str, current, old_val, fixed_thresh, improved_thresh, *, higher_is_better: bool = True) -> str:
        if current is None:
            return "unknown"
        if higher_is_better:
            if current >= fixed_thresh:
                return "fixed"
            if current >= improved_thresh:
                return "improved"
            return "still_failing"
        else:
            if current <= fixed_thresh:
                return "fixed"
            if current <= improved_thresh:
                return "improved"
            return "still_failing"

    prev_comparison = {
        "character_count": symptom("chars", char_count, 20, 5),
        "timeline_density": symptom("events", main_event_count, 10, 4),
        "chapter_order": ("fixed" if chapters_ordered else "still_failing") if chapters_ordered is not None else "unknown",
        "language_consistency": "fixed" if not mixed_fields else "still_failing",
        "world_routing": symptom("containers", len(container_proposals), 3, 2),
    }

    metrics = {
        "status": "pass" if judge_passed else ("warning" if judge_score and judge_score >= 6 else "fail"),
        "project_path": BENCH_PROJECT,
        "source_path": SOURCE_FILE,
        "import_run_id": import_run_id,
        "duration_seconds": round(final_status.get("duration_seconds", 0), 1),
        "chapters": {
            "count": chapter_count,
            "ordered": chapters_ordered,
            "manuscript_preserved": manuscript_preserved,
        },
        "characters": {
            "count": char_count,
            "key_presence": key_chars,
            "organizations_in_characters": org_in_chars,
            "groupkey_distribution": groupkey_dist,
        },
        "world": {
            "containers": containers_by_cat,
            "items_by_category": items_by_cat,
            "qixuanmen_category": qixuanmen_category,
        },
        "timeline": {
            "branch_count": branch_count,
            "canonical_event_count": canonical_event_count,
            "main_branch_event_count": main_event_count,
            "side_branch_event_count": side_event_count,
            "discarded_duplicate_count": discarded_count,
        },
        "language": {
            "source_language": source_lang,
            "mixed_user_visible_fields": mixed_fields[:20],
        },
        "judge": {
            "score": judge_score,
            "passed": judge_passed,
            "failed_gates": failed_gates,
            "thematic_rerun_requests": [r.get("theme", r) if isinstance(r, dict) else r for r in thematic_reruns],
            "converge_status": converge_status,
            "iteration": judge_iteration,
        },
        "previous_failure_comparison": prev_comparison,
    }
    return metrics


# ── Step 8: Write reports ─────────────────────────────────────────────────────

def write_report(metrics: dict, final_status: dict) -> None:
    m = metrics
    dur = _fmt(m["duration_seconds"])
    status_emoji = {"pass": "PASS", "warning": "WARNING", "fail": "FAIL"}.get(m["status"], m["status"].upper())
    prev = m["previous_failure_comparison"]
    judge = m["judge"]
    chars = m["characters"]
    tl = m["timeline"]
    world = m["world"]
    chap = m["chapters"]
    lang = m["language"]

    def sym(v: str) -> str:
        return {"fixed": "[FIXED]", "improved": "[IMPROVED]", "still_failing": "[STILL FAILING]", "unknown": "[UNKNOWN]"}.get(v, v)

    report = f"""# W1 Orchestrated Import Quality V2 Benchmark Report

**Status:** {status_emoji}
**Run Timestamp:** {RUN_CONFIG['timestamp']}
**Branch:** {RUN_CONFIG['branch']}
**Duration:** {dur}

---

## Executive Summary

W1 orchestrated import (`use_supervisor=true`, `use_orchestrator=true`, `prompt_profile=deep`)
completed against the first-50-chapter Chinese novel fixture (凡人修仙传).

- **Characters extracted:** {chars['count']}
- **Canonical timeline events:** {tl['canonical_event_count']} ({tl['main_branch_event_count']} main branch)
- **World containers:** {sum(world['containers'].values())}
- **Chapters in manuscript:** {chap['count']}
- **Judge score:** {judge['score']} | Passed: {judge['passed']}
- **Converge status:** {judge['converge_status']}

---

## Run Configuration

| Field | Value |
|-------|-------|
| Source file | `凡人修仙传_前50章.txt` (first 50 chapters) |
| Import mode | `import_all` |
| Prompt profile | `deep` |
| Model | `deepseek-chat` (DeepSeek V4 Pro) |
| use_supervisor | true |
| use_orchestrator | true |
| Sidecar URL | {RUN_CONFIG['sidecar_url']} |
| Branch | {RUN_CONFIG['branch']} |
| Project path | `{m['project_path']}` |

---

## Artifact Paths

| Artifact | Path |
|----------|------|
| Import run ID | `{m['import_run_id']}` |
| Benchmark project | `{m['project_path']}` |
| Results dir | `{str(RESULTS_DIR)}` |
| Artifacts dir | `{str(RESULTS_DIR / 'copied_artifacts')}` |

---

## Metrics Table

| Metric | Value |
|--------|-------|
| Duration | {dur} |
| Chapters | {chap['count']} |
| Chapters ordered | {chap['ordered']} |
| Manuscript preserved | {chap['manuscript_preserved']} |
| Character proposals | {chars['count']} |
| 韩立 present | {chars['key_presence'].get('韩立', False)} |
| 墨大夫 present | {chars['key_presence'].get('墨大夫', False)} |
| 厉飞雨 present | {chars['key_presence'].get('厉飞雨', False)} |
| 张铁 present | {chars['key_presence'].get('张铁', False)} |
| Orgs in characters | {chars['organizations_in_characters']} |
| Timeline branches | {tl['branch_count']} |
| Canonical events | {tl['canonical_event_count']} |
| Main branch events | {tl['main_branch_event_count']} |
| Side branch events | {tl['side_branch_event_count']} |
| Discarded duplicates | {tl['discarded_duplicate_count']} |
| World containers | {sum(world['containers'].values())} |
| World items | {sum(world['items_by_category'].values())} |
| 七玄门 category | `{world['qixuanmen_category']}` |
| Mixed lang fields | {len(lang['mixed_user_visible_fields'])} |
| Judge score | {judge['score']} |
| Judge passed | {judge['passed']} |
| Converge status | {judge['converge_status']} |

---

## Previous Failure Comparison

| Symptom | Previous | Current | Status |
|---------|----------|---------|--------|
| Character count (≥20=fixed) | 4 | {chars['count']} | {sym(prev['character_count'])} |
| Timeline density (≥10 main=fixed) | 3 events | {tl['main_branch_event_count']} main | {sym(prev['timeline_density'])} |
| Chapter order | Out of order | ordered={chap['ordered']} | {sym(prev['chapter_order'])} |
| Language consistency | Mixed Eng/Zh | {len(lang['mixed_user_visible_fields'])} mixed fields | {sym(prev['language_consistency'])} |
| World routing (≥3 containers=fixed) | 1 collapsed | {sum(world['containers'].values())} containers | {sym(prev['world_routing'])} |

---

## Judge Artifact Summary

- **Score:** {judge['score']}
- **Passed:** {judge['passed']}
- **Failed gates:** {judge['failed_gates']}
- **Thematic rerun requests:** {judge['thematic_rerun_requests']}
- **Converge status:** {judge['converge_status']}
- **Iteration:** {judge['iteration']}

---

## Timeline Quality Analysis

- **Branch count:** {tl['branch_count']}
- **Canonical events:** {tl['canonical_event_count']}
- **Main branch:** {tl['main_branch_event_count']} events
- **Side branches:** {tl['side_branch_event_count']} events
- **Discarded duplicates:** {tl['discarded_duplicate_count']}

---

## Character Extraction Analysis

- **Total proposals:** {chars['count']}
- **Key characters:**
  - 韩立 (Han Li / protagonist): {chars['key_presence'].get('韩立', False)}
  - 墨大夫 (Mo Dafu): {chars['key_presence'].get('墨大夫', False)}
  - 厉飞雨 (Li Feiyu): {chars['key_presence'].get('厉飞雨', False)}
  - 张铁 (Zhang Tie): {chars['key_presence'].get('张铁', False)}
- **GroupKey distribution:** {chars['groupkey_distribution']}
- **Organizations mis-routed as characters:** {chars['organizations_in_characters']}

---

## World Ontology Analysis

- **Containers by category:** {world['containers']}
- **Items by category:** {world['items_by_category']}
- **七玄门 (Qi Xuan Sect) category:** `{world['qixuanmen_category']}`
  (Expected: organization/faction; must NOT be location or character)

---

## Chapter/Manuscript Preservation Analysis

- **Chapter count:** {chap['count']} (expected ≤50)
- **Sequential ordering:** {chap['ordered']}
- **Source text preserved per chapter:** {chap['manuscript_preserved']}

---

## Language Consistency

- **Source language:** Chinese (zh)
- **Mixed-language user-visible fields detected:** {len(lang['mixed_user_visible_fields'])}
{chr(10).join(f'  - {f}' for f in lang['mixed_user_visible_fields'][:10]) if lang['mixed_user_visible_fields'] else '  (none)'}

---

## Residual Risks

- If judge score < 8: thematic reruns may not have converged; check `judge_artifact.json` for unfixed gates.
- If missing key characters: check `cross_validation.json` for `missing_major_characters`.
- If world containers < 3: world routing still collapsing; check `tool_operating_spec.json` for `world_boundary_mode`.
- If mixed language fields > 0: language normalization not fully applied; check prompt profile overrides.

---

## Recommended Next Fixes

See `failures_and_followups.md` for the full prioritized list.
"""

    (RESULTS_DIR / "benchmark_report.md").write_text(report, encoding="utf-8")
    print("\nbenchmark_report.md written")


def write_followups(metrics: dict) -> None:
    prev = metrics["previous_failure_comparison"]
    lines = ["# Failures and Follow-ups\n"]
    for symptom_key, status in prev.items():
        if status in ("still_failing", "unknown"):
            lines.append(f"## {symptom_key}: {status.upper()}\n")
            if symptom_key == "character_count":
                lines.append("- Increase `min_characters_per_chapter` in ToolOperatingSpec\n")
                lines.append("- Check if judge thematic reruns targeted `character_undercoverage`\n")
            elif symptom_key == "timeline_density":
                lines.append("- Increase `event_density_target` in ToolOperatingSpec\n")
                lines.append("- Check if main branch is over-pruned by Timeline Architect\n")
            elif symptom_key == "chapter_order":
                lines.append("- Check `node_split_chunks` ordering; verify `prompt_windows.json` chunk order\n")
            elif symptom_key == "language_consistency":
                lines.append("- Add explicit Chinese-output constraint to character extraction prompts\n")
                lines.append("- Check if language normalization step fires for `source_language=zh`\n")
            elif symptom_key == "world_routing":
                lines.append("- Check `world_boundary_mode` in ToolOperatingSpec (should separate org/location)\n")
                lines.append("- Verify `_normalize_world_category` is classifying 七玄门 as organization\n")
    if not any(v in ("still_failing", "unknown") for v in prev.values()):
        lines.append("All previous failure symptoms resolved.\n")
    (RESULTS_DIR / "failures_and_followups.md").write_text("\n".join(lines), encoding="utf-8")
    print("failures_and_followups.md written")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("W1 Orchestrated Import Quality V2 Benchmark")
    print(f"Timestamp: {RUN_CONFIG['timestamp']}")
    print(f"Branch:    {RUN_CONFIG['branch']}")
    print(f"Source:    {SOURCE_FILE}")
    print(f"Project:   {BENCH_PROJECT}")
    print("=" * 70)

    # Step 3
    ensure_sidecar()

    # Step 4
    final_status = run_import()

    # Step 5
    import_run_id, artifact_index = collect_artifacts()

    # Step 6
    run_diagnostics(import_run_id)

    # Step 7
    metrics = analyze(final_status, import_run_id)
    _dump(RESULTS_DIR / "benchmark_metrics.json", metrics)
    print(f"\nbenchmark_metrics.json written")

    # Step 8
    write_report(metrics, final_status)
    write_followups(metrics)

    print("\n" + "=" * 70)
    print(f"BENCHMARK COMPLETE — status={metrics['status'].upper()}")
    print(f"Duration:   {_fmt(metrics['duration_seconds'])}")
    print(f"Characters: {metrics['characters']['count']}")
    print(f"Events:     {metrics['timeline']['canonical_event_count']} canonical ({metrics['timeline']['main_branch_event_count']} main)")
    print(f"Chapters:   {metrics['chapters']['count']}")
    print(f"Judge:      score={metrics['judge']['score']} passed={metrics['judge']['passed']}")
    print(f"Results:    {RESULTS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
