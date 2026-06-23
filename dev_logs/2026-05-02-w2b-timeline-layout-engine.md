# 2026-05-02 W2B Timeline Layout Engine

## Scope
- Added a pure frontend timeline layout engine v2 for deterministic branch/event geometry.
- Kept canvas rendering and direct interaction logic untouched for Wave 2C.

## Changes
- Added `timelineLayoutEngine.ts` with flexible branch/event hint inputs, adaptive branch virtual length, deterministic lane assignment, segmented S-curve paths for dense branches, same-rank/cluster-key clustering, and collision relaxation for visible node/cluster boxes.
- Added additive `bezierMath.ts` helpers for clamping, polyline sampling, and segmented SVG path construction while preserving existing exports.
- Added `tests/timeline_layout_engine_check.ts` as a lightweight dense synthetic fixture covering 100+ events, virtual length growth, monotonic branch order, and cluster conversion.

## Tests
- `npm ci --ignore-scripts` repaired a local missing `typescript/lib/tsc.js` dependency issue before verification. Tracked `node_modules` side effects were restored.
- `rm -rf /tmp/narrative-timeline-layout-check && npx tsc tests/timeline_layout_engine_check.ts src/ui-react/components/timeline/timelineLayoutEngine.ts src/ui-react/components/timeline/bezierMath.ts --outDir /tmp/narrative-timeline-layout-check --rootDir . --module NodeNext --moduleResolution NodeNext --target ES2022 --skipLibCheck --strict && node /tmp/narrative-timeline-layout-check/tests/timeline_layout_engine_check.js`
  - Passed: `timeline layout engine check passed: 121 events, 1 clusters`.
- `npm run ui:lint`
  - Passed.
- `npm run ui:build`
  - Passed. Vite reported the existing chunk-size advisory for the main bundle.
