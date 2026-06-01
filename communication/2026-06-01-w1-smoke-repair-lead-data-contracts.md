# W1 Smoke Repair — Lead Data Contracts and Worker Conflict Matrix

**Date:** 2026-06-01  
**Branch:** `codex/w1-orchestrated-import-quality`  
**Author:** Claude Code (Lead Integration Manager session)  
**Scope:** Canonical type contracts and worker path ownership for W1 smoke repair iteration

---

## Purpose

This document is the single source of truth for:
- Which files each worker owns and which are forbidden
- The canonical data field contracts workers must implement and consume
- Worker dispatch sequencing

All workers must read this document before implementing changes.

---

## Worker Conflict Matrix

| Worker | Owned Paths | Shared Surfaces (coordinate before editing) | Forbidden |
|--------|------------|---------------------------------------------|-----------|
| **Lead (done)** | `models/project.ts`, `projectService.ts` schema metadata only | — | Prompt templates, W1 graph, WorldWorkspace |
| **A — Project Loader** | `projectService.ts`, `models/project.ts`, `WritingWorkspace.tsx`, `tests/e2e/p1/writing_manuscript_import_display.spec.ts` | `projectService.ts` — coordinate with D, E before editing | sidecar |
| **B — W1 Manuscript** | `sidecar/workflows/w1_import.py` (manuscript nodes only), `tests/test_w1_import_compiler.py` | `w1_import.py` — coordinate with C on shared graph changes | Frontend files |
| **C — Timeline Architect** | `sidecar/workflows/w1_import.py` (timeline nodes, branch inference), `sidecar/prompts/w1_prompts.py`, `sidecar/supervisor/prompt_policy.py`, `tests/test_w1_import_compiler.py` | `w1_import.py` — coordinate with B | Frontend files |
| **D — World Hierarchy** | `sidecar/supervisor/organizer.py`, `models/project.ts`, `WorldWorkspace.tsx`, `projectService.ts` (worldItem hydration normalization only), `tests/test_w1_organizer.py` | `projectService.ts`, `models/project.ts` — coordinate with A, E | Timeline files |
| **E — Character Dedupe** | `sidecar/supervisor/reviewers/quality_reviewer.py`, `sidecar/supervisor/tools.py`, `projectService.ts` (proposal apply path only), `tests/test_w1_reviewers_quality.py`, `tests/e2e/p1/workbench_reviewer_repair_package.spec.ts` | `projectService.ts`, `tools.py` — coordinate with A, D | organizer.py |
| **F — Token/Cost UX** | `sidecar/workflows/w1_import.py` (ledger emit only), `sidecar/routers/workflows.py`, `src/ui-react/services/electronApi.ts`, `src/ui-react/store.ts`, `src/ui-react/components/ImportWorkflow.tsx` | `store.ts` — coordinate with A if both touch import state | project loader |
| **G — Architecture** | `communication/` report, `dev_docs/ARCHITECTURE.md`, `dev_docs/DATA_MODEL.md` (after Lead approval only) | — | All core product code without Lead approval |
| **H — Verification** | `communication/` report only | — | All product code |

### Sequencing Rules

1. **Lead patch first** (done). Type contracts now in `models/project.ts`.
2. **Worker A next** (unblocks UI smoke trust).
3. **Workers B + C in parallel** (both own `w1_import.py` — must not edit the same function simultaneously; B owns manuscript nodes, C owns timeline/branch nodes).
4. **Workers D + E in parallel** (both touch `projectService.ts` — D owns worldItem hydration path, E owns character proposal apply path).
5. **Worker F** after A (avoids store.ts collision).
6. **Worker H** after all implementation workers have final patches.

---

## Canonical Data Contracts

### 1. `WorldItem` — NEW optional fields (added by Lead, now in `models/project.ts`)

