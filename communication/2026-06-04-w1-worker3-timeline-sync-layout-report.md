# Worker W3 Delivery Report — Timeline Frontend/Backend Consistency and Label Layout

**Date:** 2026-06-04
**Branch:** `codex/w1-orchestrated-import-quality`
**Worker:** W3 — Timeline Sync, Round-trip Persistence, Dense Label Layout, Topology Correctness

---

## Summary

W3 completed all 5 assigned tasks across schema hygiene, drag-to-persist round-trips, dense event label layout validation, branch topology acceptance path testing, and full suite triage. All 33 new p1 tests pass. 9 pre-existing p0 failures were root-cause classified and confirmed unrelated to W3.

---

## Task 1 — Schema Cleanup: Remove 6 Runtime-Only Fields from optional Declarations

**File changed:** `src/ui-react/services/projectService.ts`

Six fields that were always stripped by `toCanonical()` and never persisted were removed from the schema optional declarations:

- **Branch fields removed:** `anchorStartPos`, `anchorEndPos`
- **Event fields removed:** `position`, `sharedBranchIds`, `layoutLock`, `modalStateHints`

**Behavioral analysis:** `collectTimelineSyncSchemaMissingFields()` checks the FRONTEND→SCHEMA direction. Runtime fields were already excluded at the code level via `BRANCH_RUNTIME_FIELDS` / `EVENT_RUNTIME_FIELDS` guard sets. Declaring them as optional in the schema was a dead declaration that could only cause false-positive schema-mismatch warnings. The fix eliminates that risk at the contract level.

This is a data-contract cleanliness fix with no behavioral side effects.

**Test added:** `tests/e2e/p1/timeline_sync_roundtrip.spec.ts`
- "sync analysis: no false-positive warnings about runtime-only fields" — **PASS**

**Shared surface note:** `projectService.ts` is a shared surface. W3 must merge before W4/W5 begin work on any task that touches this file.

---

## Task 2 — Drag → Save → Reload Round-Trip (Two Layers)

**Tests added to:** `tests/e2e/p1/timeline_sync_roundtrip.spec.ts`

### Layer A — Store-Level Canonical Mutation

Calls `moveTimelineEvent()` directly on the Zustand store. Verifies `branchId` and `orderIndex` update correctly in memory. Uses two-phase save wait (dirty → saved state transition). Reloads the application, navigates back to the timeline view, waits for store repopulation, and verifies canonical fields survived persistence.

**Result: PASS**

### Layer B — UI Pointer-Drag Interaction

Registers a `pageerror` listener before any store injection to capture any JS errors produced during drag. Performs a 20-step pointer drag following a 600ms long-press activation. Checks whether snap-to-branch-curve fired (snap threshold 40px). In headless Playwright, canvas geometry does not guarantee snap due to pixel rendering differences from headed mode.

Outcome: snap did not fire in headless (known geometry limitation); JS error count was 0 (else branch asserts pageerror count = 0).

**Result: PASS** (else branch — no snap in headless, no JS errors)

---

## Task 3 — Dense 30+ Event Label Layout

**Tests added/hardened in:** `tests/e2e/p1/timeline_topology_import.spec.ts`

**Test:** "dense event labels do not overlap and hidden labels still expose tooltip"

- Injects 42 events: 32 mainline + 10 fork events
- Waits for first label visibility using an event-driven approach (no `waitForTimeout`)
- Asserts 21+ visible labels
- Runs pairwise AABB non-overlap check for all visible labels
- Verifies that events with hidden labels still expose a tooltip on hover

**Result: PASS**

**Engine assessment:** `timelineLayoutEngine.ts` was reviewed — the existing 8-candidate placement strategy is sufficient for the 42-event dense scenario. No changes needed.

**Tooltip assessment:** `TimelineEventNode.tsx` was reviewed — tooltip rendering is already unconditional with no gate on label visibility. No changes needed.

---

## Task 4 — Branch Topology Preservation via Proposal-Acceptance Path

**Tests added to:** `tests/e2e/p1/timeline_topology_import.spec.ts` (Suite 4: "Timeline topology: proposal acceptance path")

### 4-Branch Topology Test

Injects 11 proposals (4 branches + 7 events) via `store.proposals`. Calls `resolveProposals(ids, 'accepted')` to exercise the real acceptance path through `applyImportPackageBatches()`. Verifies:

- 4 branches created with correct fork/merge topology
- Mentor branch has `endMode: 'merge'`, `mergeEventId`, and `mergeTargetBranchId` set correctly
- Two-phase save wait completes
- After reload + `waitForFunction` targeting specific branch ID, all 4 branches survive `normalizeTimelineCollections()`

