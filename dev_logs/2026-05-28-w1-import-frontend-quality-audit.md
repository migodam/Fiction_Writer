# W1 Import Frontend Quality Audit — 2026-05-28

## Session Constraints

- No live API calls made.
- No full50 benchmark run.
- No provider credentials used.
- All fixes are deterministic and zero-cost.
- Tests use seed project data and IPC mocks only.

---

## Timeline Layout Algorithm Audit

### Lane Assignment
Fan-based: `fanLaneOffset(branchOrder - 1, spacing=1)` returns integer lane indexes (0, -1, 1, -2, 2, …).
`laneY = laneIndex × 170px`. Deterministic, collision-free across branches.
**Status: ✅ Working correctly.**

### X/Y Positioning
Rank → `rankToT()` (4% padding, linear mapping) → `pointOnPolyline()` for per-branch coordinates.
Canvas min-spacing pass in `TimelineCanvas.tsx` enforces 80px horizontal gap per branch.
**Status: ✅ Working correctly.**

### Collision Avoidance
6-pass relaxation: shifts overlapping nodes ±42px vertically within the same visual pool.
- **Gap 1:** No inter-branch collision detection. Two branches with the same `laneIndex` can overlay events.
- **Gap 2:** No label collision detection. SVG text labels can overlap neighboring nodes at high density.

**Status: ⚠️ Partial. Adequate for current seed project density; degrades at 50+ events per lane or tight branch spacing.**

### CJK Label Truncation
**Was broken:** `title.slice(0, 18)` treated CJK chars as 1 unit. At 10px font, 18 CJK ≈ 180px overflow.
**Fixed this session:** `isCjkChar()` + `truncateTitle()` truncate at visual-width 18 (≈9 CJK or ≈18 ASCII).
**Status: ✅ Fixed.**

### Cluster Rendering
Layout algorithm marks events as `renderMode: 'clustered'` when ≥4 events share rank ≤0.0001.
**Gap:** `TimelineCanvas.tsx` does not differentiate cluster vs node rendering visually.
Dense clusters appear as overlapping individual circles rather than a single grouped indicator.
**Status: ⚠️ Algorithm detects clusters; UI rendering gap not fixed. Documented only.**

### Fork/Merge Topology
`parentBranchId + forkEventId` → start anchor; `mergeTargetBranchId + mergeEventId` → end anchor.
Cubic Bézier from fork to merge. Visual fork/merge correctly represented.
**Status: ✅ Working correctly.**

### Zoom/Pan/Scroll
Exponential zoom 0.1–4×, cursor-centered. Pan via drag. Canvas min 2000px.
**Status: ✅ Working correctly.**

---

## Import UI Audit

### Currently Surfaced

| Feature | Status | Notes |
|---------|--------|-------|
| Progress bar + chunk count | ✅ Correct | Per-chunk granularity |
| Current tool / window / chapter range | ✅ Correct | RuntimeField cards during run |
| Judge score + converge status | ✅ Correct | Both during run and in review |
| Review status color coding | ✅ Fixed this session | amber=acceptable_with_warnings, green=pass, red=fail |
| Warnings list (expandable) | ✅ Fixed this session | Show N more toggle for >4 warnings |
| Safe accept all | ✅ Correct | Count and action correct |
| Failed chunk count | ✅ Correct | Red banner |
| Per-chunk console with rewind | ✅ Correct | Breakpoint controls present |

### Product Gaps (Backend Exists, UI Not Yet Surfaced)

| Gap | Priority | Recommendation |
|-----|----------|----------------|
| `blocked_ids[]` in review report | Medium | Show blocked proposal count with explanation |
| `duplicate_merges[]` | Low | Collapsible "Duplicates" section in review |
| `low_confidence_items[]` | Medium | Yellow-badge count in review summary |
| Judge `strengths[]`, `risks[]`, `recommendations[]` | Medium | Expandable collapsible in judge artifact card |
| Per-chunk quality rubric score | Low | Sparkline in console log entries |
| SourceProfile (language, style detection) | Medium | Badge in import header ("Chinese / wuxia novel detected") |
| PlannerProposal + PromptPolicyPatch | Blocked | Planner knobs not yet applied to prompts (backend gap) |
| `w1UseSupervisor` UI toggle | Deferred | In store but no UI control |
| Window metadata (late-zone density cap) | Low | "Dense late chapter detected" warning badge |
| Cluster rendering differentiation | Medium | Distinguish clustered vs individual event nodes visually |

---

## Product Readiness Progress Table

