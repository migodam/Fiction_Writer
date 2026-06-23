# Worker G — Orchestrator & Data Architecture Research Log

**Date:** 2026-06-01  
**Branch:** codex/w1-orchestrated-import-quality  
**Worker:** G (Architecture)

---

## Work Performed

1. Read `dev_docs/README.md`, `dev_docs/DEV_RULES.md`, `dev_docs/ARCHITECTURE.md`, `dev_docs/DATA_MODEL.md`
2. Read `communication/2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md` and all 2026-05-31 and 2026-06-01 communication files
3. Explored `sidecar/workflows/` (W0-W7 implementations), `sidecar/supervisor/` (policy, tools, organizer, tool_registry), `sidecar/models/state.py`, `sidecar/shared/`
4. Read `sidecar/workflows/w1_run_events.py` (activity feed reference implementation, 141 lines)
5. Read `tests/test_w1_organizer.py` (test pattern: inline TypedDict construction, zero mocks, zero LLM calls)
6. Read `sidecar/routers/status.py` — confirmed `/workflow/status` returns HTTP 501
7. Identified 7 workflow architecture gaps and 5 data structure limitations

---

## Key Findings

### Workflow Architecture Gaps

| Location | Finding |
|----------|---------|
| `sidecar/routers/status.py:18` | `/workflow/status` raises `HTTPException(501)` — completely unimplemented |
| `sidecar/workflows/w1_run_events.py:71-78` | `cancel_requested()` exists but no LangGraph node in any workflow checks it |
| `sidecar/models/state.py:32` | W0 status: 5-value literal; W1: 4-value; W3: raw `str`; W4-W7: 3-value — no shared schema |
| `sidecar/routers/orchestrator.py` | W0 session state in in-memory dict — lost on sidecar restart |
| `sidecar/routers/workflows.py` | W3 session state in separate in-memory dict — lost on sidecar restart |
| `sidecar/supervisor/tools.py` | `qa_review` and `proposal_write` never call `organize_project_content()` from `organizer.py` |
| `sidecar/supervisor/tools.py` | Reviewer repair proposals emit `{"type": action_type, ...}` but frontend expects `{op, entityType, entityId, fields}` |

### Data Structure Gaps

| Structure | Gap |
|-----------|-----|
| All entity files | `orderIndex: int` — gap compression requires renumbering all siblings; no fractional insert |
| All entity files | `linkedXIds` arrays exist but no reverse index — delete-safety check requires full scan |
| `system/index-cache.json` | Exists but only partially populated; no guaranteed rebuild on project load |
| Timeline events | `branchId` per event but no branch DAG — topology traversal requires scanning all events |
| World items | `categoryPath`/`parentId` per item but no pre-built hierarchy index |

### W1 Activity Feed as Reference Pattern

`w1_run_events.py` is the design template for a unified event feed:
- In-memory dict keyed by `session_id`
- `ensure_session()`, `append_event()`, `list_events(after=N)`, `session_status()`
- Secret key redaction built in
- `mark_cancel_requested()` / `cancel_requested()` already present — just not consumed

All other workflows can reuse the same module or adopt the same pattern.

---

## Deliverables Produced

- `communication/2026-06-01-worker-g-orchestrator-data-architecture-report.md` — full architecture proposal with Mermaid diagrams, tradeoff table, implementation roadmap, and worker recommendations
- Proposed `sidecar/models/workflow_contract.py` — 3 TypedDicts (`WorkflowStatus`, `ActivityEntry`, `TokenLedger`) with full code in the report
- Proposed `sidecar/shared/s5_reference_graph.py` — `ReferenceGraph` class with full code in the report
- Proposed `sidecar/shared/s6_sequence_order.py` — 3 pure functions (`midpoint`, `needs_rebalance`, `rebalance`) with full code in the report

---

## Files Consulted

```
dev_docs/README.md
dev_docs/DEV_RULES.md
dev_docs/ARCHITECTURE.md
dev_docs/DATA_MODEL.md
communication/2026-06-01-w1-smoke-defect-analysis-and-repair-plan.md
communication/2026-05-31-w1-import-test11-delivery-report.md
communication/2026-06-01-w1-lead-integration-codex-acceptance-addendum.md
communication/2026-06-01-w1-lead-integration-patch-report.md
communication/2026-06-01-w1-reviewer-organizer-codex-acceptance-review.md
sidecar/workflows/w0_orchestrator.py (453 lines)
sidecar/workflows/w1_import.py (5653 lines)
sidecar/workflows/w1_run_events.py (141 lines)
sidecar/workflows/w2_manuscript_sync.py (412 lines)
sidecar/workflows/w3_writing_assistant.py (404 lines)
sidecar/workflows/w4_consistency_check.py (405 lines)
sidecar/workflows/w5_simulation.py (387 lines)
sidecar/workflows/w6_beta_reader.py (360 lines)
sidecar/workflows/w7_metadata_ingestion.py (335 lines)
sidecar/supervisor/policy.py (1257 lines)
sidecar/supervisor/tools.py (1595 lines)
sidecar/supervisor/tool_registry.py (49 lines)
sidecar/supervisor/organizer.py (527 lines)
sidecar/models/state.py (1356 lines)
sidecar/routers/status.py (22 lines)
sidecar/routers/orchestrator.py (219 lines)
sidecar/routers/workflows.py (~800 lines)
sidecar/shared/s1_context_builder.py
sidecar/shared/s4_proposal_queue.py
tests/test_w1_organizer.py
tests/test_w1_pipeline_tools.py
```

---

## Next Steps (Pending Lead Approval)

Implement Phase B scaffolding as described in the architecture report, Section 5:
1. `sidecar/models/workflow_contract.py` + `tests/test_workflow_contract.py`
2. `sidecar/shared/s5_reference_graph.py` + `tests/test_reference_graph.py`
3. `sidecar/shared/s6_sequence_order.py` + `tests/test_sequence_order.py`

All three modules are additive-only. Zero changes to existing workflow, supervisor, or model files.
