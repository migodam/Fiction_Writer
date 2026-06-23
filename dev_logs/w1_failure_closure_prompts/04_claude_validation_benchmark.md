/goal

# Claude D — W1 Failure Closure Benchmark

You are Claude Code working on Narrative IDE.

## Goal
After Codex integrates Claude A/B/C, run objective validation: 10-chapter smoke, then 50-chapter DeepSeek V4 Pro benchmark. Do not change product code.

## Start Condition
Do not run this prompt until Codex explicitly says Stage 2 integration is complete.
Stage 2 is complete when the current branch is `codex/w1-orchestrated-import-quality` and contains commit `b76b2ef` or a later descendant.

## Repo And Branch
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Branch: `codex/w1-orchestrated-import-quality`
- Expected integrated commit: `b76b2ef` or later
- Output directory pattern: `benchmark_results/w1_failure_closure_YYYYMMDD_HHMMSS/`

## Read First
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
4. `dev_docs/W1_IMPORT_COMPILER.md`
5. Previous benchmark:
   - `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_report.md`
   - `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_metrics.json`
   - `benchmark_results/w1_orchestrated_import_quality_20260525_085059/failures_and_followups.md`

## Owned Scope
- `benchmark_results/w1_failure_closure_YYYYMMDD_HHMMSS/`
- Optional benchmark helper scripts inside that benchmark directory only
- `dev_logs/2026-05-25-w1-closure-validation-benchmark.md`

## Forbidden Scope
- Do not edit product source code.
- Do not edit prompts.
- Do not edit UI.
- Do not edit DevDocs except the validation dev log.
- Do not merge main.
- Do not commit API keys or write API keys into `run_config.json`, logs, reports, copied artifacts, or dev logs.
- Do not reuse or overwrite previous benchmark project directories.

## SubAgent Guidance
Do not use Claude subagents for this benchmark. Keep the run single-controller to avoid sidecar/project collisions.

## Run Requirements
- Use real DeepSeek V4 Pro / active DeepSeek profile if available.
- Read the API key from `DEEPSEEK_API_KEY` or the existing app settings path only. If a copied historical `run_config.json` contains an `api_key` field, remove it before running and redact it from any copied output.
- Do not overwrite old benchmark projects.
- Create new timestamped project copies under `/Volumes/migodam's-external-brain/home/narrative_ide/`.
- First run a 10-chapter smoke benchmark.
- If 10-chapter smoke fails to write `manuscript.json` or `system/inbox.json`, stop and report.
- If 10-chapter smoke passes, run 50-chapter benchmark.
- Capture sidecar status, supervisor status, raw logs, copied artifacts, and metrics.
- Before running model calls, run the local sanity commands below. If they fail, stop and report the failure instead of spending model tokens:
  - `sidecar/.venv/bin/python -m py_compile sidecar/prompts/w1_prompts.py sidecar/supervisor/tools.py sidecar/workflows/w1_import.py sidecar/models/state.py sidecar/supervisor/policy.py sidecar/supervisor/tool_registry.py`
  - `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_prompt_windows.py -q`
  - `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q`

## Suggested Implementation Path
1. Confirm branch and commit:
   - `git status --short --branch`
   - `git rev-parse --short HEAD`
   - `git merge-base --is-ancestor b76b2ef HEAD`
2. Create a timestamp:
   - `YYYYMMDD_HHMMSS`
3. Create result directory:
   - `benchmark_results/w1_failure_closure_YYYYMMDD_HHMMSS/`
4. Copy the previous runner as a starting point if useful:
   - source: `benchmark_results/w1_orchestrated_import_quality_20260525_085059/run_benchmark.py`
   - target: new benchmark directory
   - remove any hardcoded key handling from copied config
5. Create two benchmark project paths:
   - smoke: `/Volumes/migodam's-external-brain/home/narrative_ide/w1_failure_closure_smoke_YYYYMMDD_HHMMSS`
   - full: `/Volumes/migodam's-external-brain/home/narrative_ide/w1_failure_closure_50ch_YYYYMMDD_HHMMSS`
6. Use source file:
   - `/Volumes/migodam's-external-brain/home/narrative_ide/novels/凡人修仙传_前50章.txt`
7. For the 10-chapter smoke, create a temporary 10-chapter source copy inside the benchmark result directory. Prefer deterministic chapter-boundary truncation over character truncation.
8. Run smoke first. Stop if it fails to write both `manuscript.json` and `system/inbox.json`.
9. Run 50-chapter only after smoke passes.
10. Run diagnostics and produce the required output files.

## Required Output Files
Inside `benchmark_results/w1_failure_closure_YYYYMMDD_HHMMSS/`:
- `benchmark_report.md`
- `benchmark_metrics.json`
- `run_config.json`
- `artifact_index.json`
- `failures_and_followups.md`
- `raw_logs/`
- `copied_artifacts/`
- `smoke_10_chapter/` or equivalent smoke output

## Metrics Required
`benchmark_metrics.json` must include:
- run status and duration
- source path and benchmark project path
- import_run_id
- whether `manuscript.json` exists
- chapter count, order, manuscript preservation
- whether `system/inbox.json` exists
- character count and key presence for 韩立、墨大夫、厉飞雨、张铁
- organizations incorrectly in character registry
- world entity count, items by category, 七玄门 category
- timeline branch count, canonical events, main branch events, side branch events, discarded duplicates
- language mismatch fields
- judge score, passed, failed gates, thematic rerun requests, converge status
- comparison against previous benchmark symptoms
- current branch and commit
- whether local sanity commands passed before model calls
- whether any secret-like strings were detected in the benchmark output directory

## Acceptance Criteria To Evaluate
- 10-chapter smoke writes `manuscript.json` and `system/inbox.json`.
- 50-chapter run does not OOM.
- `language_mismatch=false` or no mixed Chinese/English user-visible fields.
- `character_undercoverage` absent or characters >= 75.
- world entity count clearly below previous 366 unless justified by dedupe report.
- 七玄门 is organization/faction, not character/location.
- manuscript chapters ordered.
- timeline main branch does not regress to sparse state.
- no API key or secret-like string appears in the generated benchmark result directory.

## Secret Hygiene Check
Before final handoff, scan the benchmark output directory for obvious secrets and redact if necessary:
- `rg -n "sk-[A-Za-z0-9_-]{16,}|DEEPSEEK_API_KEY|api_key" benchmark_results/w1_failure_closure_YYYYMMDD_HHMMSS`

If this finds a real key, remove/redact the file before handoff and mention the redaction.

## Handoff Format
Final handoff must include:
- Benchmark result directory
- Status: pass/warning/fail
- 10-chapter smoke result
- 50-chapter result
- Key metrics
- Blockers
- Files created
- Whether Codex should analyze benchmark next