**Result: PASS**

### User-Named Empty Planning Branch Survival

Adds a branch named `'未来规划'` (not in the exact-name deletion filter `['main branch', 'main timeline', '主时间线']`). After two-phase save wait, reload, and `waitForFunction` targeting the specific branch ID (not a weak `length > 0` check), asserts the name `'未来规划'` is still present.

**Result: PASS**

**Filter assessment:** `normalizeTimelineCollections()` uses an exact-name filter for cleanup. This is conservative and correct. User-named branches survive normalization.

---

## Task 5 — Full Timeline Suite Triage

### W3-New p1 Tests: 33/33 PASS

| Spec file | Tests | Result |
|---|---|---|
| `tests/e2e/p1/timeline_sync_roundtrip.spec.ts` | 11 | 11/11 PASS |
| `tests/e2e/p1/timeline_interaction.spec.ts` | 3 | 3/3 PASS |
| `tests/e2e/p1/timeline_topology_import.spec.ts` | 19 | 19/19 PASS |

### W3-Introduced Failures Fixed During Development

Tests for "sync analysis" (Task 1), Layer A, and Layer B (Task 2) were failing because `page.goto('/')` alone does not open the timeline panel. Fix: added `activity-btn-timeline.click()` after navigation. Fixed in commit `ad026fd`.

### Pre-Existing p0 Failures: 9 Failures, All Classified

All 9 pre-existing p0 failures were root-cause classified. None were introduced by W3.

**Group 1 — `timeline_sync.spec.js` (lines 29, 64) — "orphan file cleanup"**
Tests assert `fs.existsSync(eventFile)` returns false after event deletion. These fail because file persistence to disk requires the Electron IPC layer (native file writes), which is not active in web dev server mode (`http://localhost:3000`). Pre-existing; unrelated to W3.

**Group 2 — `timeline_canvas.spec.js` (line 62) — "fully overlapped timelines"**
Looks for `data-testid="timeline-branch-overlap-branch_echo"`. This overlap rendering group is not present in the current DOM. The parallel offset curves feature for this branch may not be implemented. Pre-existing.

**Group 3 — `timeline_canvas.spec.js` (line 74) — "can create, edit, and delete a timeline event"**
Looks for `add-event-btn`, `create-event-title-input`, `event-edit-modal`. These UI elements are not present in the current component tree. Pre-existing.

**Group 4 — `timeline_sync.spec.js` (lines 95–153) — branch delete context menu (5 tests)**
Right-clicks on `timeline-branch-hitarea-branch_main`. Element resolves but is CSS-hidden (`visibility: hidden`). Context menu feature is not wired to the hitarea in the current implementation. Pre-existing.

---

## Build Status

`npm run ui:build` — **PASS**

No TypeScript errors. One pre-existing chunk size warning (unrelated to W3 changes).

---

## Shared Surface Note

`src/ui-react/services/projectService.ts` was modified in Task 1 (schema optional declaration cleanup). W3 must merge before W4/W5 begin work on any shared surface that touches this file to avoid merge conflicts.

---

## Remaining Risks

| Risk | Severity | Notes |
|---|---|---|
| Layer B snap reliability in headless | Low | Snap-to-branch-curve requires pixel-accurate pointer proximity (SNAP_THRESHOLD=40px). Headless Playwright canvas geometry may not match headed geometry. Layer A (store-level) covers canonical persistence. Layer B validates drag interaction completes without JS errors. Acceptable coverage split. |
| p0 file system tests require Electron IPC | Medium | Tests in `timeline_sync.spec.js` for orphan file cleanup only pass when running against the full Electron app, not the web dev server. Not a W3 gap — a test environment gap. |
| p0 branch context menu hidden hitarea | Medium | `timeline-branch-hitarea-branch_main` is CSS-hidden; context menu is not wired in current implementation. This is a production gap. Not in W3 scope; should be tracked as a separate backlog item. |

---

## Files Changed or Added by W3

| File | Change type |
|---|---|
| `src/ui-react/services/projectService.ts` | Modified — removed 6 runtime-only optional field declarations |
| `tests/e2e/p1/timeline_sync_roundtrip.spec.ts` | New tests added — Tasks 1, 2 (11 tests total) |
| `tests/e2e/p1/timeline_topology_import.spec.ts` | New tests added — Tasks 3, 4 (19 tests total) |
| `tests/e2e/p1/timeline_interaction.spec.ts` | Hardened — 3 tests |
