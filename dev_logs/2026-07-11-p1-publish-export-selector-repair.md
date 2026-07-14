# P1 Publish Export Selector Repair

Date: 2026-07-11
Owner: Publish P1

## Root Cause

Commit `26f4aeb` replaced the separate `publish-export-markdown` and
`publish-export-html` commands with a format selector plus the shared
`publish-export-action` command. The export service and artifact history were
still functional, but `world_map_publish.spec.ts` retained the removed button
selectors.

## Changes

- Added stable selectors for Markdown and HTML format selection.
- Updated the P1 flow to export Markdown, then HTML, through the current UI.
- Asserted that both generated artifact types appear in Publish history.

## Verification

- Passed: `npx playwright test --config=tests/playwright.config.ts tests/e2e/p1/world_map_publish.spec.ts --retries=0`
  - 1 passed; Markdown and HTML artifacts both appeared in Publish history.
- Passed: `npm run ui:build`
  - TypeScript and Vite production build completed successfully.
