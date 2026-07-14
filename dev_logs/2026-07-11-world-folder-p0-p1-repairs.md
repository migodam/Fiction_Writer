# World Folder P0/P1 Repairs

## Findings
- `tag_hierarchy_drag_drop` expected the hidden virtual `世界模型` root to render. The current Folder UI intentionally promotes its children, so the assertion was stale rather than a product defect.
- World folder rename was a product defect: the editable input was nested in the focus-restored container button. Closing the context menu refocused that button, triggering the input blur and unmounting it during `fill`.

## Changes
- Render folder rename input outside the interactive container button, preserving the current Folder labels and context-menu entry point.
- Update P0 rename coverage to assert the committed name is rendered.
- Update P1 hierarchy coverage to assert the virtual root is hidden and its Folder descendants remain visible.

## Verification
- `npx playwright test --config tests/playwright.config.ts tests/e2e/p0/graph_crud.spec.ts tests/e2e/p1/tag_hierarchy_drag_drop.spec.ts --workers=1 --retries=0 --reporter=line` — 8 passed.
- `npm run ui:lint` — passed.
- `npm run ui:build` — passed (existing Vite chunk-size warning only).
- `git diff --check` — passed.
