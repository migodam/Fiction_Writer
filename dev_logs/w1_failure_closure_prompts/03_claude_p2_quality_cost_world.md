/plan

# Claude C — P2/P3 Quality, World Dedup, Token Cost

You are Claude Code working on Narrative IDE.

## Goal
Reduce world entity inflation, reduce token/memory cost, and prevent late-window character undercoverage without rewriting the whole orchestrator.

## First Response Requirement
In `/plan` mode, do not edit files. Produce a concrete implementation plan first. Wait for the user/Codex to approve before `/goal`.

## Repo And Branch
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Start from branch: `codex/w1-orchestrated-import-quality`
- Recommended branch/worktree: `codex/w1-closure-p2-quality-cost`

## Read First
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
4. `dev_docs/W1_IMPORT_COMPILER.md`
5. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_report.md`
6. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/failures_and_followups.md`
7. `sidecar/models/state.py`
8. `sidecar/supervisor/policy.py`
9. `sidecar/supervisor/tools.py`
10. `sidecar/supervisor/tool_registry.py`
11. `sidecar/workflows/w1_import.py`
12. `sidecar/prompts/w1_prompts.py`
13. W1 tests under `tests/`

## Owned Scope
- `sidecar/models/state.py`
- `sidecar/supervisor/policy.py`
- `sidecar/supervisor/tools.py`
- `sidecar/supervisor/tool_registry.py`
- `sidecar/workflows/w1_import.py`
- `sidecar/prompts/w1_prompts.py` only for world `dedupeKey` schema alignment
- W1-focused Python tests
- `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
- `dev_docs/W1_IMPORT_COMPILER.md`
- `dev_logs/2026-05-25-w1-closure-p2-quality-cost.md`

## Forbidden Scope
- Do not edit UI.
- Do not touch proposal-write batching owned by Claude A.
- Do not touch language prompt policy owned by Claude B except avoiding conflicts.
- Do not implement full function-calling/tool-calling migration.
- Do not merge main.
- Do not edit `AGENTS.md` or `CLAUDE.md`.

## SubAgent Guidance
You may use up to two Claude subagents:
- Subagent 1: read-only world dedup and ontology reducer review.
- Subagent 2: read-only window/rerun/token-cost review.

## Implementation Requirements
- Add `max_world_entities_per_chapter` or equivalent soft parameter to TOS.
- Add world `dedupeKey` to prompt/schema expectations and deterministic fallback if model omits it.
- Add `reduce_world_entities` or equivalent deterministic reducer to collapse duplicate world entries across windows.
- Keep `七玄门` and similar names routed to organization/faction.
- Reduce world entity inflation from benchmark scale, targeting clearly below 366 for 50 chapters.
- Improve extraction failure handling so one failed character/event/world prompt is not silently converted to `{}` without rerun/metrics.
- Adjust deep late-window policy so dense late chapters use smaller windows, preferably 3-6 chapters depending on source density.
- Keep token cost down by compacting registry summaries and not feeding excessive world entries back into every prompt.

## Acceptance Tests
Run if feasible:
- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/supervisor/policy.py sidecar/supervisor/tools.py sidecar/supervisor/tool_registry.py sidecar/workflows/w1_import.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_prompt_windows.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q`

Add or update tests for:
- world dedupe by normalized name/category/dedupeKey
- world cap enforced by chapter count
- failed extraction prompt creates failed metric/rerun trigger
- late windows use smaller chapter cap
- 七玄门 remains organization/faction

## Handoff Format
Final handoff must include:
- Changed files
- Tests run with exact output summary
- Expected world entity reduction strategy
- Token-cost impact
- Any residual risk for real DeepSeek benchmark

