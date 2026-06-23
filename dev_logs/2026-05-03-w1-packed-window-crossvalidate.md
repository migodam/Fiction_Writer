# 2026-05-03 — W1 Packed Window Cross-Validation

## Goal
Upgrade W1 import from one-chapter prompt windows to packed chapter windows that target the 256k total input budget for `deep`/`custom`, while preserving complete chapters and feeding rolling cross-validation into subsequent windows.

## Changes
- Added packed prompt-window budget metadata and multi-chapter window construction.
- Added window-level prompt cache contract for packed windows.
- Wired cross-validation into the W1 scout loop after each packed window.
- Preserved manuscript chapter outputs by creating covered-chapter extraction records for every chunk represented by a packed window.
- Deepened W1 prompts to explicitly use `PROJECT_STRUCTURE_DIGEST` and `PREVIOUS_VALIDATION_SUMMARY` inside packed windows.

## Tests
- `sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py` — passed, 20 tests.
- `npm run ui:lint` — passed.
- `npm run ui:build` — passed.
- `npm run sidecar:test` — W1 tests passed, but the full suite still fails in legacy `src/core` memory/settings/timeline tests unrelated to W1 import.
