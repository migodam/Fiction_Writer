# W1 World Container Reference Hotfix

## Incident

The reviewer-ready 10-chapter import package could not be accepted. Every generated `world_item` referenced an Organizer container such as `world_container_organizations`, while the staged package only contained fallback containers such as `cont_import_organizations`.

## Root Cause

- Both supervisor execution paths copied Organizer world items into `entity_registry` but dropped `organizer_output.world_containers`.
- Proposal writing then supplied default `cont_import_*` containers.
- Stale `world_detailed.containerId` and `parentId` values overrode the writer's semantic container resolution, creating dangling package dependencies.
- A failed atomic accept annotated every proposal in the package with the same `lastBlockReason`, so repairing only the culprit left a stale blocked package card.

## Fix

- Propagate Organizer containers through both supervisor paths.
- At the proposal boundary, accept explicit World parent IDs only when they exist in the emitted container set; otherwise rebind by normalized semantic category.
- Extend W1 diagnostics with hard failures for dangling World container references and pending proposals that retain block markers.
- Repair the ignored reviewer-ready artifact deterministically without another API call. The original inbox was backed up to `/tmp/w1-inbox-before-world-container-fix-20260714.json`.

## Verification

- `158 passed`: supervisor policy, import compiler, organizer, semantic quality, and diagnostics suites.
- `npm run ui:build`: passed.
- `npm run ui:lint`: passed.
- `22 passed`: `tests/e2e/p1/workbench_import_package_accept.spec.ts` with a live Vite server.
- `tools/w1_import_diagnostics.py --fail-on-threshold`: all flags false for `benchmark_results/w1_reviewer_ready_final_20260714`; dangling references `48 -> 0`, stale block markers `65 -> 0`.
- No paid DeepSeek call was made.

## Residual Note

The first Playwright invocation did not start Vite and produced only `ERR_CONNECTION_REFUSED`; it was stopped and rerun against `http://localhost:3000`, where all 22 tests passed.
