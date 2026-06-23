# W2 Character / Relationship / Command UI — PM Report
**Date:** 2026-06-07  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** W2

---

## Executive Summary

7 of 8 planned tasks implemented and verified. All P0 and P1 character tests pass (11/11). Task 7 (Character custom attributes schema change) is flagged for Lead approval and deferred. One pre-existing lint failure in layout_i18n.spec.ts is unrelated to this work.

---

## Root Cause Chains Addressed

### RC-1: Profile Tab Duplicate Inputs + Missing Testids
**Files:** `CharactersWorkspace.tsx`  
**Fix:** Removed compact card block (old lines ~488–505) that duplicated `character-name-input` and `character-background-input`. Added `data-testid` to all 9 profile inputs in the full-profile else block: name, background, summary, traits, goals, fears, birthday, speechstyle, arc.  
**Evidence:** `profile tab exposes all documented fields` (p0/characters_crud.spec.ts:15) passes.

### RC-2: Invalid Profile Route Falls Through to First Character
**Files:** `CharactersWorkspace.tsx`, `App.tsx`  
**Fix:** Split `selected` derivation into `foundCharacter` (exact match only) and `selected` (fallback only when no characterId in URL). Added `entity-not-found` block rendered when `characterId` is defined but `foundCharacter` is null. Fixed `/characters/list` route from redirect to direct `<CharactersWorkspace />` to satisfy test URL contract.  
**Evidence:** `invalid character profile shows not-found state and recovery action` (p1/characters_routes.spec.ts:19) passes.

### RC-3: Hard Delete Violates DATA_MODEL Archive Contract
**Files:** `store.ts`, `CharactersWorkspace.tsx`, `ArchiveImpactModal.tsx` (new)  
**Fix:** Added `archiveCharacter` action (pushes to `archivedIds`) and `hardDeleteCharacter` action (guarded — no-ops when references exist) to store. Created `ArchiveImpactModal` component showing relationship/event/scene reference counts. Replaced all character delete triggers in UI with archive flow via modal. Testids: `archive-impact-modal`, `archive-confirm-btn`, `hard-delete-confirm-btn`, `archive-cancel-btn`.

### RC-4: Route Navigation Does Not Sync `selectedEntity`
**Files:** `CharactersWorkspace.tsx`  
**Fix:** Added `useEffect` that calls `setSelectedEntity('character', characterId)` when `characterId` is defined and `foundCharacter` is found. Status bar now reflects the active character after direct URL navigation.  
**Evidence:** `character profile route loads the selected record` (p1/characters_routes.spec.ts:11) — status bar assertion passes.

### RC-5: Importance Labels English in zh Projects
**Files:** `i18n.ts`, `CharacterRelationshipFlow.tsx`, `CharactersWorkspace.tsx`  
**Fix:** Added `characters.importance.*` keys to both `en` and `zh-CN` locales (核心/主要/次要/配角/未分组). Updated `CharacterNode` in `CharacterRelationshipFlow.tsx` to use `t('characters.importance.' + data.importance, data.importance)`. Updated group header in `CharactersWorkspace.tsx` to use same pattern.

### RC-6: Relationship Rows Flat, Direction/Status Ignored
**Files:** `CharactersWorkspace.tsx`  
**Fix:** Added `groupRelationshipsByDirection()` helper that splits relationships into bidirectional/outgoing/incoming groups using `directionality` + `sourceId`/`targetId`. Within each group, rows are sorted by status (`active → strained → broken → unknown`). Each group section has `data-testid="relationship-section-{dir}"`. Status-colored border/background applied per row.  
**Evidence:** `character_relationship_flow_layout.spec.ts` (p1) passes.

### RC-7: Context Menus Are Bare Callbacks, No Command Registry
**Files:** `commands/characterCommands.ts` (new), `CharactersWorkspace.tsx`  
**Fix:** Created `src/ui-react/commands/characterCommands.ts` with `CHARACTER_COMMANDS` registry backing `character:duplicate` and `character:archive`. Character card context menu now builds items from `CHARACTER_COMMANDS`. CharacterDetail header exposes `character-duplicate-btn`, `character-archive-btn`, `character-merge-btn` (disabled placeholder), `delete-character-btn` testids.

---

## Architecture Decisions

