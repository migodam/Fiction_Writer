# W1 Import + Timeline Wave 1 Integration

Date: 2026-05-02
Branch: `codex/w1-import-timeline-integration`
Baseline: `codex/w1-industrial-baseline` at `4ae0657`

## Merge Order

1. `codex/w1-import-diagnostics`
2. `codex/w1-context-windowing`
3. `codex/w1-prompt-crossvalidate`

## Integrated Scope

- Added W1 import diagnostics tooling and synthetic tests.
- Added chapter-aware prompt windows with project structure digest artifacts.
- Added industrial W1 prompt contracts and `CrossValidationArtifact`.
- Kept UI, package scripts, and Import_Test6 project data untouched.

## Verification

- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_diagnostics.py` passed after diagnostics merge.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py` passed after context-windowing merge: `11 passed`.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_import_diagnostics.py` passed after prompt-crossvalidation merge: `15 passed`.
- `/Volumes/migodam's-external-brain/Development/Narrative_IDE/sidecar/.venv/bin/python -m py_compile sidecar/workflows/w1_import.py sidecar/models/state.py sidecar/prompts/w1_prompts.py tools/w1_import_diagnostics.py` passed.

## Import_Test6 Baseline Diagnostics

Command:

```bash
python3 tools/w1_import_diagnostics.py /Volumes/migodam\'s-external-brain/home/narrative_ide/Import_Test6 --format both
```

Key baseline symptoms:

- Inbox proposals: `188`
- Review report proposal total: `972`
- Character records analyzed: `41`
- Character summary outliers: `14`, max length `2065`
- Timeline branches: `7`
- Canonical timeline events: `132`
- Over-budget branches: `branch_main=77`, `branch_import_conflict=32`
- Duplicate event clusters: `14`
- Mainline density: `77` events, `0.5833` share

## Known Baseline Caveat

The broad `npm run sidecar:test` command is not currently a clean W1 signal because legacy `src.core.persistence.ProjectMemory` tests fail on pre-existing API drift. W1-targeted sidecar tests are green and are the merge gate for this wave unless the legacy test scope is explicitly reopened.
