# Reviewer P1: Portrait Target Symlink

## Scope

- `src/electron/main.js`
- `tests/electron/runtime_smoke.mjs`

## Changes

- Rejected existing portrait destinations unless they are regular, non-symlink files.
- Routed portrait save and upload writes through a no-follow file descriptor and verified the opened descriptor is a regular file.
- Replaced destination `copyFile` calls with authorized-source reads followed by the guarded destination write.
- Added runtime smoke coverage that creates real portrait-target symlinks to an external sentinel for both `portraitSave` and `portraitUpload`; each request must fail and the sentinel must remain unchanged.

## Verification

- `node --check src/electron/main.js && node --check tests/electron/runtime_smoke.mjs` - passed.
- `npm run electron:smoke` initially could not bind its loopback fixture server in the sandbox (`listen EPERM`).
- Re-ran `npm run electron:smoke` with loopback permission - passed. The smoke output reported `Electron runtime smoke passed.`

## Risk

- The smoke cleanup still force-terminates Electron after its bounded close timeout, an existing cleanup-harness behavior after the successful assertions. It did not affect the test result.
