# W1 Reviewer / Organizer / Timeline Sync — Lead Architect Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade W1 Import from "能跑" to "可信、可审阅、可修复、前后端一致" by adding a Reviewer framework, an Organizer stage, Timeline front-back round-trip persistence, and enhanced Inbox package UX — all as Orchestrator-callable tools.

**Architecture:** Reviewer tools run deterministically over artifacts (not full source text), classify findings into `localRepairActions` (small) or `orchestratorRequests` (large), and feed PromptPolicyPatch / targeted rerun. An Organizer stage routes imported candidates to correct modules (Timeline / Character / World / Manuscript) before proposal write. Timeline operations are validated and persisted via `projectService.applyTimelinePatch`.

**Tech Stack:** Python 3.11 + FastAPI sidecar, TypeScript + React + Zustand frontend, pytest, Playwright.

---

## 1. Goals and Non-Goals

### Goals
1. **Quality Reviewer** — deterministic checks over import artifacts: event density, mainline/branch ratio, World Model contamination, character completeness, relationship evidence.
2. **Fact Reviewer** — evidence-ref–based mismatch detection for candidate items against source spans; RAG snippets only, no full source read.
3. **Consistency Reviewer** — cross-import continuity: duplicate characters, branch topology breaks, world item collisions.
4. **Organizer Tool** — route imported candidates to correct modules; filter World Model pollution; output proposal packages (not silent writes).
5. **PromptPolicyPatch / Pipeline Toolization** — expose Reviewer findings as structured knob patches and targeted-rerun requests; no raw prompt injection.
6. **Timeline Canonical Adapter + Dense Label Placement** — all drag/drop/branch/merge/fork Timeline UI operations persist via `projectService.applyTimelinePatch`; reload round-trips correctly. Dense event layouts must use a deterministic scoring algorithm so label bounding boxes do not overlap; hidden labels must still expose full title via hover tooltip.
7. **Inbox Package UX** — ProposalPackage cards with dependency graph, per-package Accept/Retry, precise blocked reason; reviewer repair packages use same path.
8. **Zero-cost tests** for every new component.

### Non-Goals
- No live API calls.
- No full50 benchmark runs.
- No raw prompt injection or dynamic text in PromptPolicyPatch.
- Reviewer does not directly mutate canonical project storage.
- Import UI option toggles for Manuscript / Relationship extract switches (deferred).
- LLM-powered Reviewer adapters (interface stubs only; deterministic first).
- Deep character-card enrichment (W1 still produces compact drafts per spec).

---

## 2. Architecture Overview

```
Source Text
  └─ Segment Manifest → Prompt Windows → Extraction Tools
                                              ↓
                                     Reducer / Character Registry
                                              ↓
                             ┌────────────────┴────────────────┐
                     Timeline Architect             Organizer Tool
                             │                           │
                             └─────────┬─────────────────┘
                                Proposal Package Builder
                                       ↓
                              ┌────────┴────────┐
                      Quality Reviewer    Fact Reviewer    Consistency Reviewer
                              └────────┬────────┘
                                  Finding Router
                                 ┌─────┴─────┐
                          localRepair    orchestratorRequest
                                │              │
                          Repair Package   PromptPolicyPatch
                                │          + targeted rerun
                                └────┬─────────┘
                              Workbench Inbox
                          ProposalPackage Cards (UI)
                                    ↓
                          Package Accept Transaction
                                    ↓
                         Canonical Project Storage
```

---

## 3. File Map

### New files (by owner window)

