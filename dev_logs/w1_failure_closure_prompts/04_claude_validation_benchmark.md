/goal

# Claude D — W1 Failure Closure Benchmark

You are Claude Code working on Narrative IDE.

## Goal
After Codex integrates Claude A/B/C, run objective validation: 10-chapter smoke, then 50-chapter DeepSeek V4 Pro benchmark. Do not change product code.

## Start Condition
Do not run this prompt until Codex explicitly says Stage 2 integration is complete.

## Repo And Branch
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Branch: the integration branch Codex tells you to use, expected `codex/w1-orchestrated-import-quality`
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

## SubAgent Guidance
Do not use Claude subagents for this benchmark. Keep the run single-controller to avoid sidecar/project collisions.

## Run Requirements
- Use real DeepSeek V4 Pro / active DeepSeek profile if available.
- Do not overwrite old benchmark projects.
- Create new timestamped project copies under `/Volumes/migodam's-external-brain/home/narrative_ide/`.
- First run a 10-chapter smoke benchmark.
- If 10-chapter smoke fails to write `manuscript.json` or `system/inbox.json`, stop and report.
- If 10-chapter smoke passes, run 50-chapter benchmark.
- Capture sidecar status, supervisor status, raw logs, copied artifacts, and metrics.

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

## Acceptance Criteria To Evaluate
- 10-chapter smoke writes `manuscript.json` and `system/inbox.json`.
- 50-chapter run does not OOM.
- `language_mismatch=false` or no mixed Chinese/English user-visible fields.
- `character_undercoverage` absent or characters >= 75.
- world entity count clearly below previous 366 unless justified by dedupe report.
- 七玄门 is organization/faction, not character/location.
- manuscript chapters ordered.
- timeline main branch does not regress to sparse state.

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

