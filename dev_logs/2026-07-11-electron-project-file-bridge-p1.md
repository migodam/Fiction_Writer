# Electron Project File Bridge P1

## Changes
- Added explicit `utf8` and `base64` project-file bridge modes, with bounded 64 MiB raw-file payloads.
- Replaced renderer binary spread encoding with byte-wise base64 conversion, preventing argument-limit failures for large assets.
- Revalidated authorized roots, realpath ancestors, targets, and destination paths immediately before project-file operations, including canonical handling of `/tmp`-style filesystem aliases.
- Made writes and copies durable through exclusive no-follow temporary files, file fsync, atomic rename, parent-directory fsync, and temporary cleanup on failure.
- Applied equivalent path revalidation to rename and unlink operations.

## Coverage
- Electron smoke creates, saves, and reopens a real project through `projectService`, then asserts the persisted `project.json` roundtrip.
- Electron smoke roundtrips a deterministic 2 MiB binary asset through the renderer bridge.
- Electron smoke rejects root-external paths and symlink escapes for read, copy, rename, and unlink.

## Verification
- PASS: `node --check src/electron/main.js`
- PASS: `node --check src/electron/preload.cjs`
- PASS: `node --check tests/electron/runtime_smoke.mjs`
- PASS: `npx tsc --noEmit --pretty false`
- PASS: `npm run ui:lint`
- PASS: `npm run ui:build`
- PASS: `npm run electron:smoke`