| Stage | Backend Status | Frontend Status | Product-Quality Status | Remaining Risk |
|-------|---------------|-----------------|------------------------|----------------|
| Cost guard / 402 | ✅ Hard stop enforced | ✅ Error displayed | ✅ Production-safe | None |
| Granularity profiles | ✅ 4 presets dispatched | ✅ Dropdown + 7-dim custom panel | ✅ User-configurable | None |
| Prompt variants (8 deep) | ✅ asyncio.gather dispatch | ⚠️ Profile selection only | ⚠️ Per-prompt quality opaque | Live smoke needed |
| ImportPlan | ✅ Validated + gated | ❌ Not shown in UI | ❌ Opaque to user | Document only |
| SourceProfile | ✅ Language/style detected | ❌ Not surfaced | ❌ User unaware | Document only |
| PlannerProposal | ✅ Schema validated | ❌ Not surfaced | ❌ Planner decisions invisible | Backend prompt gap |
| PromptPolicyPatch | ✅ Typed + validated | ❌ Knobs not applied to prompts | ❌ No effect yet | Blocked: prompt design session |
| Quality rubric | ✅ 15 zero-cost checks | ⚠️ Status only (not rubric detail) | ⚠️ Minimal transparency | Document gaps |
| Window metadata | ✅ Density cap + late-zone tracking | ❌ Not surfaced | ❌ Invisible to user | Document only |
| Timeline topology UI | ✅ Backend assigns branchId/orderIndex | ✅ CJK truncation fixed | ⚠️ Usable; cluster rendering gap remains | Document cluster gap |
| Import review UI | ✅ Judge artifact + warnings + blocked_ids | ✅ Status color + expand toggle fixed | ✅ Acceptable for launch | Blocked/duplicate gaps remain |
| Responsive/macOS readiness | N/A | ✅ Playwright tests at 4 viewports | ✅ No critical clipping | None |
| Live smoke readiness | ❌ No full50, no live run | ❌ Not tested with real import output | ❌ Not ready | Requires authorized live smoke session |

---

## Verified Fixes This Session

1. **`acceptable_with_warnings` in type union** (`electronApi.ts`) — `W1ImportReviewReport.status` now includes all backend status values.
2. **CJK label truncation** (`TimelineEventNode.tsx`) — visual-width estimator (CJK=2, others=1), truncate at width 18.
3. **`acceptable_with_warnings` status color** (`ImportWorkflow.tsx`) — amber via `REVIEW_STATUS_COLOR` map using existing Tailwind tokens.
4. **Warnings expand toggle** (`ImportWorkflow.tsx`) — "Show N more / Show less" button for >4 warnings.
5. **DEV-mode store exposure** (`store.ts`) — `window.__narrativeStore` (guarded by `typeof window !== 'undefined' && import.meta.env.DEV`) enables Playwright dense-topology injection without modifying `seedProject.ts`.

## New Tests Added

**`tests/e2e/p1/timeline_topology_import.spec.ts`** — 15 tests:
- Seed project suite (6): node visibility, no-overlap, branch lanes, label presence, canvas dimensions
- Dense injection suite (6): ≥20 nodes, no-overlap, lane segments, lane separation, CJK label length, canvas size
- Responsive suite (4): 1280×800, 1440×900, 1728×1117, 1024×768

**`tests/e2e/p1/import_quality_status.spec.ts`** — 10 tests:
- acceptable_with_warnings suite (6): text, color class, 4-item initial count, show-more toggle, expand to 6, judge summary
- pass suite (2): green color, no toggle
- Responsive suite (2): 1280×800, 1024×768

## Known Remaining Frontend Gaps

- **Cluster rendering**: dense event clusters render as overlapping individual circles, not a grouped indicator. Layout engine correctly marks them; `TimelineCanvas.tsx` needs a dedicated cluster node component.
- **Dense label collision**: at >30 events per branch, SVG text labels can overlap neighboring nodes. No label collision avoidance exists in the current rendering layer.
- **blocked_ids / duplicate_merges / low_confidence_items**: exist in `W1ImportReviewReport` type and backend output but not surfaced in `ImportWorkflow.tsx`.
- **Judge strengths/risks/recommendations**: fields present in `W1JudgeArtifactSummary` type but not displayed in review card.

## Next Recommended Step

**Authorized live smoke**: Run W1 import on a real Chinese wuxia chapter (with provider key, explicit cost approval) and verify:
- Timeline events carry `branchId`, `orderIndex`, and `topologyHints.rank`
- Imported topology renders without CJK label overflow
- `acceptable_with_warnings` appears correctly in review with amber status
- Judge score ≥ 0.7 and `converge_status = 'converged'`
- No cluster rendering clutter at actual import density