| Window | File | Purpose |
|---|---|---|
| W1 Reviewer | `sidecar/supervisor/reviewers/__init__.py` | package |
| W1 Reviewer | `sidecar/supervisor/reviewers/schemas.py` | ReviewFinding, RepairAction, OrchestratorRequest, ReviewReport, ZeroCostLedger |
| W1 Reviewer | `sidecar/supervisor/reviewers/base.py` | BaseReviewer ABC, token-budget guard |
| W1 Reviewer | `sidecar/supervisor/reviewers/quality_reviewer.py` | QualityReviewer: event density, mainline share, World contamination, char completeness |
| W1 Reviewer | `sidecar/supervisor/reviewers/fact_reviewer.py` | FactReviewer: evidence-ref mismatch; RAG stub interface |
| W1 Reviewer | `sidecar/supervisor/reviewers/consistency_reviewer.py` | ConsistencyReviewer: cross-import continuity, duplicate characters, branch breaks |
| W1 Reviewer | `tests/test_w1_reviewers_quality.py` | QualityReviewer unit tests |
| W1 Reviewer | `tests/test_w1_reviewers_fact.py` | FactReviewer unit tests |
| W1 Reviewer | `tests/test_w1_reviewers_consistency.py` | ConsistencyReviewer unit tests |
| W2 Organizer | `sidecar/supervisor/organizer.py` | `organize_project_content()`: World routing, module pollution filter, exclusion log |
| W2 Organizer | `tests/test_w1_organizer.py` | Organizer unit tests |
| W3 Prompt | `sidecar/supervisor/pipeline_tools.py` | Tool contracts: `run_quality_review`, `run_fact_review`, `run_consistency_review`, `organize_project_content`, `rerun_targeted_window`, `repair_import_artifacts`, `write_proposal_package` |
| W3 Prompt | `tests/test_w1_pipeline_tools.py` | Pipeline tool contract tests |
| W4 Timeline | `src/ui-react/components/timeline/TimelineCanonicalAdapter.ts` | normalize canonical → renderer state |
| W4 Timeline | `src/ui-react/components/timeline/TimelineOperations.ts` | TimelineOperation union type + validator |
| W4 Timeline | `src/ui-react/components/timeline/TimelinePersistencePatch.ts` | patch type + `applyTimelinePatch` call |
| W4 Timeline | `src/ui-react/components/timeline/TimelineLabelPlacement.ts` | deterministic candidate-anchor scoring; bounding-box overlap check; hidden-label + tooltip fallback |
| W4 Timeline | `tests/e2e/p1/timeline_sync_roundtrip.spec.ts` | Drag/branch/anchor/fork/merge persist + reload round-trip + dense-label bounding-box assertions |
| W5 Inbox | no new files; existing `WorkbenchWorkspace.tsx` + `projectService.ts` |
| W5 Inbox | `tests/e2e/p1/workbench_import_package_repair.spec.ts` | Reviewer repair package accept/retry |
| W6 Verify | `communication/2026-06-01-w1-reviewer-organizer-verification-report.md` | PM report |
| W6 Verify | `dev_logs/2026-06-01-w1-reviewer-organizer-verification.md` | Dev log |

### Modified files (by owner window)

| Window | File | Change |
|---|---|---|
| W1 Reviewer | `sidecar/models/state.py` | **Minimal additive only**: add `reviewer_report: ReviewReport \| None = None` field to `ImportSupervisorState` (or equivalent TypedDict) if state needs to carry review output — no other types added here. All dataclass definitions (`ReviewReport`, `ReviewFinding`, etc.) live exclusively in `reviewers/schemas.py`. |
| W2 Organizer | `dev_docs/W1_IMPORT_COMPILER.md` | Update Stage list to include Organizer stage |
| Lead (integration patch) | `sidecar/workflows/w1_import.py` | Wire `organize_project_content` after reconcile, before proposal_write — **deferred to Lead integration patch after W2 organizer.py is reviewed and merged; W2 must NOT change this file directly** |
| W3 Prompt | `sidecar/supervisor/prompt_policy.py` | Add `reviewer_mode`, `rerun_scope`, `organizer_strictness` knobs to PromptPolicyPatch |
| W3 Prompt | `sidecar/supervisor/planner.py` | Add `_reviewer_findings_to_policy_patch()` mapper |
| W3 Prompt | `sidecar/supervisor/tools.py` | Register `run_quality_review`, `run_fact_review`, `run_consistency_review` as callable tools |
| W4 Timeline | `src/ui-react/store.ts` | Add `applyTimelineOperation(op: TimelineOperation)` that calls `projectService.applyTimelinePatch` |
| W4 Timeline | `src/ui-react/services/projectService.ts` | Add `applyTimelinePatch(projectDir, patch)` that persists branch/event mutations and saves |
| W4 Timeline | `src/ui-react/components/timeline/TimelineCanvas.tsx` | Replace direct state mutations in drag handlers with `store.applyTimelineOperation()` |
| W5 Inbox | `src/ui-react/components/WorkbenchWorkspace.tsx` | ProposalPackage card UI: source badge, risk badge, dependency summary, Accept/Retry |
| W5 Inbox | `src/ui-react/services/projectService.ts` | Extend `applyProposalPackageTransaction` to handle `source: "quality_reviewer" | "fact_reviewer" | "consistency_reviewer" | "organizer"` packages |

### Shared surfaces (require reservation notice)

