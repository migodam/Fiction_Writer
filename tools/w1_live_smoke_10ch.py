#!/usr/bin/env python3
"""Run a gated W1 10-chapter live smoke test.

This runner is intentionally conservative:
- no full50
- no provider key printed
- no live model call unless LIVE_SMOKE_APPROVED=1 and DEEPSEEK_API_KEY is set
- scratch project/output defaults to /tmp so benchmark artifacts are not
  accidentally staged in the repo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE = (
    REPO_ROOT
    / "benchmark_results"
    / "w1_manuscript_smoke_20260526_091106"
    / "smoke_10_chapter"
    / "凡人修仙传_前10章.txt"
)
DEFAULT_OUTPUT_ROOT = Path("/tmp/narrative_ide_w1_live_smoke")
REQUIRED_IMPORT_ARTIFACTS = (
    "manifest.json",
    "prompt_windows.json",
    "evidence_cards.json",
    "cross_validation.json",
    "timeline_architecture.json",
    "review_report.json",
)
_SECRET_VALUE_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})", re.IGNORECASE)
_SECRET_FIELD_NAMES = {"api_key", "apikey", "authorization", "token", "password", "secret"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _ensure_scratch_project(project_path: Path, project_name: str) -> None:
    """Create the minimum canonical folder layout W1 needs for proposals/artifacts."""
    for rel in [
        "system/imports",
        "writing/chapters",
        "writing/scenes",
        "writing/manuscript",
        "characters",
        "timeline",
        "world",
        "graph",
        "scripts",
        "storyboards",
        "schemas",
    ]:
        (project_path / rel).mkdir(parents=True, exist_ok=True)

    project_index = project_path / "project.json"
    if not project_index.exists():
        now = datetime.now(timezone.utc).isoformat()
        _write_json(
            project_index,
            {
                "schemaVersion": 5,
                "metadata": {
                    "schemaVersion": 5,
                    "projectId": f"w1_live_smoke_{project_path.name}",
                    "name": project_name,
                    "rootPath": str(project_path),
                    "storageMode": "nodefs",
                    "locale": "zh-CN",
                    "version": 5,
                    "createdAt": now,
                    "updatedAt": now,
                    "template": "blank",
                    "capabilities": {"import": True, "rag": False, "scripts": False},
                    "storageBackends": {"canonical": "project-folder-json", "rag": "project-folder-keyword-index"},
                    "futureBackends": [],
                },
            },
        )
    _write_json(project_path / "system" / "inbox.json", _read_json(project_path / "system" / "inbox.json", []))
    _write_json(project_path / "system" / "history.json", _read_json(project_path / "system" / "history.json", []))
    _write_json(project_path / "system" / "issues.json", _read_json(project_path / "system" / "issues.json", []))
    _write_json(project_path / "writing" / "manuscript" / "nodes.json", _read_json(project_path / "writing" / "manuscript" / "nodes.json", []))


def _latest_import_dir(project_path: Path) -> Path | None:
    imports_dir = project_path / "system" / "imports"
    if not imports_dir.exists():
        return None
    dirs = [p for p in imports_dir.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def _chapter_number(title: str) -> int | None:
    zh_digits = {
        "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    m = re.search(r"第\s*(\d+)\s*章", title)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*([零一二两三四五六七八九十]+)\s*章", title)
    if not m:
        return None
    text = m.group(1)
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = zh_digits.get(left, 1) if left else 1
        ones = zh_digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return zh_digits.get(text)


def _quality_probe(project_path: Path) -> dict[str, Any]:
    manuscript = _read_json(project_path / "manuscript.json", {})
    chapters = manuscript.get("chapters") if isinstance(manuscript, dict) else []
    if not isinstance(chapters, list):
        chapters = []
    inbox = _read_json(project_path / "system" / "inbox.json", [])
    nodes = _read_json(project_path / "writing" / "manuscript" / "nodes.json", [])
    latest = _latest_import_dir(project_path)
    review_report = _read_json(latest / "review_report.json", {}) if latest else {}
    organizer = _read_json(latest / "organizer_output.json", {}) if latest else {}

    chapter_numbers = [_chapter_number(str(ch.get("title", ""))) for ch in chapters if isinstance(ch, dict)]
    duplicates = sorted({n for n in chapter_numbers if n is not None and chapter_numbers.count(n) > 1})
    blocked = [p for p in inbox if isinstance(p, dict) and (p.get("lastBlockReason") or p.get("requiresManualReview"))]
    empty_branches = []
    timeline = _read_json(latest / "timeline_architecture.json", {}) if latest else {}
    if isinstance(timeline, dict):
        events = timeline.get("canonical_events") or timeline.get("events") or []
        event_branch_ids = {e.get("branchId") or e.get("branch_id") for e in events if isinstance(e, dict)}
        for branch in timeline.get("branches", []) or []:
            if isinstance(branch, dict) and (branch.get("id") or branch.get("branchId")) not in event_branch_ids:
                empty_branches.append(branch.get("id") or branch.get("branchId"))

    return {
        "project_path": str(project_path),
        "latest_import_dir": str(latest) if latest else None,
        "chapter_count": len(chapters) if isinstance(chapters, list) else 0,
        "manuscript_nodes_count": len(nodes) if isinstance(nodes, list) else 0,
        "duplicate_chapter_numbers": duplicates,
        "inbox_count": len(inbox) if isinstance(inbox, list) else 0,
        "blocked_count": len(blocked),
        "empty_branch_ids": empty_branches,
        "review_status": review_report.get("status") if isinstance(review_report, dict) else None,
        "organizer_world_items": len(organizer.get("world_items", [])) if isinstance(organizer, dict) else 0,
        "organizer_excluded_items": len(organizer.get("excluded_items", [])) if isinstance(organizer, dict) else 0,
        "missing_required_artifacts": [
            name for name in REQUIRED_IMPORT_ARTIFACTS if latest is None or not (latest / name).is_file()
        ],
    }


def _quality_probe_failures(probe: dict[str, Any]) -> list[str]:
    """Return smoke-quality failures that should make the runner non-zero.

    This is intentionally conservative: the live-smoke runner is a product gate,
    not a benchmark. A run that completes but produces no visible manuscript,
    duplicate chapters, empty branches, or blocked proposals is not acceptable.
    """
    failures: list[str] = []
    if int(probe.get("chapter_count") or 0) != 10:
        failures.append("chapter_count_not_10")
    if int(probe.get("manuscript_nodes_count") or 0) <= 0:
        failures.append("manuscript_nodes_empty")
    if probe.get("duplicate_chapter_numbers"):
        failures.append("duplicate_chapter_numbers")
    if int(probe.get("blocked_count") or 0) > 0:
        failures.append("blocked_proposals")
    if probe.get("empty_branch_ids"):
        failures.append("empty_timeline_branches")
    if probe.get("review_status") in {"fail", "hard_fail"}:
        failures.append("review_status_failed")
    if probe.get("missing_required_artifacts"):
        failures.append("missing_required_artifacts")
    return failures


def _artifact_secret_leaks(output_dir: Path) -> list[str]:
    """Scan every generated artifact without loading or printing any real key."""
    leaks: list[str] = []
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _SECRET_VALUE_PATTERN.search(text):
            leaks.append(str(path.relative_to(output_dir)))
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        stack = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, child in value.items():
                    is_safe_placeholder = child is None or (isinstance(child, str) and child in {"", "***", "[redacted]"})
                    if key.lower() in _SECRET_FIELD_NAMES and not is_safe_placeholder:
                        leaks.append(str(path.relative_to(output_dir)))
                        stack = []
                        break
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)
    return sorted(set(leaks))


def _smoke_result_exit_code(result: dict[str, Any]) -> int:
    terminal = result.get("terminal", {}) if isinstance(result, dict) else {}
    probe = result.get("quality_probe", {}) if isinstance(result, dict) else {}
    errors = terminal.get("errors") if isinstance(terminal, dict) else None
    status = (
        terminal.get("status")
        or terminal.get("status_text")
        or ("error" if terminal.get("current_node") == "error" or errors else "done")
    )
    converge_status = terminal.get("converge_status")
    if status in {"error", "timeout", "budget_exhausted", "auth_failed"}:
        return 1
    if converge_status in {"hard_fail", "failed"}:
        return 1
    if _quality_probe_failures(probe if isinstance(probe, dict) else {}):
        return 1
    return 0


async def _run_live(args: argparse.Namespace, project_path: Path, output_dir: Path) -> dict[str, Any]:
    from sidecar.workflows.w1_import import run_streaming

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    config = {
        "project_path": str(project_path),
        "source_file_path": str(args.source),
        "import_mode": args.import_mode,
        "prompt_profile": args.prompt_profile,
        "use_supervisor": True,
        "use_orchestrator": True,
        "custom_profile_config": {
            "extract_relationships": args.extract_relationships,
            "extract_world": args.extract_world,
            "extract_timeline": args.extract_timeline,
        },
        "profile_config": {
            "extract_relationships": args.extract_relationships,
            "extract_world": args.extract_world,
            "extract_timeline": args.extract_timeline,
        },
        "budget_policy": {
            "max_cost_usd": args.max_cost_usd,
            "max_input_tokens": args.max_input_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
            "max_calls": args.max_calls,
            "fail_on_unknown_pricing": True,
            "fail_on_missing_usage": True,
        },
        "rerun_cap": 0,
        "max_reruns": 0,
        "context": {
            "api_key": api_key,
            "model": args.model,
            "endpoint": args.endpoint,
            "prompt_profile": args.prompt_profile,
            "use_supervisor": True,
            "use_orchestrator": True,
        },
        "session_id": f"live_smoke_{_timestamp()}",
    }
    safe_config = {**config, "context": {**config["context"], "api_key": "***"}}
    _write_json(output_dir / "run_config.safe.json", safe_config)

    updates: list[dict[str, Any]] = []
    start = time.time()
    terminal: dict[str, Any] = {}
    try:
        async with asyncio.timeout(args.timeout_seconds):
            async for update in run_streaming(str(project_path), config):
                update = dict(update or {})
                updates.append(update)
                _write_json(output_dir / "updates.json", updates)
                errors = " ".join(map(str, update.get("errors", [])))
                print(
                    "[live-smoke]",
                    f"progress={update.get('progress')}",
                    f"node={update.get('current_node') or update.get('current_tool') or '?'}",
                    f"errors={len(update.get('errors', []) or [])}",
                    flush=True,
                )
                if "402" in errors or "budget exhausted" in errors.lower() or "insufficient" in errors.lower():
                    terminal = {"status": "budget_exhausted", "update": update}
                    break
                if any(marker in errors.lower() for marker in ("401", "403", "unauthorized", "authentication", "invalid api key")):
                    terminal = {"status": "auth_failed", "update": update}
                    break
                terminal = update
    except TimeoutError:
        terminal = {"status": "timeout", "elapsed_seconds": int(time.time() - start)}
    except Exception as exc:
        terminal = {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}

    probe = _quality_probe(project_path)
    secret_leaks = _artifact_secret_leaks(output_dir)
    if secret_leaks:
        terminal = {"status": "error", "error": "secret_leakage_detected"}
    result = {
        "elapsed_seconds": int(time.time() - start),
        "terminal": terminal,
        "quality_probe": probe,
        "secret_leak_artifacts": secret_leaks,
    }
    _write_json(output_dir / "final_result.json", result)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gated W1 10-chapter live smoke runner")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--project-path", type=Path, default=None)
    parser.add_argument("--project-name", default="W1 Live Smoke 10 Chapters")
    parser.add_argument("--prompt-profile", default="deep", choices=["fast", "balanced", "deep", "custom"])
    parser.add_argument("--import-mode", default="import_all")
    parser.add_argument("--model", default="deepseek-v4-flash", choices=["deepseek-v4-flash", "deepseek-v4-pro"])
    parser.add_argument("--endpoint", default=os.environ.get("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/v1"))
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-cost-usd", type=float, default=3.0)
    parser.add_argument("--max-input-tokens", type=int, default=1_000_000)
    parser.add_argument("--max-output-tokens", type=int, default=250_000)
    parser.add_argument("--max-total-tokens", type=int, default=1_250_000)
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--extract-relationships", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--extract-world", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--extract-timeline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prepare-only", action="store_true", help="Create scratch project/output dirs and exit without live calls.")
    parser.add_argument("--reuse-project", action="store_true", help="Do not delete an existing scratch project path before running.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.source.exists():
        print(f"ERROR: source file not found: {args.source}", file=sys.stderr)
        return 2

    run_id = _timestamp()
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    project_path = args.project_path or (output_dir / "project")
    if project_path.exists() and not args.reuse_project:
        shutil.rmtree(project_path)
    _ensure_scratch_project(project_path, args.project_name)

    setup = {
        "source": str(args.source),
        "project_path": str(project_path),
        "output_dir": str(output_dir),
        "prompt_profile": args.prompt_profile,
        "model": args.model,
        "endpoint_host": re.sub(r"//.*", "//***", args.endpoint),
        "budget": {
            "max_cost_usd": args.max_cost_usd,
            "max_input_tokens": args.max_input_tokens,
            "max_output_tokens": args.max_output_tokens,
            "max_total_tokens": args.max_total_tokens,
            "max_calls": args.max_calls,
        },
        "rerun_cap": 0,
        "live_smoke_approved": os.environ.get("LIVE_SMOKE_APPROVED") == "1",
        "deepseek_api_key_set": bool(os.environ.get("DEEPSEEK_API_KEY")),
    }
    _write_json(output_dir / "setup.json", setup)
    print(json.dumps(setup, ensure_ascii=False, indent=2))

    if args.prepare_only:
        print("[w1-live-smoke] prepare-only complete; no model calls made.")
        return 0
    if os.environ.get("LIVE_SMOKE_APPROVED") != "1":
        print("[w1-live-smoke] skipped: set LIVE_SMOKE_APPROVED=1 to allow a 10-chapter live model run.")
        return 2
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("[w1-live-smoke] skipped: DEEPSEEK_API_KEY is not set.")
        return 2

    result = asyncio.run(_run_live(args, project_path, output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _smoke_result_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