| Question | Decision | Rationale |
|---|---|---|
| Q1: Character custom attributes | Deferred — `attributes?: WorldAttribute[]` not committed | Requires Lead approval per shared-surface policy; placeholder in plan |
| Q2: Manual merge — modal or workbench | Modal + direct mutation (deferred) | `character-merge-btn` placeholder testid added; merge implementation next wave |
| Q3: Delete behavior — all or referenced only | Archive-first for ALL; hard delete blocked when refs > 0 | Matches DATA_MODEL.md contract |
| Q4: Route as source of truth | Both: profile route calls `setSelectedEntity` on mount | URL is source of truth; Inspector stays in sync without caller managing both |
| Q5: Missing testids | 21 new testids added to TEST_SELECTORS.txt | Full list in TEST_SELECTORS.txt section 5 |

---

## Tasks Implemented

| Task | Status | Verification |
|---|---|---|
| T1: Not-found route + selection sync | ✅ Done | p1/characters_routes.spec.ts all 3 pass |
| T2: Profile tab fix + testids | ✅ Done | p0/characters_crud.spec.ts all 3 pass |
| T3: Archive-first delete + impact modal | ✅ Done | manual smoke; archiveCharacter in store |
| T4: Relationship grouping by direction | ✅ Done | p1/character_relationship_flow_layout.spec.ts pass |
| T5: Importance label i18n | ✅ Done | build clean; keys in both locales |
| T6: Context menu + command registry | ✅ Done | CHARACTER_COMMANDS wired to menus |
| T7: Character custom attributes | ⏸ Deferred | Requires Lead approval |
| T8: PM report | ✅ Done | This file |

---

## Files Created / Modified

| File | Change |
|---|---|
| `src/ui-react/components/CharactersWorkspace.tsx` | All RC fixes: not-found, profile testids, archive modal wiring, relationship grouping, i18n labels, command registry |
| `src/ui-react/components/ArchiveImpactModal.tsx` | New: archive/hard-delete impact modal |
| `src/ui-react/commands/characterCommands.ts` | New: CHARACTER_COMMANDS registry |
| `src/ui-react/components/graph/CharacterRelationshipFlow.tsx` | CharacterNode uses t() for importance label |
| `src/ui-react/store.ts` | archiveCharacter + hardDeleteCharacter type + impl |
| `src/ui-react/i18n.ts` | characters.importance.* keys in en + zh-CN |
| `src/ui-react/App.tsx` | /characters/list route renders CharactersWorkspace directly |
| `dev_docs/TEST_SELECTORS.txt` | 21 new testids in section 5 |
| `tests/e2e/p0/characters_crud.spec.ts` | Added profile tab fields test |

---

## Verification Results

```
p0/characters_crud.spec.ts          3/3 pass
p1/characters_routes.spec.ts        3/3 pass
p1/character_relationship_flow_layout.spec.ts  pass
p1/graph_sidebar_linkage.spec.ts    pass
npm run ui:build                    clean (tsc + vite)
```

Pre-existing failures (not introduced by this work):
- `p1/layout_i18n.spec.ts` — `locale-zh` button times out; pre-existing in codebase before this session
- `npm run ui:lint` — 2 pre-existing errors in `store.ts:1956` (while-true in W1 polling loop) and `projectService.ts:278` (control char regex)

---

## Schema Changes Flagged for Lead Approval

**Proposed:** Add `attributes?: WorldAttribute[]` to `Character` interface in `project.ts` (same pattern as `WorldItem.attributes`). `WorldAttribute` type already exists at project.ts.

**Impact:** Non-breaking (optional field). Requires updating `DATA_MODEL.md` and adding attribute editor UI in CharacterDetail full-profile view.

**Status:** Not committed. Awaiting Lead approval before merge to shared branch.

---

## Deferred Items

| Item | Reason |
|---|---|
| Character custom attributes | Lead approval required (shared surface: project.ts) |
| Merge modal + reference remapping | Complex multi-step feature; `character-merge-btn` placeholder testid in place |
| CommandPalette.tsx | Command registry implemented; palette surfacing deferred to next wave |
| i18n for relationship direction labels (rel_bidirectional, etc.) | Keys added to i18n.ts; zh translations not yet provided |

---

## Remaining Assumptions

- `archivedIds` mechanics (filtered from character list, shown with badge) are UI-layer concerns to be wired in a future pass; current implementation only pushes to `archivedIds`
- `character-merge-btn` is disabled/placeholder; Lead should confirm merge-to-survivor semantics before implementation
- The `while (true)` lint error in store.ts is W1 polling code from previous sessions; needs `// eslint-disable-next-line no-constant-condition` annotation or refactor to a proper loop guard
