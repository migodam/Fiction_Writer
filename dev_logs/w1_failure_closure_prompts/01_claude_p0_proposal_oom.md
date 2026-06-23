/plan

# Claude A — P0 Proposal OOM / Write Stability

You are Claude Code working on Narrative IDE.

## Goal
Make W1 50-chapter orchestrated import complete without dying during `proposal_write`, while preserving proposal gatekeeping and manuscript output.

## First Response Requirement
In `/plan` mode, do not edit files. Produce a concrete implementation plan first. Wait for the user/Codex to approve before `/goal`.

## Repo And Branch
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Start from branch: `codex/w1-orchestrated-import-quality`
- Recommended branch/worktree: `codex/w1-closure-p0-proposal-oom`

## Read First
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
4. `dev_docs/W1_IMPORT_COMPILER.md`
5. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_report.md`
6. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/failures_and_followups.md`
7. `sidecar/workflows/w1_import.py`
8. `sidecar/supervisor/tools.py`
9. `tests/test_w1_import_compiler.py`
10. `tests/test_w1_supervisor_tools.py`

## Owned Scope
- `sidecar/workflows/w1_import.py`
- `sidecar/supervisor/tools.py` only if needed for artifact write timing or state slimming
- W1-focused Python tests
- `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
- `dev_docs/W1_IMPORT_COMPILER.md`
- `dev_logs/2026-05-25-w1-closure-p0-proposal-oom.md`

## Forbidden Scope
- Do not edit prompts.
- Do not edit UI.
- Do not redesign timeline algorithms.
- Do not implement full function-calling/tool-calling migration.
- Do not merge main.
- Do not edit `AGENTS.md` or `CLAUDE.md`.

## SubAgent Guidance
You may use exactly one Claude subagent in `/plan` or `/goal` mode for memory/state-size review. The subagent must be read-only unless you explicitly own the file it wants to edit.

## Implementation Requirements
- Fix `proposal_write` memory pressure by writing proposals in bounded batches or streaming receipts.
- Avoid retaining unnecessary full payload lists once proposals are persisted.
- Ensure `manuscript.json` still writes after proposal generation.
- Ensure `supervisor_decisions.json`, `window_metrics.json`, `cross_validation.json`, and `judge_artifact.json` are written before or during final stages so a late crash still leaves diagnostics.
- Preserve proposal gatekeeping: AI-originated data must still go through inbox/proposal flow, not direct canonical mutation.
- Keep final return state compact enough for router/status polling.
- Add instrumentation or logs that make proposal-write progress visible.

## Acceptance Tests
Run if feasible:
- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/supervisor/tools.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_tools.py -q`

Add or update tests for:
- proposal writing in batches
- diagnostics artifacts written before final proposal completion
- manuscript write still occurs
- no canonical direct write bypass

## Handoff Format
Final handoff must include:
- Changed files
- Tests run with exact output summary
- Memory/OOM mitigation summary
- Any remaining risk for 50-chapter benchmark
- Whether Claude D benchmark can be run after integration

