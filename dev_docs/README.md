# DevDocs Governance Index

## Purpose
This directory is the operating system for product, architecture, workflow, and delivery decisions in this repository.

Use this file first. It defines what is active, what is legacy, and which document wins when two docs disagree.

## Active Implementation Baseline
- Active app stack: `src/ui-react` + `src/electron` + `sidecar`
- Active runtime shape: Electron shell, React workspace UI, Zustand state, service-layer persistence, Python sidecar workflows
- Legacy/reference-only paths: `src/ui`, older prototype-era Python UI layers, and mixed-era planning docs kept only for historical context

## Source-of-Truth Registry
| Category | Canonical doc | Secondary docs | Notes |
|---|---|---|---|
| Governance and doc precedence | `README.md` | `DEV_RULES.md` | Start here every session. |
| Mandatory development rules | `DEV_RULES.md` | repo-root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | Agent entry docs must mirror this category, not redefine it. |
| Product boundary and active module inventory | `PRODUCT_SPEC.md` | `ARCHITECTURE.md`, `DATA_MODEL.md` | Use this for what the product is and what modules are active. |
| Runtime architecture and integration boundaries | `ARCHITECTURE.md` | `WORKFLOW_STATUS.md`, `FRONTEND_BACKEND_CHECKLIST.md`, `DATA_MODEL.md` | Use this for data flow and layer ownership. |
| Workflow status (W0-W7) | `WORKFLOW_STATUS.md` | `PHASE7_TEST_REPORT.md` | Use this for what is active, verified, stubbed, or still open. |
| Workflow/UI/backend integration mapping | `FRONTEND_BACKEND_CHECKLIST.md` | `WORKFLOW_STATUS.md` | Use this for UI action -> store -> bridge -> sidecar mapping. |
| UI behavior and acceptance rules | `UI_logic.txt` | `UX_rules.txt`, `UI_ROUTES.txt`, `TEST_SELECTORS.txt`, `TEST_PLAN.md` | This precedence remains strict for UI behavior only. |
| Data model and canonical storage rules | `DATA_MODEL.md` | `src/ui-react/models/project.ts`, `ARCHITECTURE.md` | Types in code are implementation truth; this doc is the operating summary. |
| Parallel worktree operating rules | `PARALLEL_WORKTREE_PROTOCOL.md` | `SHARED_SURFACES.md`, `TASK_PACK_TEMPLATE.md`, `WORKSTREAM_BOARD.md` | Every parallel task must attach to a task pack. |
| Execution order and delivery sequencing | `EXECUTION_PLAN.md` | `WORKSTREAM_BOARD.md` | Use this instead of older roadmap/planning docs. |
| Decision history | `DECISION_LOG.md` | commit history | Record durable decisions here when they affect future work. |

## Conflict Resolution
### Global rules
1. `README.md` decides which doc category is authoritative.
2. Within a category, the canonical doc wins over all secondary docs.
3. Implementation does not become canonical until the corresponding canonical doc is updated.
4. Legacy/reference docs may explain history, but they must not be used to define new work.

### UI behavior precedence
1. `UI_logic.txt`
2. `UX_rules.txt`
3. `UI_ROUTES.txt`
4. `TEST_SELECTORS.txt`
5. `TEST_PLAN.md`

## Active vs Legacy Docs
### Active docs
- `README.md`
- `DEV_RULES.md`
- `PRODUCT_SPEC.md`
- `ARCHITECTURE.md`
- `DATA_MODEL.md`
- `WORKFLOW_STATUS.md`
- `FRONTEND_BACKEND_CHECKLIST.md`
- `EXECUTION_PLAN.md`
- `PARALLEL_WORKTREE_PROTOCOL.md`
- `SHARED_SURFACES.md`
- `TASK_PACK_TEMPLATE.md`
- `WORKSTREAM_BOARD.md`
- `DECISION_LOG.md`
- `UI_logic.txt`
- `UX_rules.txt`
- `UI_ROUTES.txt`
- `TEST_SELECTORS.txt`
- `TEST_PLAN.md`

### Reference-only docs
- `ROUTES_AND_UI.md`
- `UI_CONTRACT.md`
- `UI_IMPLEMENTATION_CHECKLIST.md`
- `UI_LAYOUT_RULES.md`
- `UI_INTERACTION_RULES.md`
- `UI_PAGE_CONTENT.md`
- `DESIGN_SYSTEM.md`
- `DEV_UI_TOKENS.md`
- `PHASE7_TEST_REPORT.md`
- `langgraph.md`

### Historical/legacy docs
- `PROJECT_ROADMAP_AND_ANALYSIS.md`
- `plan.md`

## Mandatory Update Rules
Update the canonical docs in the same change whenever you modify:
- Route inventory, workspace ownership, or shell behavior
- Shared state boundaries, persistence boundaries, or workflow bridges
- Workflow status, trigger availability, or integration coverage
- Task allocation rules, write-scope ownership, or shared-surface coordination rules
- Durable architecture or planning decisions that future agents must reuse

## New-Agent Read Order
1. `dev_docs/README.md`
2. `dev_docs/DEV_RULES.md`
3. Category docs for the task:
   - product/architecture -> `PRODUCT_SPEC.md`, `ARCHITECTURE.md`
   - UI behavior -> `UI_logic.txt`, `UX_rules.txt`, `UI_ROUTES.txt`
   - workflows -> `WORKFLOW_STATUS.md`, `FRONTEND_BACKEND_CHECKLIST.md`
   - parallel delivery -> `PARALLEL_WORKTREE_PROTOCOL.md`, `SHARED_SURFACES.md`, `WORKSTREAM_BOARD.md`

## Documentation Interfaces
### Source-of-Truth Registry
`category -> canonical doc -> secondary docs -> notes`

### Decision Log Entry
- `date`
- `id`
- `decision`
- `rationale`
- `impact`
- `supersedes`
- `status`

### Workstream Exit Criteria
- deliverable completed
- required tests passed
- required docs updated
- handoff artifacts published
