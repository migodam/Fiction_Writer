#!/usr/bin/env python3
"""
W1 Failure Closure Benchmark Runner
Run: sidecar/.venv/bin/python benchmark_results/w1_failure_closure_20260526_011743/run_benchmark.py [smoke|full]
API key is read from DEEPSEEK_API_KEY env var or app settings — never written to disk.
"""
import argparse
import json
import os
import sys
import time
import pathlib
import requests
import traceback

SIDECAR_URL = "http://127.0.0.1:8765"
TS = "20260526_011743"
RESULTS_DIR = pathlib.Path(f"/Volumes/migodam's-external-brain/Development/Narrative_IDE/benchmark_results/w1_failure_closure_{TS}")
HOME_NI = pathlib.Path("/Volumes/migodam's-external-brain/home/narrative_ide")

SMOKE_SOURCE = str(RESULTS_DIR / "smoke_10_chapter" / "凡人修仙传_前10章.txt")
FULL_SOURCE = str(HOME_NI / "novels" / "凡人修仙传_前50章.txt")

SMOKE_PROJECT = str(HOME_NI / f"w1_failure_closure_smoke_{TS}")
FULL_PROJECT = str(HOME_NI / f"w1_failure_closure_50ch_{TS}")


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    settings_path = pathlib.Path.home() / "Library/Application Support/fiction-writer-ide/narrative-ide-app-settings.json"
    if settings_path.exists():
        d = json.loads(settings_path.read_text())
        for p in d.get("providerProfiles", []):
            k = p.get("apiKey", "").strip()
            if k:
                return k
    raise RuntimeError("No API key found in DEEPSEEK_API_KEY env or app settings")


def poll_run(session_id: str, log_prefix: str, timeout_s: int = 7200) -> dict:
    start = time.time()
    n = 0
    last_status = {}
    while True:
        elapsed = time.time() - start
        if elapsed > timeout_s:
            print(f"[{log_prefix}] TIMEOUT after {elapsed:.0f}s")
            return {**last_status, "run_status": "timeout", "elapsed_s": elapsed}

        try:
            r = requests.get(f"{SIDECAR_URL}/workflow/w1/status", params={"session_id": session_id}, timeout=30)
            status = r.json()
        except Exception as e:
            print(f"[{log_prefix}] poll error: {e}")
            time.sleep(15)
            continue

        n += 1
        log_path = RESULTS_DIR / "raw_logs" / f"{log_prefix}_poll_{n:04d}.json"
        log_path.write_text(json.dumps(status, ensure_ascii=False, indent=2))

        try:
            sup = requests.get(f"{SIDECAR_URL}/workflow/w1/supervisor_status", params={"session_id": session_id}, timeout=30)
            sup_data = sup.json()
            sup_log = RESULTS_DIR / "raw_logs" / f"{log_prefix}_supervisor_{n:04d}.json"
            sup_log.write_text(json.dumps(sup_data, ensure_ascii=False, indent=2))
        except Exception:
            sup_data = {}

        progress = status.get("progress", 0)
        current_tool = status.get("current_tool", "")
        phase = sup_data.get("orchestrator_phase", "")
        judge_score = sup_data.get("judge_score", "")
        run_status = status.get("status", "")

        print(f"[{log_prefix}] t={elapsed:.0f}s poll={n} status={run_status} progress={progress:.0%} tool={current_tool} phase={phase} judge={judge_score}")

        last_status = status

        if run_status in ("done", "error"):
            (RESULTS_DIR / "raw_logs" / f"{log_prefix}_final.json").write_text(
                json.dumps(status, ensure_ascii=False, indent=2)
            )
            elapsed_final = time.time() - start
            return {**status, "run_status": run_status, "elapsed_s": elapsed_final}

        time.sleep(30)


def start_run(project_path: str, source_path: str, label: str) -> str:
    api_key = get_api_key()
    payload = {
        "project_path": project_path,
        "source_file_path": source_path,
        "import_mode": "import_all",
        "prompt_profile": "deep",
        "model": "deepseek-v4-pro",
        "endpoint": "https://api.deepseek.com/v1",
        "api_key": api_key,
        "use_supervisor": True,
        "use_orchestrator": True,
        "sidecar_url": SIDECAR_URL,
    }
    r = requests.post(f"{SIDECAR_URL}/workflow/w1/start", json=payload, timeout=30)
    r.raise_for_status()
    resp = r.json()
    session_id = resp.get("session_id", "")
    print(f"[{label}] started session_id={session_id}")
    (RESULTS_DIR / "raw_logs" / f"{label}_start.json").write_text(
        json.dumps(resp, ensure_ascii=False, indent=2)
    )
    # Write run_config WITHOUT the api_key
    cfg = {k: v for k, v in payload.items() if k != "api_key"}
    cfg["timestamp"] = TS
    cfg["branch"] = "codex/w1-orchestrated-import-quality"
    cfg["session_id"] = session_id
    (RESULTS_DIR / "run_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    return session_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["smoke", "full"])
    args = parser.parse_args()

    if args.mode == "smoke":
        session_id = start_run(SMOKE_PROJECT, SMOKE_SOURCE, "smoke")
        result = poll_run(session_id, "smoke", timeout_s=3600)
        print("SMOKE RESULT:", json.dumps({k: v for k, v in result.items() if k != "state"}, indent=2))
    else:
        session_id = start_run(FULL_PROJECT, FULL_SOURCE, "full50")
        result = poll_run(session_id, "full50", timeout_s=10800)
        print("FULL RESULT:", json.dumps({k: v for k, v in result.items() if k != "state"}, indent=2))
