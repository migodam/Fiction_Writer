# W0 Architecture Contract — 2026-06-06

> **Architecture-only contract. No implementation code. No git commands. Workers must produce Investigation Reports before any coding begins.**

---

## Section 1: Baseline State

**Current HEAD at contract time:** `2bf0cd6` (full: `2bf0cd690d55cff18f4ebff6b0b607383326d98e`)
**Branch:** `codex/w1-orchestrated-import-quality`

**BASELINE_FREEZE_HASH:** `[TBD — Lead records after human confirms commit scope and runs freeze]`

All workers fork from **BASELINE_FREEZE_HASH**, not from the current dirty HEAD.

### Dirty File Classification — Human/Codex Confirmation Required Before Any Commit

The repo has 25 tracked-modified files + 24 untracked files. This is a classification proposal. Lead must not run `git add` or `git commit` until the human confirms the exact scope.

#### Category A — Product Code Changes (tracked modified)

Completed P0 repair work. Require zero-cost gate to pass before staging.

| File | Prior-round purpose | Confirm before staging |
|------|-------------------|----------------------|
| `sidecar/models/state.py` | TypedDict schema for supervisor state | Does it contain only completed/tested changes? |
| `sidecar/routers/workflows.py` | W1 router endpoints | Same |
| `sidecar/supervisor/organizer.py` | classify_world_item + reclassify repair | Covered by test_w1_organizer.py |
| `sidecar/supervisor/policy.py` | Hard-fail guard + extraction loop budget guard | Covered by test_w1_supervisor_policy.py |
| `sidecar/supervisor/tools.py` | qa_review activity events + pipeline_tools reclassify | Covered by tests |
| `sidecar/workflows/w1_import.py` | Manuscript pipeline, ManuscriptNode projection | Covered by import tests |
| `sidecar/workflows/w1_run_events.py` | Activity feed, token ledger | Covered by test_w1_token_ledger.py |
| `src/ui-react/components/ImportWorkflow.tsx` | Granularity presets UI | Covered by import_workflow_presets.spec.ts |
| `src/ui-react/components/graph/CharacterRelationshipFlow.tsx` | Radial layout + edge label boxes | Covered by character_relationship_flow_layout.spec.ts |
| `src/ui-react/models/project.ts` | ManuscriptNode type, world category fields | Schema change — Lead reviews before staging |
| `src/ui-react/services/electronApi.ts` | IPC bridge changes | Is bridge contract stable? |
| `src/ui-react/services/projectService.ts` | Manuscript persistence, undo boundary | Covered by writing_manuscript_import_display tests |
| `src/ui-react/store.ts` | Undo stack, moveWorldItemToCategory, granularity slice | Covered by global_undo.spec.ts |
| `communication/2026-06-05-w1-post-smoke-defect-repair-claude-prompts.md` | Worker prompts (flag: may be duplicate of committed version) | Verify not duplicate |
| `tools/w1_import_diagnostics.py` | Diagnostics tool | Confirm: completed, not WIP |

#### Category B — Test Changes (tracked modified)

Stage only alongside their Category A counterparts.

| File | Coverage |
|------|---------|
| `tests/e2e/p1/global_undo.spec.ts` | Undo transaction model |
| `tests/e2e/p1/import_activity_status.spec.ts` | Activity feed |
| `tests/e2e/p1/import_token_cost.spec.ts` | Token billing |
| `tests/e2e/p1/import_workflow.spec.ts` | Import granularity |
| `tests/e2e/p1/workbench_reviewer_repair_package.spec.ts` | Reviewer repair package |
| `tests/e2e/p1/writing_manuscript_import_display.spec.ts` | Manuscript display |
| `tests/test_w1_organizer.py` | Organizer classify/reclassify |
| `tests/test_w1_reviewers_quality.py` | Quality reviewer |
| `tests/test_w1_supervisor_policy.py` | Policy loop |
| `tests/test_w1_token_ledger.py` | Token ledger |

#### Category C — Untracked Communication / Dev Logs (new files)

Project history. Stage each by exact path — no globs. Stage candidates:

- `communication/README.md`
- `communication/2026-06-05-w2-import-granularity-token-billing-report.md`
- `communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md`
- `communication/2026-06-06-w1-import-p0-bug-checklist.md`
- `communication/2026-06-06-w1-live-smoke-runner-and-hardfail-report.md`
- `communication/2026-06-06-w7-post-smoke-final-qa-report.md`
- `communication/2026-06-06-w1-deep-diagnostic-multiagent-flow.md`
- `communication/2026-06-06-current-state-rollup.md`
- `communication/2026-06-06-merged-evidence-rollup.md`
- `communication/2026-06-06-task-completion-audit.md`
- `communication/2026-06-06-orchestrator-design-and-prompt-hardening-addendum.md`
- `communication/2026-06-06-next-wave-execution-guide-and-solution-architecture.md`
- `communication/2026-06-06-w0-architecture-contract.md` (this file)
- `dev_logs/2026-06-06-*.md` (all — confirm each individually)

#### Category D — Untracked New Tests and Tools

Require test gate before staging.

| File | Covers |
|------|--------|
| `tests/e2e/p1/character_relationship_flow_layout.spec.ts` | Graph radial layout |
| `tests/e2e/p1/import_workflow_presets.spec.ts` | Granularity presets |
| `tests/test_w1_import_artifact_quality.py` | Import artifact quality |
| `tests/test_w1_live_smoke_runner.py` | Smoke runner |
| `tools/w1_live_smoke_10ch.py` | 10-chapter runner tool |

#### Category E — Must NOT Be Staged

| File | Reason |
|------|--------|
| `docs/superpowers/` | Always excluded — plugin internals |
| Playwright trace/video artifacts | Test runtime artifacts |
| `.claude/` files | Session internals |
| API keys or `.env` content | Security |

### Baseline Freeze Protocol

Before any worker forks:
1. Human/Codex reviews this classification and confirms exact files to stage.
2. Lead runs zero-cost gate: `pytest tests/test_w1_*.py -q --tb=short && npm run ui:build`
3. Lead stages only confirmed files **by exact path** — no directory globs.
4. Lead commits and records resulting hash as **BASELINE_FREEZE_HASH**.
5. All workers fork from that hash.

---

## Section 2: Five-Window Compression

| Window | Name | Mission |
|--------|------|---------|
| **W0** | Lead Architecture | Product ontology, merge gates, shared-surface arbitration, review gates. No implementation. |
| **W1** | Backend Import Quality | Chapter split/manuscript contract, supervisor lifecycle, reviewer pipeline, bounded LLM planner (direction set here; implementation after Investigation Report) |
| **W2** | Character / Relationship / Command UI | Character dossier model, custom attributes, duplicate merge, English-tag origin, right-click command registry, relationship organization, typed clipboard |
| **W3** | World / Timeline / Graph | World stable-ID folder tree (Notebook/Folder/Item), drag/drop nesting, undo transaction model (command/patch), relationship graph layout |
| **W4** | QA + Docs | Playwright gap review, Electron acceptance matrix, communication index, docs consolidation (no delete without Lead approval) |

---

## Section 3: Mandatory Worker Protocol

### Step 1: Read Section 0.1 First

Every worker must read `communication/2026-06-06-w1-next-wave-multiagent-claude-plan.md` **Section 0.1 User Intent To Preserve** before any other file. The Investigation Report must open with the verbatim user intent bullets that apply to that worker's scope.

**Rejection criterion:** Investigation Report without Section 0 confirmation is returned without review.

### Step 2: Investigation Report Template