| Surface | Who touches | What |
|---|---|---|
| `sidecar/models/state.py` | W1 Reviewer (field add only) | Add at most one field reference (`reviewer_report`) to `ImportSupervisorState`; **all schema dataclasses defined in `reviewers/schemas.py` only — no dual-source** |
| `sidecar/workflows/w1_import.py` | Lead integration patch (not W2) | Integration-sensitive main execution chain; W2 proposes the call-site in a handoff note; no large pipeline restructuring |
| `sidecar/supervisor/tools.py` | W3 Prompt | Register reviewer tools |
| `sidecar/supervisor/prompt_policy.py` | W3 Prompt | Add 3 new knobs |
| `src/ui-react/store.ts` | W4 Timeline | Add `applyTimelineOperation` action |
| `src/ui-react/services/projectService.ts` | W4 Timeline + W5 Inbox | `applyTimelinePatch` (W4) + reviewer package source (W5) |

---

## 4. Tool Contracts (Interface Ground Truth)

### 4.1 Reviewer Schemas (`sidecar/supervisor/reviewers/schemas.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

ReviewerKind = Literal["quality", "fact", "consistency"]
Verdict = Literal["pass", "warn", "needs_repair", "needs_orchestrator_rerun"]
Severity = Literal["low", "medium", "high"]
RerunScope = Literal["local_window", "entity_cluster", "timeline_branch", "world_category"]

@dataclass
class ReviewFinding:
    code: str           # e.g. "event_density_too_high"
    severity: Severity
    description: str
    affected_ids: list[str] = field(default_factory=list)

@dataclass
class RepairAction:
    action_type: str    # e.g. "move_world_item_category", "merge_characters"
    entity_id: str
    params: dict        # action-specific parameters
    rationale: str

@dataclass
class OrchestratorRequest:
    request_type: str   # "prompt_policy_patch" | "targeted_rerun"
    rerun_scope: RerunScope | None = None
    prompt_policy_patch: dict | None = None   # subset of PromptPolicyPatch knobs
    affected_window_ids: list[str] = field(default_factory=list)
    rationale: str = ""

@dataclass
class ZeroCostLedger:
    live_model_calls: bool = False
    full50_run: bool = False
    model_used: str | None = None

@dataclass
class ReviewReport:
    reviewer: ReviewerKind
    verdict: Verdict
    severity: Severity
    findings: list[ReviewFinding] = field(default_factory=list)
    local_repair_actions: list[RepairAction] = field(default_factory=list)
    orchestrator_requests: list[OrchestratorRequest] = field(default_factory=list)
    token_cost_ledger: ZeroCostLedger = field(default_factory=ZeroCostLedger)
```

### 4.2 Quality Reviewer inputs

```python
# QualityReviewer.review(state: dict) -> ReviewReport
# Reads from state keys only — no full source text, no model calls.
# Checks:
#   - event count vs chapter count (density flag if > 5 events/chapter average)
#   - mainline share (warn if > 80% of events on root branch)
#   - world model contamination (person names in world items, relationship items in world)
#   - empty world containers
#   - character card completeness (summary present, alias present for CJK imports)
#   - relationship evidence presence
```

### 4.3 Fact Reviewer inputs

```python
# FactReviewer.review(candidates: list[dict], evidence_index: dict, max_snippets: int, max_total_tokens: int) -> ReviewReport
# candidates: list of { "entity_id", "claim", "evidence_ref" }
# evidence_index: { segment_id -> snippet string } — pre-fetched small excerpts only
# Does NOT read full source text.
# LLM adapter interface is a stub: `_llm_check(claim, snippet) -> bool` returns True by default.
```

### 4.4 Consistency Reviewer inputs

```python
# ConsistencyReviewer.review(current_run_summary: dict, prior_run_summaries: list[dict], project_digest: dict) -> ReviewReport
# Checks:
#   - character names/aliases in current run vs prior runs (duplicate candidates)
#   - timeline branch ids in current run vs last accepted branches (continuity)
#   - world item titles in current run vs existing project world items (collision)
#   - relationship source/target ids vs known character ids (dangling)
```

### 4.5 Organizer Tool

```python
# organize_project_content(candidates: dict, taxonomy: dict | None = None) -> OrganizerOutput
# candidates: {
#   "characters": [...],
#   "events": [...],
#   "relationships": [...],
#   "world_candidates": [...],
#   "manuscript_notes": [...],
#   "timeline_architecture": {...},
#   "project_digest": {...}
# }
# Returns:
# {
#   "world_containers": [...],
#   "world_items": [...],
#   "excluded_items": [{ "entity_id", "reason", "suggested_module" }],
#   "merge_candidates": [...],
#   "proposal_packages": [...],
#   "warnings": [...]
# }
```

### 4.6 Timeline Operations (TypeScript)

```typescript
// src/ui-react/components/timeline/TimelineOperations.ts
export type TimelineOperation =
  | { type: 'move_event'; eventId: string; branchId: string; orderIndex: number; layoutHints?: Record<string, unknown> }
  | { type: 'move_branch_anchor'; branchId: string; startAnchor?: Anchor; endAnchor?: Anchor }
  | { type: 'update_branch_geometry'; branchId: string; geometry: BranchGeometry }
  | { type: 'merge_branch'; branchId: string; mergeTargetBranchId: string; mergeEventId: string }
  | { type: 'split_branch'; parentBranchId: string; forkEventId: string; newBranch: TimelineBranchDraft };

