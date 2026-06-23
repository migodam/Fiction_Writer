# W1 Lead Integration Patch — Codex 验收补充

**Date:** 2026-06-01  
**Reviewer:** Codex  
**Scope:** 复核 Claude Lead Integration Patch 是否关闭 Codex acceptance review 中的 4 个 integration gaps。

---

## Verdict

**Go for small manual smoke.**

这次 Lead patch 的核心验收项已经通过：Reviewer 接入 `qa_review()`，Organizer 接入真实 W1 graph，package grouping 的前端契约修正，Timeline W4 regression 仍然通过。

但仍有一个非阻塞风险：Reviewer repair proposal 当前更像“可展示/可打包的修复建议”，不一定已经是可执行 canonical patch。手动 smoke 时要特别观察：接受 reviewer repair package 后，实体是否真的发生了预期修改，而不是只从 Inbox 消失。

---

## Commands Re-run By Codex

| Check | Result |
|---|---:|
| `sidecar/.venv/bin/python -m py_compile sidecar/supervisor/tools.py sidecar/supervisor/organizer.py sidecar/workflows/w1_import.py sidecar/supervisor/pipeline_tools.py sidecar/models/state.py` | PASS |
| `sidecar/.venv/bin/python -m pytest tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_pipeline_tools.py tests/test_w1_quality_rubric.py tests/test_w1_v2_harness.py -q` | **97 passed** |
| `npm run ui:build` | PASS |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/world_model_organizer.spec.ts --reporter=list` | **4 passed** |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/workbench_reviewer_repair_package.spec.ts --reporter=list` | **8 passed** |
| `npx playwright test --config tests/playwright.config.ts tests/e2e/p1/timeline_sync_roundtrip.spec.ts --reporter=list` | **8 passed** |

---

## Code Evidence

| Requirement | Evidence | Status |
|---|---|---|
| Organizer wired into W1 graph | `sidecar/workflows/w1_import.py` has `node_organize_project`; graph adds `architect_timeline -> organize_project -> generate_import_todos` | Accepted |
| Organizer artifact persisted | `node_organize_project()` writes `organizer_output.json` when `project_path` and `import_run_id` exist | Accepted |
| Reviewer wired into `qa_review()` | `sidecar/supervisor/tools.py:qa_review()` calls `QualityReviewer`, `FactReviewer`, `ConsistencyReviewer` | Accepted |
| Reviewer package metadata emitted | `_collect_repair_proposals()` emits `source`, `originTaskRunId`, `data.reviewerRunId` | Accepted for package grouping |
| Single-proposal reviewer/organizer packages render | `buildProposalPackages()` allows single proposal for reviewer sources | Accepted |
| Expanded package list shows entity names | `WorkbenchWorkspace.tsx` uses display-name helper in expanded package rows | Accepted |
| Timeline canonical sync preserved | `timeline_sync_roundtrip.spec.ts` 8/8 pass | Accepted |

---

## Remaining Risk

### Reviewer repair proposal operation schema

`_collect_repair_proposals()` currently emits operations shaped like:

```python
{"type": action_type, ...params}
```

The frontend Workbench applier normally expects operation fields like:

```ts
{ op: "create" | "update" | "delete", entityType, entityId, fields }
```

Current tests validate package metadata/grouping and package acceptance UX, but they do not prove that reviewer repair proposals perform real canonical edits. This is acceptable for manual smoke readiness, but not enough for “Reviewer can self-repair small problems” product certification.

Recommended follow-up:

- Add a zero-cost test where a reviewer repair proposal updates/reclassifies a real `world_item`.
- Normalize reviewer repair proposals to valid Workbench `proposedOperations` or explicitly mark them as advisory/manual proposals.

---

## Manual Smoke Checklist

For your next small `deep` smoke:

- Verify `system/imports/<run_id>/organizer_output.json` exists.
- Verify World Model no longer contains module contamination like `人物关系图` / `事件时间线`.
- Verify Inbox shows organizer/reviewer package cards, including single-proposal packages.
- Accept an organizer package and confirm world item actually appears in canonical World Model.
- Accept a reviewer repair package and confirm whether it actually changes canonical data; if not, log as next bug.
- Verify Timeline branch/fork/merge fields survive reload after import and manual drag.
- Verify Timeline sync has no false-positive schema warnings.

---

## PM Judgment

This patch is a meaningful integration completion. It is now reasonable for the user to run a **small manual deep smoke**, not a full production certification. The next quality gate should be based on real import artifacts: event density, topology branch fidelity, world taxonomy quality, manuscript content, and whether reviewer repair packages are executable or merely advisory.
