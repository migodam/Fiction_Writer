# W1 Supervisor Manuscript Fix

Date: 2026-05-26
Branch: `codex/w1-orchestrated-import-quality`

## Context

Claude D benchmark `benchmark_results/w1_failure_closure_20260526_011743/` closed the major W1 quality failures for character extraction, language consistency, world routing, timeline density, and proposal-write survival. Validation exposed one blocking regression: both smoke and 50-chapter supervisor imports wrote `manuscript.json` with an empty `chapters` array.

## Root Cause

`node_build_manuscript()` built import-all manuscripts from `state["chunk_extractions"]`. The supervisor path extracts by prompt window and does not produce per-chunk extraction records, while the deterministic source chapters remain available in `state["chunks"]`.

## Change

- Added a deterministic raw-chunk fallback in `node_build_manuscript()` for `import_all` runs with no `chunk_extractions`.
- Preserved existing legacy behavior when per-chunk extraction records exist.
- Added a regression test proving unordered raw chunks are written as ordered manuscript chapters.

## Verification

- `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py::test_build_manuscript_orders_chapters_by_source_chunk_id tests/test_w1_import_compiler.py::test_build_manuscript_supervisor_falls_back_to_chunks_without_extractions tests/test_w1_import_compiler.py::test_node_write_to_project_manuscript_still_written -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_supervisor_policy.py tests/test_w1_supervisor_tools.py tests/test_w1_prompt_windows.py -q`
- `npm run ui:build`

