# W1 Extraction Variant Dispatch

## Summary
- Wired supervisor `extract_window` to select character, event, world, and relationship prompt variants from `state["import_granularity_profile"]`.
- Preserved the old runtime behavior when `import_granularity_profile` is missing, `None`, or partially populated.
- Left `W1_EXTRACT_SCENE_SUMMARIES` unchanged; scene summaries do not dispatch by granularity.

## Files
- `sidecar/supervisor/tools.py`
  - Added variant prompt imports.
  - Added lookup tables and `_select_extraction_prompts()`.
  - Updated the extraction gather call to use selected prompt templates for four domains.
- `tests/test_w1_extraction_variants.py`
  - Added helper dispatch tests.
  - Added mocked `extract_window` tests proving old fallback and webnovel variant selection.
- `dev_docs/W1_IMPORT_COMPILER.md`
  - Documented supervisor-only extraction granularity dispatch.
- `dev_docs/W1_AGENTIC_IMPORT_SUPERVISOR.md`
  - Documented `import_granularity_profile` field-to-variant mapping.

## Validation
- `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/tools.py`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_extraction_variants.py -q`
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_supervisor_tools.py tests/test_w1_prompt_windows.py -q`

## Notes
- This is the dispatch layer only. Policy still needs to populate `import_granularity_profile` before extraction for the variants to take effect automatically.
- No model calls or full-50 benchmark were run.
