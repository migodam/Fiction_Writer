# Electron virtual project DB guard

## Changes

- Guarded renderer DB open/close and sidecar startup behind a filesystem project-root check.
- Kept Electron canonicalization, authorization, and root-containment checks unchanged.
- Added an Electron runtime smoke regression proving clean startup with the memory project makes no DB or sidecar calls.

## Tests

- `npm run electron:smoke` passed.
- `npm run ui:lint` passed.
