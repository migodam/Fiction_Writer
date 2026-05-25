/plan

# Claude B — P1 Chinese Language Policy

You are Claude Code working on Narrative IDE.

## Goal
Ensure Chinese source imports produce Chinese user-visible fields and stop failing the W1 `language_mismatch` judge gate.

## First Response Requirement
In `/plan` mode, do not edit files. Produce a concrete implementation plan first. Wait for the user/Codex to approve before `/goal`.

## Repo And Branch
- Repo: `/Volumes/migodam's-external-brain/Development/Narrative_IDE`
- Start from branch: `codex/w1-orchestrated-import-quality`
- Recommended branch/worktree: `codex/w1-closure-p1-language-policy`

## Read First
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
4. `dev_docs/W1_IMPORT_COMPILER.md`
5. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/benchmark_report.md`
6. `benchmark_results/w1_orchestrated_import_quality_20260525_085059/failures_and_followups.md`
7. `sidecar/prompts/w1_prompts.py`
8. `sidecar/supervisor/tools.py`
9. `sidecar/workflows/w1_import.py`
10. `tests/test_w1_supervisor_tools.py`
11. `tests/test_w1_import_compiler.py`

## Owned Scope
- `sidecar/prompts/w1_prompts.py`
- W1 prompt call sites in `sidecar/supervisor/tools.py`
- W1 prompt call sites in `sidecar/workflows/w1_import.py`
- Language-focused W1 tests
- `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
- `dev_docs/W1_IMPORT_COMPILER.md`
- `dev_logs/2026-05-25-w1-closure-p1-language-policy.md`

## Forbidden Scope
- Do not edit proposal-write memory logic.
- Do not edit UI.
- Do not edit world reducer or timeline density logic.
- Do not implement full function-calling/tool-calling migration.
- Do not merge main.
- Do not edit `AGENTS.md` or `CLAUDE.md`.

## SubAgent Guidance
You may use exactly one Claude subagent for prompt consistency review. It should compare all five deep extraction prompts and report missing language policy injection points.

## Implementation Requirements
- Add explicit `{source_language_label}` and `{language_policy}` variables to all five deep extraction prompts:
  - characters
  - events
  - world
  - relationships
  - scene summaries
- Replace vague language rules with explicit output language constraints, e.g. Chinese source -> all user-visible JSON string values must be Chinese unless preserving a source name/code.
- Wire source language and policy through both supervisor path and legacy W1 path.
- Add or improve deterministic post-extraction cleanup for zh source:
  - remove or translate Latin-only `personality_traits`
  - prevent English fallback summaries/stakes/descriptions where source is zh
  - keep enum/internal keys in English where required
- Ensure judge `language_mismatch` can pass when cleanup succeeds.

## Acceptance Tests
Run if feasible:
- `sidecar/.venv/bin/python -m py_compile sidecar/prompts/w1_prompts.py sidecar/supervisor/tools.py sidecar/workflows/w1_import.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_tools.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q`

Add or update tests for:
- prompt formatting includes `source_language_label`
- zh import strips or normalizes English trait strings
- judge language gate no longer fails for cleaned zh character records

## Handoff Format
Final handoff must include:
- Changed files
- Tests run with exact output summary
- Prompt variables added
- Known fields that intentionally remain English because they are enum/internal keys
- Remaining risk for DeepSeek V4 Pro

