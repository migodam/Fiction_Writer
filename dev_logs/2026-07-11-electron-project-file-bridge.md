# Electron Project File Bridge

## Changes
- Added a named, synchronous preload project-file bridge for project-local existence, read, atomic write, directory, listing, delete, realpath, copy, and rename operations.
- Main-process operations derive the authorized root from the sender session, reject escaping paths and symlink-resolved ancestors outside that root, and only permit the existing create-project parent-to-child transition.
- Replaced `projectService` renderer `require` dependence with a bridge-backed filesystem/path adapter while retaining the existing injected Node runtime fallback for browser tests.
- Extended Electron runtime smoke coverage to create, overwrite, and read a real project file after root selection, and to reject an external path.

## Files Modified
- `src/electron/main.js`
- `src/electron/preload.cjs`
- `src/ui-react/services/electronApi.ts`
- `src/ui-react/services/projectService.ts`
- `tests/electron/runtime_smoke.mjs`
- `dev_logs/2026-07-11-electron-project-file-bridge.md`

## Tests
- PASS: `node --check src/electron/main.js`
- PASS: `node --check src/electron/preload.cjs`
- PASS: `node --check tests/electron/runtime_smoke.mjs`
- PASS: `npm run ui:lint`
- PASS: `npm run ui:build`
- BLOCKED: final `npm run electron:smoke` was denied by the execution approval service because the workspace is out of credits. The smoke assertions were updated but could not be rerun after this change.