export type TimelinePersistencePatch = {
  updatedBranches: TimelineBranch[];
  updatedEvents: TimelineEvent[];
  warnings: string[];
};

// TimelineSyncValidator.validate(op: TimelineOperation, state: StoreState): ValidationResult
// Returns { ok: boolean; reason?: string; patch: TimelinePersistencePatch }
```

### 4.7 PromptPolicyPatch extended knobs

```python
# New knobs added to sidecar/supervisor/prompt_policy.py
# ALLOWLIST only — no raw prompt text accepted:
#   reviewer_mode: "quality" | "fact" | "consistency" | None
#   rerun_scope: "local_window" | "entity_cluster" | "timeline_branch" | "world_category" | None
#   organizer_strictness: "low" | "medium" | "high" | None
# Existing knobs remain unchanged:
#   event_density_strategy, topology_fidelity, world_model_scope, etc.
```

---

## 5. Task Packs for Parallel Windows

### Task Pack W1 — Reviewer Framework

**Goal:** Implement Quality, Fact, Consistency Reviewers in `sidecar/supervisor/reviewers/`.

**Owner paths:**
- `sidecar/supervisor/reviewers/*` (new)
- `tests/test_w1_reviewers_quality.py` (new)
- `tests/test_w1_reviewers_fact.py` (new)
- `tests/test_w1_reviewers_consistency.py` (new)

**Shared surface by reservation:**
- `sidecar/models/state.py` — touch only if `ImportSupervisorState` (or a global TypedDict) needs a field reference to carry review output (e.g., `reviewer_report: ReviewReport | None = None`). **All dataclass definitions live in `reviewers/schemas.py` exclusively — no dual-source.**

**Forbidden paths:** frontend, `w1_import.py`, timeline components, live API.

**Required tests (all zero-cost / deterministic):**
1. Quality catches event density > 5 events/chapter.
2. Quality catches mainline share > 80%.
3. Quality catches empty World containers.
4. Quality catches relationship missing evidence.
5. Fact catches synthetic claim mismatch using evidence snippet (mock LLM returns False).
6. Fact does NOT read `state["chunks"]` or any full-text field.
7. Consistency catches duplicate character across two import summaries.
8. Consistency catches branch continuity break (current run proposes new branch with unknown parentBranchId).

**Acceptance:** All 8 tests pass. `sidecar/.venv/bin/python -m pytest tests/test_w1_reviewers_*.py -q` → PASS.

---

### Task Pack W2 — Organizer Agent

**Goal:** Implement `organize_project_content()` in `sidecar/supervisor/organizer.py`.

**Owner paths:**
- `sidecar/supervisor/organizer.py` (new)
- `tests/test_w1_organizer.py` (new)
- `dev_docs/W1_IMPORT_COMPILER.md` — Stage 7.5 Organizer entry

**Forbidden paths:** `sidecar/workflows/w1_import.py` (integration-sensitive; W2 must not modify it directly — propose the exact call-site in handoff notes for Lead integration patch), frontend, timeline components, live API.

**Organizer rules (deterministic, CJK-aware):**
- Relationship graphs, event timelines, person/role-only entries → excluded, routed to their modules.
- `门派`/`宗门` → organization; `功法`/`法诀` → cultivation_method; `地名` → location; `阵营`/`势力` → faction.
- Named orgs like `七玄门` → world item (organization), not character candidate.
- `记名弟子`/`内门弟子` → excluded from cultivation_method; routed to system/concept or excluded with reason.
- Empty English starter containers removed.
- All exclusions emit `ExcludedItem { entity_id, reason, suggested_module }`.

**Required tests (all zero-cost):**
1. `七玄门` routes to organization world item, not character candidate.
2. `长春功` routes to cultivation_method.
3. `记名弟子` excluded from cultivation_method with reason.
4. `韩立` (person name) excluded from world items.
5. Relationship graph string excluded with reason `"module_owned_by_relationship"`.
6. Empty world containers removed before proposal output.
7. `categoryPath` and `parentId` present on world item proposals.
8. `excludedItems[].reason` is non-empty for every exclusion.

**Handoff note required:** W2 must include in its handoff artifact the exact proposed diff (call-site snippet) for wiring `organize_project_content` into `w1_import.py`; Lead applies it as a separate integration patch.

**Acceptance:** All 8 tests pass. `sidecar/.venv/bin/python -m pytest tests/test_w1_organizer.py -q` → PASS. `npm run ui:build` → PASS (no frontend change in this pack).

---

### Task Pack W3 — Prompt / Pipeline Toolization

**Goal:** Expose Reviewer findings as PromptPolicyPatch knobs; define pipeline tool registry callable by Orchestrator.

**Owner paths:**
- `sidecar/supervisor/pipeline_tools.py` (new)
- `sidecar/supervisor/prompt_policy.py` — add 3 knobs
- `sidecar/supervisor/planner.py` — add `_reviewer_findings_to_policy_patch()`
- `sidecar/supervisor/tools.py` — register `run_quality_review`, `run_fact_review`, `run_consistency_review`
- `tests/test_w1_pipeline_tools.py` (new)

**Depends on:** W1 Reviewer schemas (ReviewReport, RepairAction, OrchestratorRequest must be defined first).

**Forbidden paths:** frontend, timeline UI, live API, raw prompt text injection.

**Mapping rules:**
| Reviewer finding code | Policy patch |
|---|---|
| `event_density_too_high` + severity ≥ medium | `event_density_strategy = "sparse_turning_points"` |
| `mainline_share_too_high` | `topology_fidelity = "high"` |
| `world_contamination_high` | `world_model_scope = "world_only"`, `organizer_strictness = "high"` |
| `fact_mismatch_entity_cluster` | `rerun_scope = "entity_cluster"` |
| `duplicate_character_cross_import` | local repair merge, no rerun |

**Required tests (all zero-cost):**
1. `ReviewReport(findings=[ReviewFinding("event_density_too_high", "high")])` → patch contains `event_density_strategy="sparse_turning_points"`.
2. `ReviewReport(findings=[ReviewFinding("world_contamination_high", "high")])` → patch contains `world_model_scope="world_only"`.
3. Low-severity finding (`severity="low"`) → no orchestrator request generated.
4. Raw prompt text passed to policy patch → raises `ValueError`.
5. `run_quality_review` tool registered in tool registry with correct signature.
6. `rerun_targeted_window` requires non-empty `affected_window_ids` — empty list raises `ValueError`.

**Acceptance:** All 6 tests pass. `sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -q` → PASS.

---

### Task Pack W4 — Timeline Front/Back Consistency

**Goal:** All Timeline UI operations (drag, anchor, branch, fork/merge) persist via `projectService.applyTimelinePatch`; reload round-trips correctly.

**Owner paths:**
- `src/ui-react/components/timeline/TimelineOperations.ts` (new)
- `src/ui-react/components/timeline/TimelineCanonicalAdapter.ts` (new)
- `src/ui-react/components/timeline/TimelinePersistencePatch.ts` (new)
- `src/ui-react/components/timeline/TimelineCanvas.tsx` — replace direct mutations with `applyTimelineOperation`
- `src/ui-react/store.ts` — add `applyTimelineOperation(op)` action
- `src/ui-react/services/projectService.ts` — add `applyTimelinePatch(projectDir, patch)`
- `tests/e2e/p1/timeline_sync_roundtrip.spec.ts` (new)

**Shared surfaces by reservation:** `src/ui-react/store.ts`, `src/ui-react/services/projectService.ts`.

**Forbidden paths:** sidecar import pipeline (except schema compatibility), Workbench package accept, live API.

**Round-trip contract:**
```
drag event node → TimelineOperation { type: "move_event" }
  → TimelineSyncValidator.validate()
  → store.applyTimelineOperation(op)
  → projectService.applyTimelinePatch(dir, patch)
  → save to disk
  → reload project
  → event.branchId === original operation target
```

**BRANCH_RUNTIME_FIELDS** (`anchorStartPos`, `anchorEndPos`, `endAnchor`, `endMode`, `mergeEventId`, `mergeTargetBranchId`) must NOT be included in persistence patch — they are recomputed at render time.

**Required tests (Playwright, mocked IPC):**
1. Drag event to different branch → `branchId` persisted after reload.
2. Drag event within branch → `orderIndex` persisted after reload; `layoutHints` also persisted when set.
3. Branch anchor drag → `startAnchor` persisted after reload.
4. Branch geometry drag → `geometry` (x, y, width) persisted after reload.
5. Fork operation → new branch with `parentBranchId`/`forkEventId` persisted after reload.
6. Merge operation → `mergeTargetBranchId` + `mergeEventId` persisted after reload.
7. Reload after all operations → full topology identical (branch ids, event order, anchor positions).
8. `collectTimelineSyncEntityFieldMismatches` returns 0 warnings after clean round-trip (sync happy path — no unexplained warnings).
9. Dense label layout: 20 events on 3 branches → `TimelineLabelPlacement.checkOverlap()` returns 0 bounding-box intersections (unit-level assertion against the scoring algorithm output; no visual/pixel comparison required).
10. Hidden labels: when a label is demoted to hidden due to overlap, its full title is accessible via tooltip text (Playwright `.getAttribute("title")` or `aria-label` check on the hidden-label element).

**Acceptance:** All 10 tests pass. `npm run ui:build` → PASS. `npx playwright test tests/e2e/p1/timeline_sync_roundtrip.spec.ts` → PASS.

---

### Task Pack W5 — Inbox Package / Repair UX

**Goal:** ProposalPackage cards in Workbench show source badge, risk, dependency count, Accept/Retry; Reviewer repair packages use the same transaction path.

**Owner paths:**
- `src/ui-react/components/WorkbenchWorkspace.tsx` — ProposalPackage card UI
- `src/ui-react/services/projectService.ts` — extend `applyProposalPackageTransaction` for reviewer source types
- `tests/e2e/p1/workbench_import_package_repair.spec.ts` (new)

**Depends on:** W1 Reviewer schemas must define `source: "quality_reviewer" | "fact_reviewer" | "consistency_reviewer" | "organizer"`.

**Shared surfaces by reservation:** `src/ui-react/services/projectService.ts`.

**Forbidden paths:** sidecar reviewer implementation, timeline rendering, live API.

**UI requirements:**
- ProposalPackage card shows: source badge (w1_import / quality_reviewer / fact_reviewer / consistency_reviewer / organizer), risk badge (low/medium/high), entity type counts (N characters, N events, etc.), dependency count.
- Card is collapsed by default; expandable to show individual proposals.
- "Accept Package" button: disabled if package blocked; shows precise blocking edge reason in tooltip.
- "Retry Blocked" button visible when `lastBlockReason` is set; clears stale block reason on retry.
- Reviewer repair packages from `localRepairActions` are injected into inbox with `source = reviewer_type`.

**Required tests (Playwright, mocked IPC):**
1. Import package: all same-batch character + event proposals accept in one transaction.
2. Reviewer repair package: `move_world_item_category` repair action applies and does not mutate canonical data silently.
3. Package rollback: one blocked proposal causes entire package to roll back; project unchanged.
4. Cyclic refs: character A references event B, event B references character A → both pre-registered, package accepts.
5. Blocked reason displays character name + edge type in UI tooltip.
6. Retry blocked package re-attempts without requiring manual clear of `lastBlockReason`.

**Acceptance:** All 6 tests pass. `npm run ui:build` → PASS. `npx playwright test tests/e2e/p1/workbench_import_package_repair.spec.ts` → PASS.

---

### Task Pack W6 — Verification / PM Reporting

**Goal:** Validate all Windows 1–5 deliverables against user bug list; produce PM report.

**Owner paths:**
- `tests/e2e/p1/*` — may add new regression specs, must not modify business files
- `communication/2026-06-01-w1-reviewer-organizer-verification-report.md`
- `dev_logs/2026-06-01-w1-reviewer-organizer-verification.md`

**Forbidden paths:** sidecar core, projectService, timeline components (read only).

**Checklist to verify:**

| Item | Verify how |
|---|---|
| Quality Reviewer catches event density | `pytest test_w1_reviewers_quality.py` |
| Fact Reviewer is token-light | Assert no `state["chunks"]` read in FactReviewer |
| Consistency Reviewer catches duplicate character | `pytest test_w1_reviewers_consistency.py` |
| Organizer filters World Model contamination | `pytest test_w1_organizer.py` |
| PromptPolicyPatch mapping works | `pytest test_w1_pipeline_tools.py` |
| Timeline drag persists (branchId/orderIndex/layoutHints) | Playwright `timeline_sync_roundtrip.spec.ts` |
| Timeline branch geometry / fork anchor / merge anchor persisted | Playwright `timeline_sync_roundtrip.spec.ts` |
| Timeline sync happy path no unexplained warnings | Playwright roundtrip + sync check |
| Dense labels bounding boxes do not overlap | `TimelineLabelPlacement.checkOverlap()` unit assertion |
| Hidden labels preserve tooltip/full title | Playwright `timeline_sync_roundtrip.spec.ts` test item 10 |
| Inbox repair package accept/retry | Playwright `workbench_import_package_repair.spec.ts` |
| Package blocked reason readable | Playwright `workbench_import_package_repair.spec.ts` |
| No live API | Grep `ANTHROPIC_API_KEY`, `openai`, `requests.post` in new files |
| dev_docs updated | Check `W1_IMPORT_COMPILER.md` for Organizer stage |

---

## 6. Execution Ordering and Dependencies

```
Day 1 (can start immediately, parallel):
  W1 Reviewer framework (schemas.py, base.py, quality/fact/consistency reviewers)
  W2 Organizer agent (organizer.py + tests; w1_import.py wiring via Lead integration patch)
  W4 Timeline front/back consistency (TimelineOperations.ts, TimelineCanvas.tsx, store.ts, projectService.ts)

Day 2 (unblocked after W1 schemas are defined):
  W3 Prompt / Pipeline Toolization (needs ReviewReport schema from W1)
  W5 Inbox Package / Repair UX (needs reviewer source type from W1 schemas)

Day 3:
  W6 Verification (needs W1–W5 deliverables)
```

**Hard dependency edges:**
- W3 must not start implementing `_reviewer_findings_to_policy_patch` until W1 exports `ReviewReport` and `ReviewFinding`.
- W5 must not implement `source: "quality_reviewer"` routing until W1 exports that literal.
- W6 runs after all others; can write verification plan on Day 1.

---

## 7. Test Plan Summary

### Python (pytest, zero-cost, no live API)
```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_pipeline_tools.py -q
```
Expected: all pass.

### TypeScript build
```bash
npm run ui:build
```
Expected: 0 errors.

### Playwright (mocked IPC)
```bash
npx playwright test --config tests/playwright.config.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts tests/e2e/p1/workbench_import_package_repair.spec.ts --reporter=list
```
Expected: all pass.

### Regression guard (must stay green)
```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py tests/test_w1_quality_rubric.py tests/test_w1_supervisor_policy.py -q
npx playwright test --config tests/playwright.config.ts tests/e2e/p1/import_smoke_acceptance.spec.ts tests/e2e/p1/workbench_proposal_safety.spec.ts --reporter=list
```

---

## 8. Interfaces / Handoff Between Windows

| Producer | Consumer | Contract |
|---|---|---|
| W1 Reviewer (`schemas.py`) | W3 Prompt (policy mapping), W5 Inbox (source literal) | `ReviewReport`, `RepairAction`, `OrchestratorRequest` dataclasses |
| W2 Organizer (`OrganizerOutput`) | W5 Inbox (proposal packages from organizer), W3 Prompt (organizer_strictness knob trigger) | `OrganizerOutput.proposal_packages`, `OrganizerOutput.excluded_items` |
| W4 Timeline (`TimelineOperation`, `TimelinePersistencePatch`) | W6 Verification (round-trip test) | `applyTimelinePatch` persists and returns `roundTripVerified: bool` |
| W5 Inbox (`ProposalPackage` card source) | W6 Verification | Reviewer repair packages appear in Workbench with correct source badge |

---

## 9. Risks and Deferred Items

| Risk / Deferred Item | Severity | Mitigation / Plan |
|---|---|---|
| `sidecar/models/state.py` merge conflict | Low | W1 adds at most one field to ImportSupervisorState; all schema dataclasses live in `reviewers/schemas.py` only — no dual-source risk |
| `sidecar/workflows/w1_import.py` integration collision | Medium | W2 must NOT touch this file; Lead applies a single integration patch after W2 merges — serializes the risk |
| `src/ui-react/services/projectService.ts` touched by both W4 and W5 | Medium | W4 adds `applyTimelinePatch` (new function); W5 extends `applyProposalPackageTransaction` (existing function). No overlap if merged in that order. |
| `src/ui-react/store.ts` touched by W4 | Low | W4 adds one new action; no other window touches store.ts in this wave |
| Timeline round-trip: `BRANCH_RUNTIME_FIELDS` may grow | Low | `timelineSyncAnalysis.ts` already has the set; W4 must not remove existing fields |
| Dense Timeline label placement | **Resolved — P0 in W4** | W4 implements `TimelineLabelPlacement.ts` with deterministic candidate-anchor scoring; Playwright bounding-box assertion required |
| Dense label hidden tooltip | Low | If any label is demoted to hidden, full title must be accessible via tooltip (W4 test item 10) |
| Organizer LLM-readiness stub left incomplete | Low | Intentional deferral — deterministic first; stub interface comment in code is sufficient |
| Fact Reviewer RAG stub | Low | Intentional deferral — LLM adapter returns `True` by default; real RAG is future work |
| Import UI toggles (Manuscript / Relationship) | Medium | Explicitly deferred; no frontend changes in this wave |
| Character card enrichment | Low | W1 spec: compact drafts only; deep fields remain empty |
| Live `import_test11` re-run | Medium | Code is fixed; user must manually re-import or run repair script (deferred to PM decision) |

---

## 10. Final Acceptance Checklist (Lead Integrator)

- [ ] `sidecar/supervisor/reviewers/schemas.py` exists with `ReviewReport`, `ReviewFinding`, `RepairAction`, `OrchestratorRequest`, `ZeroCostLedger` — single source of truth for all reviewer types.
- [ ] `sidecar/supervisor/reviewers/quality_reviewer.py` catches event density > 5/chapter.
- [ ] `sidecar/supervisor/reviewers/quality_reviewer.py` catches mainline share > 80%.
- [ ] `sidecar/supervisor/reviewers/quality_reviewer.py` catches empty World containers.
- [ ] `sidecar/supervisor/reviewers/fact_reviewer.py` does NOT read full source text (`state["chunks"]`).
- [ ] `sidecar/supervisor/reviewers/consistency_reviewer.py` catches duplicate character across import summaries.
- [ ] Reviewer `localRepairActions` are emitted for small findings.
- [ ] Reviewer `orchestratorRequests` are emitted for medium/high severity.
- [ ] `sidecar/models/state.py` has at most one new field reference (e.g., `reviewer_report`); no duplicate dataclass definitions.
- [ ] `sidecar/supervisor/organizer.py` filters World Model pollution (person names, relationship graphs, scene beats).
- [ ] Organizer outputs `categoryPath` and `parentId` on world item proposals.
- [ ] W2 handoff includes proposed `w1_import.py` call-site snippet for Lead integration patch.
- [ ] `sidecar/supervisor/prompt_policy.py` accepts `reviewer_mode`, `rerun_scope`, `organizer_strictness` knobs.
- [ ] Raw prompt text rejected by policy patch with `ValueError`.
- [ ] `_reviewer_findings_to_policy_patch()` maps `event_density_too_high` → `sparse_turning_points`.
- [ ] Timeline drag event → `branchId`/`orderIndex`/`layoutHints` persisted after reload.
- [ ] Timeline branch anchor drag → `startAnchor` persisted after reload.
- [ ] Timeline branch geometry drag → `geometry` persisted after reload.
- [ ] Timeline fork → `parentBranchId`/`forkEventId` persisted after reload.
- [ ] Timeline merge → `mergeTargetBranchId`/`mergeEventId` persisted after reload.
- [ ] Timeline sync happy path: `collectTimelineSyncEntityFieldMismatches` returns 0 warnings (no unexplained warnings).
- [ ] `BRANCH_RUNTIME_FIELDS` NOT included in persistence patch.
- [ ] Dense label layout: `TimelineLabelPlacement.checkOverlap()` returns 0 bounding-box intersections for 20 events / 3 branches.
- [ ] Hidden labels: full title accessible via tooltip (`title` or `aria-label`) when label is demoted to hidden.
- [ ] Inbox ProposalPackage card shows source badge + risk badge.
- [ ] Blocked package shows precise blocking edge in UI.
- [ ] Blocked package Retry button clears stale `lastBlockReason`.
- [ ] Reviewer repair package enters Inbox as `source: "quality_reviewer"` package.
- [ ] All new files have zero-cost tests (no live API, no full50).
- [ ] `dev_docs/W1_IMPORT_COMPILER.md` updated with Organizer stage.
- [ ] `npm run ui:build` → PASS.
- [ ] All Python tests → PASS.
- [ ] All Playwright tests → PASS.
- [ ] `communication/` has PM-style verification report.

---

## 11. My Owner Files (Lead / Window 0)

- `communication/2026-06-01-w1-reviewer-organizer-lead-plan.md` ← this file
- `dev_docs/W1_IMPORT_COMPILER.md` — minor additive update (Organizer stage entry) after W2 lands
- `dev_docs/WORKFLOW_STATUS.md` — update W1 open gaps after all windows land
- `dev_docs/WORKSTREAM_BOARD.md` — add new task packs for this wave
- `dev_logs/` — integration log entry after verification

I own (integration patch, after W2 merges):
- `sidecar/workflows/w1_import.py` — apply W2's proposed call-site snippet to wire `organize_project_content` after reconcile

I do NOT own or directly edit:
- `sidecar/supervisor/tools.py` (W3 owns tool registration)
- `src/ui-react/components/timeline/*` (W4 owns)
- `src/ui-react/services/projectService.ts` (W4 + W5 own)
- `src/ui-react/store.ts` (W4 owns)
- `src/ui-react/components/WorkbenchWorkspace.tsx` (W5 owns)

---

*Report generated: 2026-06-01*  
*Branch: codex/w1-orchestrated-import-quality*  
*Architect: Codex (Claude Code, Window 0 Lead)*