```typescript
interface WorldItem {
  // ... existing fields ...
  categoryPath?: string[];      // materialized path for hierarchy, e.g. ["世界模型", "功法与术法", "长春功"]
  parentId?: string | null;     // parent container id or parent world item id
  importCategoryKey?: string;   // raw import category key (e.g. "item", "organization", "location")
}
```

W1 already writes `categoryPath` in proposals (`w1_import.py` line 4063). Worker D must:
- Ensure `organizer.py` also populates `categoryPath` (already done at line 834) and populates `parentId` (currently always `None` — needs fix).
- Render hierarchy in `WorldWorkspace.tsx` by grouping on `categoryPath[1]` within each container.
- Filter containers named `人物关系图` and `事件时间线`.

### 2. `TimelineEvent` — NEW optional fields (added by Lead, now in `models/project.ts`)

```typescript
interface TimelineEvent {
  // ... existing fields ...
  globalOrderIndex?: number;    // absolute source order across all chapters (0-based)
  chapterNumber?: number;       // parsed chapter number where this event appears
  sourceChunkIds?: string[];    // chunk IDs from manuscript that generated this event
  sourceOrder?: number;         // within-chapter source position (0-based)
}
```

W1 already writes `globalOrderIndex` (`w1_import.py` line 3473). Worker C must:
- Ensure all events carry `globalOrderIndex`, `chapterNumber`, `sourceChunkIds`, `sourceOrder`.
- Fix branch ID generation to never use world category values (`item`, `location`, etc.).
- Strengthen density policy so only irreversible state changes become canonical events.

### 3. Reviewer Repair Proposal Operation Schema (Worker E must fix)

Current broken format emitted by `_collect_repair_proposals()` in `tools.py`:
```python
"operations": [{"type": action.get("action_type"), ...action.get("params", {})}],
```

Required executable format for frontend `applyProposalOperation()`:
```typescript
{
  op: 'update' | 'create' | 'delete',
  entityType: 'character' | 'world_item' | 'timeline_event',
  entityId: string,
  fields: Record<string, unknown>
}
```

Worker E must update `_collect_repair_proposals()` in `sidecar/supervisor/tools.py` to emit `op`, `entityType`, `entityId`, `fields` keys.

### 4. Token Cost Ledger Schema (Worker F must implement)

Sidecar must emit in workflow status:
```python
{
  "estimated_input_tokens": int,
  "estimated_output_tokens": int,
  "estimated_total_tokens": int,
  "prompt_window_count": int,
  "model": str,
  "active_api_calls": int,
  "actual_usage": {"input_tokens": int, "output_tokens": int} | None
}
```

Frontend `ImportWorkflow.tsx` must render this without exposing API keys or provider credentials.

### 5. `NarrativeProject` Split-File Hydration (Worker A must verify)

`projectService.loadProject()` reads split files at:
- `writing/chapters/*.json` → `project.chapters`
- `writing/scenes/*.meta.json` + `*.md` → `project.scenes`
- `entities/characters/*.json` → `project.characters`
- `entities/timeline/event_*.json` → `project.timelineEvents`
- `entities/timeline/branches.json` → `project.timelineBranches`
- `entities/world/item_*.json` and `entities/world/world_*.json` → `project.worldItems`
- `entities/world/containers.json` → `project.worldContainers`
- `entities/relationships.json` → `project.relationships`

Code exists at lines 802–826 of `projectService.ts`. **Worker A must verify this actually works end-to-end** — that `WritingWorkspace` renders chapters from `project.chapters` correctly, that starter `chap_1`/`scene_1` is hidden when imported chapters exist, and that chapters sort by `orderIndex`.

---

## What the Lead Does NOT Own

The following are out-of-scope for the Lead patch and must not be touched:
- Timeline branch inference logic (`_timeline_lane_key`, `_timeline_theme_key`)
- W1 prompt templates (`w1_prompts.py`)
- WorldWorkspace rendering
- Character dedupe logic
- Token cost sidecar ledger
- W0–W7 orchestrator architecture (Worker G report only)
