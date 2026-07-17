# Benchmark Original Repair-Only Migration - 2026-07-15

## Scope
- Added `tests/electron/w1_original_repair_only.mjs`, a bounded real Electron/UI-service migration runner for the original `w1_reviewer_ready_final_20260714` benchmark.
- Repair-only migration now removes legacy `artifact_path` fields from every
  migrated `operations` and `proposedOperations` descriptor while preserving
  ArtifactRef v2 as the sole path authority.
- The runner only navigates to the original project, clicks the single blocked-package **Repair** control, verifies the resulting valid package, restarts Electron, and exits. It has no acceptance interaction.

## Safety And Evidence
- Requires `benchmark_results/_recovery_backups/20260715_pre_resilience/w1_reviewer_ready_final_20260714` before mutation.
- Removes credential-like environment variables before launching Electron and makes no external API calls.
- Captures pre/post SHA-256 inventories for canonical character, chapter, scene, timeline, world, and manuscript files, plus pre/post inbox and staged-projection hashes.
- Writes the screenshot and JSON receipt only to ignored `benchmark_results/_evidence/20260715_w1_original_repair_only/`.

## Command
```text
node tests/electron/w1_original_repair_only.mjs
```

## Required Assertions
- 89 pending proposals, zero accepted, zero proposal history before and after Repair/restart.
- Canonical content hashes unchanged.
- `source_ref` is present and `source_file_path` absent in the staged projection.
- Real `operations` descriptors use ArtifactRef v2.
- One committed repair transaction targets the staged projection.
- All `lastBlockReason` values clear and explicit Accept is visible but never clicked.

## Repair-Only Migration Fix Verification
- `npm run ui:lint -- --no-fix` passed.
- `npx playwright test tests/e2e/p1/workbench_import_package_accept.spec.ts --grep "repairs a blocked stale legacy package"` passed (1 test).
- `node tests/electron/w1_original_repair_only.mjs` passed against the restored original backup baseline and restarted cleanly.
- Result: 89 pending, 0 accepted, 0 history; legacy absolute paths removed; ArtifactRef v2 present; canonical inventory hashes unchanged.
- Receipt: `benchmark_results/_evidence/20260715_w1_original_repair_only/repair-only-receipt.json`.
