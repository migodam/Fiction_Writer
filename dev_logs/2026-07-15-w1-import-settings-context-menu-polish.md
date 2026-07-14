# W1 Import, Settings, and Context Menu Polish

## Scope
- Replaced split/reverse W1 activity lists with one chronological execution stream and a separate current-action card.
- Redesigned the idle Import surface around compact presets, extraction scope, runtime summary, and a seven-stage rail.
- Replaced the provider-test placeholder with a real Electron main-process `GET /models` probe.
- Made shared context menus theme- and locale-aware and added practical character, world, and manuscript commands.

## Provider Safety
- API keys are sent only in the `Authorization` header and never returned in results.
- Only HTTPS endpoints and loopback HTTP endpoints are accepted.
- Non-loopback hostnames must resolve only to public addresses; private, link-local, unspecified, and multicast targets are rejected. The HTTP(S) connection is pinned to the validated address list to close DNS-rebinding gaps while retaining hostname-based TLS verification.
- The probe has an 8-second timeout and typed errors for authentication, rate limits, server failures, TLS, network failures, and invalid payloads.
- The probe lists models only; it does not generate content or incur model-generation token usage.

## Verification
- `npm run ui:build`: pass (existing bundle-size warning only).
- `npm run ui:lint`: pass.
- Focused Playwright: Import observability, provider settings, character/world/manuscript context menus pass.
- Context-menu Chinese locale + light theme: automated pass.
- `node tests/electron/runtime_smoke.mjs`: pass, including success, 401, 429, 503, unsafe/internal endpoint rejection, invalid payload, `/models` path normalization, key non-disclosure, and bridge isolation.
- In-app browser visual review: Import and AI Provider settings checked at desktop viewport.

## Residual Risk
- The Electron smoke requires force termination after its assertions because the existing beforeunload dialog prevents graceful test-process shutdown; assertions complete before cleanup.
- The production bundle remains above Vite's 500 kB warning threshold; this change does not increase the functional scope to bundle splitting.
