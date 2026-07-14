# Electron Project-Root Authorization

## Changes
- Canonicalized selected project roots with `realpath` and bound each root to its renderer `webContents` session.
- Registered roots only from the native project-directory selection flow, with a one-time direct-child transition for the existing create-project flow.
- Required that binding for DB, portrait, sidecar, workflow, and sidecar-proxy IPC handlers.
- Encoded workflow status `session_id` query parameters and limited remote portrait downloads to public HTTPS URLs.

## Files Modified
- `src/electron/main.js`
- `src/electron/preload.cjs`
- `tests/electron/runtime_smoke.mjs`
- `dev_logs/2026-07-11-electron-project-root-authorization.md`

## Tests
- PASS: `node --check src/electron/main.js`
- PASS: `node --check src/electron/preload.cjs`
- PASS: `node --check tests/electron/runtime_smoke.mjs`
- PASS: `npm run electron:smoke`

## Residual Risk
- Hostname validation prevents obvious loopback and private literal-address portrait targets. It does not resolve DNS before fetching, so a hostile public hostname that resolves to a private address remains outside this focused change.