```markdown
# Investigation Report — [Worker Name] — [Date]

**BASELINE_FREEZE_HASH:** [hash]
**Worker:** W[N] — [Name]

## 0. User Product Intent (from Section 0.1)
[Verbatim bullets from Section 0.1 that apply to this worker's scope]
[Confirmation: "This report addresses [X], not a shallow patch of [Y]"]

## 1. Product Intent
What should this feature/module do for a Chinese novelist using the app?

## 2. Current Behavior Evidence
### UI Evidence (screenshot description or Playwright locator)
### Artifact Evidence (JSON file paths + relevant contents)
### Storage Evidence (what is on disk at project/system/imports/)
### Code Evidence (file:line references to the broken paths)
### Reproduction Steps

## 3. Root Cause Chain
Level 1 (user-visible): ...
Level 2 (frontend rendering): ...
Level 3 (store/service): ...
Level 4 (sidecar/pipeline): ...
Level 5 (data model/prompt): ...

## 4. External References
[Library docs, algorithms, competing tools — use context7 MCP or brave-search MCP]

## 5. Proposed Architecture
### Data Model Changes (exact TypedDict / TypeScript interface diffs)
### Algorithm (explicit pseudocode or complexity-annotated description)
### Frontend Changes (component name, data-testid contracts)
### Backend Changes (function signatures + return types)
### Prompt Changes (if any, shown as diff)

## 6. Rejected Alternatives (why not chosen)

## 7. Implementation Prompt Draft

## 8. Acceptance Criteria
### Must Pass (zero-cost: exact pytest test names)
### Must Pass (Playwright: exact spec file names + test descriptions)
### Must-Fail-Before (tests that currently fail, proving right target)
### Must-Not-Pass-If (invariants that must never be true)
### Deferred (explicitly out-of-scope, with reason)
```

### Step 3: Lead Review

Lead reviews Investigation Reports on architecture-critical surfaces before coding.

**Rejection criteria:**
- Section 0 missing or superficial
- No real artifact/code evidence
- Shallow UI patch when canonical model is wrong
- Wrong source-of-truth identified
- World category shell game (`categoryPath` retained as canonical identity)
- Snapshot-based undo patchwork (not command/patch model)
- Reviewer theater (reports without proof of repairs applied)
- No tests, no external research
- Docs deleted without Lead approval

---

## Section 4: Shared-Surface Ownership Matrix

| Surface | Owner | Merge Order | Rule |
|---------|-------|-------------|------|
| `sidecar/workflows/w1_import.py` | **W1 only** | — | No other window. Architecture changes need Lead approval. |
| `sidecar/routers/workflows.py` | **W1 only** (Lead approval) | — | Patch plan submitted; Lead reviews. |
| `sidecar/models/state.py` | **W1 only** (Lead approval) | — | TypedDict changes require Lead review + test regeneration. |
| `sidecar/supervisor/organizer.py` | **W1 only** | — | W3 coordinates through W1 if organizer output needs new world ID fields. |
| `sidecar/supervisor/policy.py` | **W1 only** | — | Stage order and planner integration owned exclusively by W1. |
| `src/ui-react/models/project.ts` | **W2 primary, W3 secondary** | W2 → W3 | Lead reviews schema changes. W3 adds world folder fields only after W2 merges. |
| `src/ui-react/store.ts` | **W3 primary** | W1 slice → W2 slice → W3 slice | Each window isolates its named slice. Lead applies overlapping changes. |
| `src/ui-react/services/projectService.ts` | **W1 → W3 → W2** (serial) | W1 first | W1: manuscript/import. W3 rebases: world/undo. W2 rebases: character. |
| `src/ui-react/services/electronApi.ts` | **W1 or W3 only** | — | Only if bridge contract adds a new IPC channel. |
| `src/ui-react/components/graph/CharacterRelationshipFlow.tsx` | **W3 only** | — | W2 adds data model; W3 owns rendering. |
| `src/ui-react/components/CharactersWorkspace.tsx` | **W2 only** | — | Note: filename has trailing `s` — `CharactersWorkspace.tsx`. |
| `src/ui-react/components/WorldWorkspace.tsx` | **W3 only** | — | World folder tree UI. |
| `communication/` | All write; W4 may create index | — | No deletion/move without Lead approval. |
| `dev_docs/` | **W4 owns consolidation** | — | No archive/delete without Lead approval. |

---

## Section 5: Review-Before-Coding Gates

| Window | Gate |
|--------|------|
| **W1** | Investigation Report → Lead review → **REQUIRED** before any implementation |
| **W2** | Investigation Report required. Lead review **REQUIRED** if touching `project.ts` schema, relationship ontology, command registry, or `electronApi.ts` |
| **W3** | Investigation Report → Lead review → **REQUIRED** before any implementation |
| **W4** | Investigation Report required. Lead review **REQUIRED** before any docs consolidation. No live provider without explicit approval. |

---

## Section 6: Merge Order

