# 2026-07-25 W1 Package Compiler Import Repair

## Scope

- Audited the official public Claude Code repository for reusable Harness
  patterns without copying proprietary implementation.
- Repaired W1 package graph compilation, persistence, acceptance ordering, and
  attempt-aware legacy projection migration.
- Recompiled and accepted the existing `Import Text 18` package.

## Root Cause

- Python persisted a dependency order that React ignored.
- Producer IDs were derived differently in Python and TypeScript.
- Partial package selection could bypass the package transaction.
- Legacy artifact repair looked only in the run root, not the attempt directory.
- The semantic re-review tool wrote pre-compile proposals back to Inbox.

## Implementation

- Added package graph contract `w1-package-graph-v2`.
- Persisted compiler order and execution plan on normalized proposals.
- Unified producer ID precedence:
  `operation.entityId -> operation.fields.id -> proposal.targetEntityId`.
- Blocked conflicting explicit producer IDs.
- Made React validation and apply consume one authoritative order.
- Added deterministic compatibility topological ordering for legacy packages.
- Blocked incomplete package acceptance.
- Added attempt-aware projection discovery and relative ArtifactRef migration.
- Made the re-review transaction persist compiler-normalized proposals.
- Added a real Electron acceptance/restart harness:
  `npm run electron:w1-package-compiler`.

## Real Project

- Backup:
  `/Volumes/migodam's-external-brain/home/narrative_ide/import_test18.backup-before-package-compiler-20260725`
- Migration receipt:
  `system/migrations/w1-pending-semantic-rereview/20260724T183027560043Z`
- Result:
  `/tmp/narrative-ide-import-compiler-result-1784917866491/result.json`
- Accepted: 108 proposals.
- Final: 0 pending, 10 chapters, 10 scenes, 20 manuscript nodes.
- Restart persistence: passed.
- Provider calls/cost: 0 / $0.

## Tests

- `pytest -q tests/test_w1_proposal_graph.py tests/test_w1_rereview_pending_package_semantics.py tests/test_w1_import_compiler.py`
  - 99 passed.
- `playwright test tests/e2e/p1/workbench_import_package_accept.spec.ts`
  - 34 passed after post-review metadata hardening.
- `npm run electron:w1-package-compiler`
  - disposable copy passed.
- `NARRATIVE_IDE_IMPORT_IN_PLACE=1 npm run electron:w1-package-compiler`
  - original project passed and persisted after restart.
- UI lint/build:
  - passed before final documentation update.

## Final Release Gate

- W1/runtime targeted pytest: 805 passed.
- Full browser P0/P1/smoke Playwright: 279 passed.
- UI lint: passed.
- UI production build: passed, with the existing large-bundle warning.
- Electron runtime smoke: passed.
- `git diff --check`: passed.
- New Electron harness syntax check: passed.
- Changed-file credential scan: no matches.
- Independent low-cost SubAgent review: recorded in the completion summary.
