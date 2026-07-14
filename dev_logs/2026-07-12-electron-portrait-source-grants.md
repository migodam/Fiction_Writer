# Electron Portrait Source Grants

Date: 2026-07-12

## Changes

- Added renderer-scoped, one-time source grants for regular files returned by the main-process file dialog. Grants use canonical paths, expire after five minutes, and are cleared when the owning window closes.
- Required both `portrait:upload` absolute paths and `portrait:save` `file:` URLs to consume a source grant before copying. Arbitrary local paths and replayed grants now fail.
- Restricted remote portrait downloads to HTTPS on port 443, resolved every redirect hop before use, rejected loopback/private/link-local and other non-public address ranges, and pinned each request lookup to a validated address to avoid DNS rebinding.
- Limited portrait file and remote response size to 16 MiB and validated inline image data.
- Extended the Electron runtime smoke with unauthorized local-source rejection, dialog-granted upload and `file:` save success, grant replay rejection, and loopback URL rejection. Existing bounded cleanup remains in place.

## Files Modified

- `src/electron/main.js`
- `tests/electron/runtime_smoke.mjs`

## Verification

- PASS: `node --check src/electron/main.js`
- PASS: `node --check src/electron/preload.cjs`
- PASS: `node --check tests/electron/runtime_smoke.mjs`
- PASS: `git diff --check`
- PASS: `npm run electron:smoke`

## Notes

- The smoke fixture permits loopback only for the application test server; portrait remote URLs still reject loopback before any connection attempt.