**Serial:** W1 backend → W2 entity/command UI → W3 algorithms → W4 QA/docs

No window begins merge until the prior window passes full gate (pytest + npm run ui:build + targeted Playwright).

Sub-order:
- `store.ts`: W1 slice → W2 slice → W3 slice
- `projectService.ts`: W1 → W3 rebase → W2 rebase
- `project.ts`: W2 → W3 rebase

---

## Section 7: Orchestrator Architecture Direction

**Decision: Option B — Bounded PlannerProposal-driven**

This is a direction decision, not an implementation spec. W1's Investigation Report defines the implementation after code review.

### Infrastructure Already Built (W1 must inspect and confirm)

| Component | File:Lines |
|-----------|-----------|
| `PlannerProposal` TypedDict (10-field schema) | `state.py:196–213` |
| `validate_planner_proposal()` (allowlist + bounds) | `planner.py:127–249` |
| `planner_proposal_to_import_plan()` (deterministic conversion) | `planner.py:~260` |
| `validate_import_plan()` (final safety gate) | `state.py:972–1028` |
| `build_planner_proposal_prompt_context()` | `planner_llm.py:51–86` |
| `parse_planner_proposal_json()` (parse + validate) | `planner_llm.py:89–109` |
| `generate_planner_proposal_stub()` (zero-cost test) | `planner_llm.py:112–141` |
| **`generate_planner_proposal_live()`** | **MISSING** |
| Live mode currently | `policy.py:222–236` — hard-fails without model call |

### Allowed LLM Planner Decisions

- `proposed_source_type` — from known frozenset
- `proposed_granularity_profile` — field overrides within numeric bounds + enum frozensets
- `proposed_window_strategy` — known safe keys only; numeric bounds
- `proposed_tool_overrides[tool].prompt_granularity` — per-tool allowlist frozenset
- `prompt_variant_preferences` — per-tool variant allowlist
- `prompt_policy_patch` — boolean knobs + `world_boundary_strictness` enum

### Forbidden LLM Planner Decisions (forever deterministic)

- Stage order (hardcoded `policy.py:850–988`)
- Raw prompt text injection (rejected `planner.py:206`)
- Adding/removing tools
- `stop_on_api_402=False`
- `dynamic_prompt_edits_allowed=True`
- `proposal_gate_required=False`
- Out-of-range numerics or unknown variant keys

### W1 Must Answer in Investigation Report

1. Which model for the planner, and how is it configured separately from extraction?
2. What prompt structure does `build_planner_proposal_prompt_context` need to produce?
3. How does `generate_planner_proposal_live` fail gracefully without cascading to extraction?
4. What zero-cost tests prove no proposal can bypass any safety gate?

---

## Section 8: Non-Negotiable Product Invariants

1. **Source text immutability:** LLM output must not contain full chapter bodies. Source spans are the canonical record.
2. **Chinese-first user-visible labels:** All user-visible names, tags, relationship types must be Chinese for Chinese source novels. English enum keys are internal only.
3. **Proposal gate mandatory:** `proposal_gate_required=True` always.
4. **API 402 hard stop:** `stop_on_api_402=True` always. No retry, no fallback.
5. **No fake success:** Extraction failure → `hard_fail` → pipeline stops before `proposal_write`.
6. **Reviewer repairs visible:** Non-empty reviewer reports after real import; repairs appear in Workbench, never silently applied.
7. **Undo granularity:** One Cmd+Z = one user operation. Import-accept is a transaction boundary.
8. **World stable IDs:** World categories use stable `id` fields as canonical identity. `categoryPath` is derived display only.
9. **No docs deletion without Lead approval:** W4 may create index/rollup; may not delete or archive.
10. **No live API calls without explicit approval:** Zero-cost fixtures only in all worker windows.

---

## Section 9: Hard Constraints (All Workers)

- No full50 run.
- No live API/model calls without explicit user approval.
- Stop on 402, no retry, no fallback.
- Do not stage `docs/superpowers/`, traces, benchmarks, API keys, `.claude` files.
- Record `BASELINE_FREEZE_HASH` in every worker report header.
- Open every Investigation Report with Section 0.1 user intent confirmation.
- No implementation begins on architecture-critical surfaces until Investigation Report is Lead-approved.
