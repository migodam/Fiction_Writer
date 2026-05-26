# W1 Granularity + Extraction Variant Validation

## Summary
- Validated Claude A's granularity foundation commit on `codex/w1-granularity-orchestrator`.
- Validated Claude B's B1 extraction prompt variant constants with zero runtime dispatch changes.
- Added this log to document the validation scope and test evidence.

## Claude A Scope
- `sidecar/models/state.py`
  - Extended `ImportGranularityProfile` with extraction dispatch fields.
  - Added `import_granularity_profile` to `ImportSupervisorState`.
  - Added `select_granularity_profile()`.
  - Extended `plan_converge_target()` with optional `granularity_profile`.
- `tests/test_w1_granularity.py`
  - Added profile selection and adaptive converge target coverage.

## Claude B Scope
- `sidecar/prompts/w1_prompts.py`
  - Added 12 inert prompt variant constants:
    - characters: webnovel, balanced, fine
    - events: arc, chapter, dense
    - world: sparse, structural, lore
    - relationships: core, recurring, dense
  - Existing runtime prompt constants remain untouched.
- `tests/test_w1_extraction_variants.py`
  - Added string-level regression checks for old constants and new variant policies.

## Validation
- `sidecar/.venv/bin/python -m py_compile sidecar/models/state.py sidecar/prompts/w1_prompts.py sidecar/supervisor/tools.py sidecar/supervisor/policy.py` — pass
- `sidecar/.venv/bin/python -m pytest tests/test_w1_granularity.py tests/test_w1_extraction_variants.py -q` — 53 passed
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_supervisor_tools.py tests/test_w1_supervisor_policy.py tests/test_w1_prompt_windows.py -q` — 127 passed
- Prompt format smoke check for all 12 new variant constants — pass

## Notes
- B1 intentionally does not wire dispatch. Runtime still uses the existing prompt constants.
- The next safe step is B2 dispatch via `import_granularity_profile`, followed by policy integration that stores the selected profile before extraction.
