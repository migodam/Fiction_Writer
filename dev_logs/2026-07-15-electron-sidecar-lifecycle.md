# Electron Sidecar Lifecycle - 2026-07-15

## Scope

- Updated `src/electron/main.js` sidecar readiness, runtime bridge gating, and shutdown cleanup.
- Updated `tests/electron/runtime_smoke.mjs` for the async `openProject` API and real sidecar lifecycle assertions.
- Added `tests/electron/sidecar_lifecycle_smoke.mjs` as a focused real-Electron bridge test.

## Changes

- Concurrent sidecar spawns share one per-project readiness promise.
- `sidecar:spawn` returns success only after the spawned process answers `/health`; early spawn/exit failures are returned with their concrete error and failed children are terminated.
- Runtime and workflow proxy calls revalidate the ready sidecar port before use.
- Window/app shutdown aborts AI and SSE streams, closes databases, sends `SIGTERM` to managed sidecars, and bounds a `SIGKILL` fallback.
- The broad smoke awaits `projectService.openProject(...)`, which is now asynchronous.

## Verification

- `node --check src/electron/main.js`
- `node --check tests/electron/runtime_smoke.mjs`
- `git diff --check`
- `npm run electron:smoke` passes the bridge, context-menu, project-service, readiness, runtime-call, and clean-exit assertions.
- `npm run electron:sidecar-lifecycle` passes the focused spawn, health, runtime, and shutdown lifecycle.
- `npm run electron:w1-actual-fixture` closes all real Electron and sidecar processes cleanly.

## Final Shutdown Contract

The sidecar identity now uses a SHA-256 digest of the canonical project path,
removing collisions caused by the previous truncated Base64 prefix. Shutdown
first drains AI/SSE streams, sidecars, and project databases, destroys windows,
and then uses a bounded `process.reallyExit(0)` fallback for Electron 30 test
transport sockets that can survive normal `app.quit()`. The fallback runs only
after durable cleanup has completed.
