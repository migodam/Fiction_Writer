# W1 Proposal Graph Closure

## Incident

Workbench blocked the preserved 10-chapter package because three character proposals referenced `event_c17b6a40`, while no timeline-event proposal produced that ID. Timeline Architect had retained the event; a second fuzzy-title dedupe inside proposal writing discarded it without an ID remap.

## Changes

- Removed the second event identity/dedupe pass from proposal writing.
- Rebuilt character event backlinks only from final Timeline Architect events.
- Added a typed proposal graph compiler with explicit remaps, reference closure, Tarjan SCC analysis, deterministic Kahn ordering, optional-edge normalization, and fail-closed package rollback.
- Tightened frontend package validation: only creates produce IDs; timeline topology references are validated.
- Added generic dangling proposal-reference diagnostics.
- Recompiled the preserved inbox without an API call, removed three stale optional backlinks, and cleared 89 stale block markers.

## Verification

- `sidecar/.venv/bin/python -m pytest tests/test_w1*.py -q`: 677 passed.
- `npm run ui:build`: passed; known large-bundle warning only.
- `npm run ui:lint`: passed.
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_import_package_accept.spec.ts`: 24 passed.
- `npm run electron:smoke`: assertions passed; expected forced-close cleanup fallback.
- Real artifact diagnostics with `--fail-on-threshold`: exit 0; all flags false.
- Full Playwright: 238 passed, 12 legacy `tests/e2e/smoke.spec.ts` failures caused by removed selectors/routes; no failure is in the W1/package acceptance surface.
