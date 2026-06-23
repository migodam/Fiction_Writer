# 2026-05-02 Wave 2C Timeline Interaction

## Scope
- Worktree: `.worktrees/timeline-interaction-v2`
- Branch: `codex/timeline-interaction-v2`
- Owned UI surface: `TimelineCanvas` timeline branch editing ergonomics.

## Changes
- Added branch segment drag overlays so users can move a curve segment without grabbing an endpoint.
- Added visible middle and Bezier control handles with stable `data-testid` selectors.
- Preserved endpoint anchor editing and added grid snapping when endpoints are not snapped to event targets.
- Added modifier-key behavior:
  - `Alt/Option` on a branch segment adjusts/inserts the practical middle control point within the current `geometry` model.
  - `Shift` constrains endpoint Y movement or locks bend while moving middle controls.
  - `Cmd/Ctrl` keeps branch drag selection non-destructive where possible.
- Added focused P1 Playwright coverage for middle-handle drag, endpoint-handle availability, and modifier-key stability.
- Updated `dev_docs/TEST_SELECTORS.txt` for the new stable selectors.

## Verification
- `npm run ui:lint` -> pass.
- `npm run ui:build` -> initial failure because `node_modules/typescript/lib/tsc.js` was missing; repaired worktree dependencies with `npm ci --ignore-scripts`, restored tracked `node_modules` artifacts, then reran.
- `npm run ui:build` -> pass.
- `npx playwright test tests/e2e/p1/timeline_interaction.spec.ts --config tests/playwright.config.ts` -> blocked before app execution because managed Playwright Chromium was missing.
- `npx playwright install chromium` -> failed with repeated CDN `ETIMEDOUT` while downloading Chromium.
- Fallback validation with temporary config using installed `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`:
  - `npx playwright test tests/e2e/p1/timeline_interaction.spec.ts --config tests/.tmp-system-chrome.playwright.config.ts` -> 3 passed.
  - `npx playwright test tests/e2e/p0/navigation.spec.ts --config tests/.tmp-system-chrome.playwright.config.ts` -> 1 passed.

## Residual Risks
- The official Playwright config still requires a successful managed Chromium install/cache repair on this machine.
- Branch control insertion remains intentionally mapped to the existing single `geometry.bend` / `geometry.laneOffset` model; no semantic topology or multi-control-point backend model was added.
