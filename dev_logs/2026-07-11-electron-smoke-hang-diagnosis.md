# Electron Smoke Hang Diagnosis

## Changes
- Added timestamped start, completion, and failure logs for fixture listening, Vite creation/listening/closing, Electron launch/window/close, page navigation/evaluations, and cleanup.
- Added bounded stage timeouts: 10s for the fixture server, 20s for Vite and navigation, 30s for Electron launch/window, 45-90s for bridge/project-service evaluations, and 5-15s for cleanup.
- Made cleanup idempotent and signal-aware. It closes active connections, attempts a graceful Electron close, force-kills Electron if that close exceeds 5s, closes Vite and the fixture server, and removes all temporary directories.
- Added late-resource disposal for a start operation that resolves after its timeout, plus an unhandled-rejection cleanup path.
- Moved the fixture context-menu assertion before Vite navigation and normalized smoke assertions for macOS `/var` to `/private/var` realpath aliases.

## Independent Run
- Command: `npm run electron:smoke`
- Exit code: `0`
- Elapsed: approximately `8.2s`
- All test stages completed by approximately `3.2s`.

## Root Cause
- The previous harness had no phase logging or timeout around `app.close()`, so Electron shutdown could wait indefinitely.
- The instrumented run shows Electron emitting a `beforeunload` dialog during close; Playwright's dialog handling races with the close path, and graceful `app.close()` does not resolve within 5s.
- The harness now records that condition, force-kills the Electron process, and completes Vite/server/temp-directory cleanup instead of hanging.
