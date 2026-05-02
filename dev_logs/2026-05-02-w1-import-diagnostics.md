# 2026-05-02 W1 Import Diagnostics

## Scope
- Added diagnostics-only tooling for W1 import acceptance review.
- Stayed outside W1 runtime, prompt, UI, and Import_Test6 fixture files.

## Changes
- Added `tools/w1_import_diagnostics.py` for single-run and comparison metrics.
- Added synthetic pytest coverage in `tests/test_w1_import_diagnostics.py`.
- Documented direct command usage in `dev_docs/W1_IMPORT_COMPILER.md`.

## Verification
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_diagnostics.py` -> passed, 3 tests.
- `python3 -m py_compile tools/w1_import_diagnostics.py tests/test_w1_import_diagnostics.py` -> passed.
- Import_Test6 baseline generated with `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python tools/w1_import_diagnostics.py "/Volumes/migodam's-external-brain/home/narrative_ide/Import_Test6" --import-run-id import_90542398fded --format markdown`.
- The worktree-local `sidecar/.venv/bin/python` path is absent; the shared main-checkout sidecar venv was used from this worktree.
