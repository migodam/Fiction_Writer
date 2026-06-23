# 2026-05-24 W1 Orchestrated Import Quality V2 — Worker A

Branch: `codex/w1-orchestrated-import-quality-worker-a`

## Scope
- Owned sidecar orchestration/state/test layer for W1.
- Did not edit `src/ui-react/*`.
- Did not implement timeline/world ontology mappings owned by Worker B.
- Did not run real DeepSeek import.

## Changes
- Added typed `ToolOperatingSpec`, `ConvergeTarget`, `JudgeArtifact`, and `ThematicRerunRequest` interfaces.
- Added deterministic planner helpers for profile/source-language/chapter-count-derived orchestration targets.
- Routed Deep/Custom streaming imports to the supervisor path by default unless `use_supervisor` is explicitly false.
- Replaced supervisor window gate density thresholds with active ToolOperatingSpec values.
- Added deterministic `judge_import` tool and bounded thematic rerun loop for character, timeline, world-boundary, and language mismatch themes.
- Added status fields: `current_tool`, `current_window`, `chapter_range`, `orchestrator_phase`, `judge_score`, `rerun_reason`, `converge_status`.
- Added artifact writes for `judge_artifact.json` and `tool_operating_spec.json`.
- Updated W1 supervisor docs for the new judge/orchestrator interfaces.

## Verification
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py -q` passed: 38 passed.
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_prompt_windows.py -q` passed: 51 passed.
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q` passed on final rerun: 29 passed.

## Residual Risks
- The thematic rerun loop is deterministic scaffolding. It delegates extraction quality to existing `rerun_window` and validator stages.
- Real DeepSeek import was intentionally not run per task constraints.
- Earlier compiler/diagnostics validation briefly exposed Worker B-owned ontology/timeline failures, but the final rerun passed after concurrent working-tree updates.
