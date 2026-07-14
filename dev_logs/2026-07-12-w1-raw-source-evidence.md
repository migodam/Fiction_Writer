# W1 Raw Source Evidence Closure

## Scope

- Owned: `sidecar/workflows/w1_import.py` and `tests/test_w1_import_compiler.py`.
- Preserved concurrent changes in all other files. No UI, Electron, or bridge files were changed.

## Changes

- Before proposal writes, W1 now copies the submitted raw source bytes to `system/imports/<import_run_id>/raw_source.txt`.
- The copy uses a same-directory temporary file, `fsync`, and `os.replace` for atomic publication.
- Evidence is immutable for a run: repeat writes may reuse identical bytes, while different bytes hard-fail without replacing the recorded source.
- Both staged manuscript projection writes and their import notes now point to the project-local evidence path. The in-memory source text remains unchanged, so manifest hashes and `SourceSpan` values retain their original source basis.
- Missing original source files hard-fail before any proposal write.

## Verification

- PASS: `sidecar/.venv/bin/pytest -q tests/test_w1_import_compiler.py` (`68 passed`)
- PASS: `sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py`
- PASS: `git diff --check`
