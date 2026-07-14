# D2 Electron Runtime Security

Date: 2026-07-11

## Changes

- Enabled `nodeIntegration: false` and `contextIsolation: true` for the Electron BrowserWindow.
- Added `src/electron/preload.cjs`, a named capability bridge with no generic `ipcRenderer`, `invoke`, or `send` exposure.
- Kept the renderer-facing `electronApi` method signatures intact through a preload adapter.
- Added validation for project-root IPC, settings payloads, file-dialog filters, portrait payloads, and DB table/entity inputs.
- Added `npm run electron:smoke`, which launches Electron with a loopback-only fixture and checks file-selection, settings, W1 project-root routing, renderer Node isolation, and context-menu propagation.

## Verification

- PASS: `npm run electron:smoke`
- PASS: `node --check src/electron/main.js`
- PASS: `node --check src/electron/preload.cjs`
- PASS: `node --check tests/electron/runtime_smoke.mjs`
- BLOCKED by concurrent UI change: `npm run ui:build` stops at `src/ui-react/components/ManuscriptWorkspace.tsx(184,49)` because an `id` property is not valid for `Omit<ManuscriptNode, "id">`.

## Headless Limitation

The smoke harness uses deterministic Electron-main dialog responses only when `NARRATIVE_IDE_RUNTIME_SMOKE=1`; it validates the real preload-to-main bridge but cannot click a native macOS/Windows/Linux file picker. A headed manual pass remains necessary for platform-native dialog presentation.
