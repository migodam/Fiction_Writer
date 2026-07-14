# Reviewer P1 Package Acceptance

## Scope

- Owned: `src/ui-react/services/projectService.ts` and `tests/e2e/p1/workbench_import_package_accept.spec.ts`.
- Preserved concurrent changes in all other files. No store, Electron, or UI changes were made.

## Changes

- Imported `create` operations that collide with an existing canonical ID now block the entire import package instead of being reported as accepted without a write.
- Imported character creates that collide by normalized name or alias now block and require an explicit, proposal-gated `EntityMergeDecision/v1` update. Merge evidence is validated when present; the service no longer selects a longer incoming string over canonical text.
- Package dependency validation runs before mutation. Missing branch/reference edges remain blocking edges and preserve full-package rollback.
- Staged manuscript acceptance now requires readable raw source evidence, validates the manifest source hash and complete `SourceSpan`, and verifies each staged scene document equals the reconstructed raw source substring. Browser-only/no-raw-source acceptance is explicitly blocked.
- Added Playwright coverage for ID collision, semantic character collision, missing branch/reference rollback, and staged content tampering.

## Verification

- PASS: `npm run ui:build`
- PASS: `npx playwright test tests/e2e/p1/workbench_import_package_accept.spec.ts --retries=0` (16/16)
- Adjacent suite: `npx playwright test tests/e2e/p1/workbench_import_package_accept.spec.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts tests/e2e/p1/import_smoke_acceptance.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts --retries=0` (33/34)

## Integration Follow-up

- Lead updated the legacy smoke fixture to expect atomic package blocking for stale branches, duplicate IDs, and semantic character collisions. Canonical chapter and World settings remain unchanged.
- Lead added a named preload SHA-256 capability so SourceSpan verification works with renderer Node access disabled; Electron smoke verifies the known `abc` digest without exposing generic IPC.
- Lead removed the remaining character-reference filtering and timeline branch fallback from imported normalization, and imported character updates now require `EntityMergeDecision/v1` rather than treating missing evidence as valid.
