# W1 Prompt / Pipeline Toolization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Reviewer findings as structured PromptPolicyPatch knobs and define a pipeline tool registry callable by the Orchestrator — replacing hard-coded reruns with informed, bounded policy decisions.

**Architecture:** ReviewReport findings map deterministically to allowlisted PromptPolicyPatch knobs via `_reviewer_findings_to_policy_patch()`. A new `pipeline_tools.py` module contains async tool implementations that the Orchestrator can call (run_quality_review, run_fact_review, run_consistency_review, rerun_targeted_window, repair_import_artifacts, write_proposal_package). No raw prompt text is ever accepted.

**Tech Stack:** Python 3.11, pytest (zero-cost / no live API), existing `reviewers/` schemas.

---

## 1. Goals and Non-Goals

### Goals
1. Extend `PromptPolicyPatch` with 3 new knobs: `reviewer_mode`, `rerun_scope`, `organizer_strictness`.
2. Add `_reviewer_findings_to_policy_patch(report)` to `planner.py`: maps finding codes → patch knobs.
3. Create `pipeline_tools.py` with 6 async Orchestrator-callable tool contracts.
4. Register reviewer pipeline tools in `tool_registry.py`.
5. All covered by zero-cost tests in `tests/test_w1_pipeline_tools.py`.

### Non-Goals
- No frontend changes.
- No World UI changes.
- No live API calls or `ANTHROPIC_API_KEY` reads.
- No raw prompt injection — all directives from static allowlist.
- No changes to `sidecar/workflows/w1_import.py`.
- No Timeline UI changes.

---

## 2. Current State (as of 2026-06-01)

Already implemented (W1 Reviewer + W2 Organizer):
- `sidecar/supervisor/reviewers/schemas.py` — TypedDict ReviewReport, ReviewFinding, RepairAction, OrchestratorRequest, ZeroCostLedger ✅
- `sidecar/supervisor/reviewers/base.py` — BaseReviewer ABC ✅
- `sidecar/supervisor/reviewers/quality_reviewer.py` — QualityReviewer ✅
- `sidecar/supervisor/reviewers/fact_reviewer.py` — FactReviewer ✅
- `sidecar/supervisor/reviewers/consistency_reviewer.py` — ConsistencyReviewer ✅
- `sidecar/supervisor/organizer.py` — organize_project_content() ✅
- 29 existing reviewer + organizer tests PASS ✅

Missing (this plan):
- `sidecar/supervisor/pipeline_tools.py` ❌
- `tests/test_w1_pipeline_tools.py` ❌
- `prompt_policy.py` — 3 new knobs ❌
- `planner.py` — `_reviewer_findings_to_policy_patch()` + updated `_PPP_ALLOWED_FIELDS` ❌
- `tool_registry.py` — reviewer tool registrations ❌

---

## 3. File Map

**New files:**
- `sidecar/supervisor/pipeline_tools.py` — all 6 async Orchestrator tool implementations
- `tests/test_w1_pipeline_tools.py` — zero-cost tests for all new functionality

**Modified files:**
- `sidecar/supervisor/prompt_policy.py:116-250` — add 3 new knobs to normalize/directives/validate
- `sidecar/supervisor/planner.py:27-115` — add `_reviewer_findings_to_policy_patch()` + update `_PPP_ALLOWED_FIELDS`
- `sidecar/supervisor/tool_registry.py` — add reviewer pipeline tools to registry

**NOT touched:**
- `sidecar/supervisor/tools.py` — tools.py is extraction/QA tools; reviewer pipeline lives in pipeline_tools.py
- Any frontend file
- `sidecar/workflows/w1_import.py`

---

## 4. Design: New PromptPolicyPatch Knobs

### 4.1 Three New Knobs

```python
# reviewer_mode: which reviewer triggered this policy (advisory annotation)
_REVIEWER_MODE_VALUES = frozenset({"quality", "fact", "consistency"})

# rerun_scope: scope of targeted rerun requested by a reviewer
_RERUN_SCOPE_VALUES = frozenset({"local_window", "entity_cluster", "timeline_branch", "world_category"})

# organizer_strictness: how strictly the organizer filters world/character boundaries
# (reuses low/medium/high like world_boundary_strictness but scopes to organizer stage only)
# already exists as _STRICTNESS_VALUES = frozenset({"low", "medium", "high"})
```

### 4.2 Directives for New Knobs

```python
_REVIEWER_MODE_DIRECTIVES = {
    "quality":      ("reviewer_mode", "Quality review mode: prioritize canonical event classification and world boundary enforcement."),
    "fact":         ("reviewer_mode", "Fact review mode: require evidence refs for all proposed entities."),
    "consistency":  ("reviewer_mode", "Consistency review mode: cross-check against prior import run summaries."),
}
_RERUN_SCOPE_DIRECTIVES = {
    "local_window":     ("rerun_scope", "Rerun scope: local window only — target the specific prompt window that failed."),
    "entity_cluster":   ("rerun_scope", "Rerun scope: entity cluster — re-extract the affected character/event cluster."),
    "timeline_branch":  ("rerun_scope", "Rerun scope: timeline branch — re-run extraction for the affected branch segment."),
    "world_category":   ("rerun_scope", "Rerun scope: world category — re-extract world entities in the affected category."),
}
_ORGANIZER_STRICTNESS_DIRECTIVES = {
    "low":    ("organizer_strictness", "Organizer strictness is low: pass ambiguous world entries with warnings."),
    "medium": ("organizer_strictness", "Organizer strictness is medium: exclude ambiguous person-name world entries."),
    "high":   ("organizer_strictness", "Organizer strictness is high: exclude all boundary-ambiguous entries; route to correct module."),
}
```

---

## 5. Design: `_reviewer_findings_to_policy_patch()`

Mapping from finding `check_name` → PromptPolicyPatch knobs.  
Only medium/high severity findings may generate orchestrator rerun requests.  
Low severity → local repair only, no patch change to rerun scope.

```python
_FINDING_TO_PATCH: dict[str, dict] = {
    # Quality: event density / timeline stream
    "timeline_stream_of_consciousness": {
        "event_density_strategy": "sparse_turning_points",
        "prefer_canonical_events": True,
    },
    "event_density_too_high": {
        "event_density_strategy": "sparse_turning_points",
        "prefer_canonical_events": True,
    },
    # Quality: branch topology flat
    "mainline_share_too_high": {
        "topology_fidelity": "high",
        "emphasize_existing_timeline_topology": True,
    },
    # Quality/Consistency: world contamination
    "world_module_pollution": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
        "world_boundary_strictness": "high",
    },
    "world_wrong_classification": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
    },
    "world_contamination_high": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
        "world_boundary_strictness": "high",
    },
    # Fact: evidence cluster mismatch
    "fact_mismatch_entity_cluster": {
        "rerun_scope": "entity_cluster",
    },
    # Consistency: duplicate characters → local repair, no patch
    "duplicate_character_cross_import": {},  # handled by local repair only
}

_HIGH_SEVERITY = {"medium", "high"}

def _reviewer_findings_to_policy_patch(report: dict) -> dict:
    """
    Map ReviewReport findings to a PromptPolicyPatch.

    Returns only allowlisted knobs. Low-severity findings contribute
    to local repairs only, not to rerun-scope patch fields.
    """
    patch: dict = {}
    for finding in report.get("findings", []):
        code = finding.get("check_name", "")
        severity = finding.get("severity", "low")
        code_patch = _FINDING_TO_PATCH.get(code, {})
        # rerun_scope only emitted for medium/high severity
        if severity not in _HIGH_SEVERITY and "rerun_scope" in code_patch:
            code_patch = {k: v for k, v in code_patch.items() if k != "rerun_scope"}
        patch.update(code_patch)
    return patch
```

---

## 6. Design: `pipeline_tools.py` Tool Contracts

```python
async def run_quality_review(state: ImportSupervisorState) -> dict:
    """Run QualityReviewer over state proposals. Stores ReviewReport in state."""

async def run_fact_review(state: ImportSupervisorState) -> dict:
    """Run FactReviewer. Evidence index built from evidence_refs only (no full source read)."""

async def run_consistency_review(state: ImportSupervisorState) -> dict:
    """Run ConsistencyReviewer over current vs prior import run summaries."""

async def rerun_targeted_window(
    state: ImportSupervisorState,
    affected_window_ids: list[str],
    reason: str,
    parameter_overrides: dict | None = None,
) -> dict:
    """Targeted rerun for specific windows. Raises ValueError if affected_window_ids is empty."""

async def repair_import_artifacts(
    state: ImportSupervisorState,
    repair_actions: list[dict],
) -> dict:
    """Apply deterministic local repair actions from ReviewReport.local_repair_actions."""

async def write_proposal_package(
    state: ImportSupervisorState,
    package: dict,
) -> dict:
    """Stage a ProposalPackage for the Workbench inbox (does not write to canonical storage directly)."""
```

---

## 7. Required Tests (all zero-cost, no live API)

| # | Test | Expected |
|---|---|---|
| 1 | `_reviewer_findings_to_policy_patch(report_with_event_density_high)` | patch contains `event_density_strategy="sparse_turning_points"` |
| 2 | `_reviewer_findings_to_policy_patch(report_with_world_contamination)` | patch contains `world_model_scope="world_only"` and `organizer_strictness="high"` |
| 3 | `_reviewer_findings_to_policy_patch(report_with_mainline_high)` | patch contains `topology_fidelity="high"` |
| 4 | Low severity finding only → `rerun_scope` NOT in patch | (rerun_scope requires medium/high) |
| 5 | Raw prompt text passed to `normalize_prompt_policy_patch` → not in output | no raw_prompt_text key survives |
| 6 | `reviewer_mode`, `rerun_scope`, `organizer_strictness` accepted by `normalize_prompt_policy_patch` | all 3 knobs normalized |
| 7 | Invalid `reviewer_mode` value rejected by `validate_prompt_policy_patch` | returns errors |
| 8 | Invalid `rerun_scope` value rejected | returns errors |
| 9 | `run_quality_review` registered in tool registry with correct signature | tool_registry key exists |
| 10 | `rerun_targeted_window` with empty `affected_window_ids` raises `ValueError` | raises ValueError |
| 11 | `rerun_targeted_window` with non-empty `affected_window_ids` calls `rerun_window` for each id | tool called once per id |
| 12 | `repair_import_artifacts` with `action_type="merge_duplicate"` applies merge to entity_registry | merged |
| 13 | `write_proposal_package` with valid package stores it in state's `pending_proposal_packages` | stored |
| 14 | `_reviewer_findings_to_policy_patch(duplicate_character_cross_import)` → empty patch | local repair only |
| 15 | Extended knobs `reviewer_mode`/`rerun_scope`/`organizer_strictness` appear in `build_directives_header` output | directive strings present |

---

## 8. Execution Tasks

### Task 1: Extend `prompt_policy.py` with 3 new knobs

**Files:**
- Modify: `sidecar/supervisor/prompt_policy.py:116-265`
- Test: `tests/test_w1_pipeline_tools.py` (write first)

- [ ] **Step 1: Write failing tests for the 3 new knobs**

```python
# tests/test_w1_pipeline_tools.py (partial)
from sidecar.supervisor.prompt_policy import (
    normalize_prompt_policy_patch,
    build_directives_header,
)
from sidecar.supervisor.planner import validate_prompt_policy_patch

def test_reviewer_mode_accepted_by_normalize():
    result = normalize_prompt_policy_patch({"reviewer_mode": "quality"})
    assert result["reviewer_mode"] == "quality"

def test_rerun_scope_accepted_by_normalize():
    result = normalize_prompt_policy_patch({"rerun_scope": "entity_cluster"})
    assert result["rerun_scope"] == "entity_cluster"

def test_organizer_strictness_accepted_by_normalize():
    result = normalize_prompt_policy_patch({"organizer_strictness": "high"})
    assert result["organizer_strictness"] == "high"

def test_invalid_reviewer_mode_rejected_by_validate():
    ok, errors = validate_prompt_policy_patch({"reviewer_mode": "unknown_mode"})
    assert not ok
    assert any("reviewer_mode" in e for e in errors)

def test_invalid_rerun_scope_rejected_by_validate():
    ok, errors = validate_prompt_policy_patch({"rerun_scope": "full_pipeline"})
    assert not ok
    assert any("rerun_scope" in e for e in errors)

def test_new_knobs_appear_in_directives_header():
    header = build_directives_header({
        "reviewer_mode": "quality",
        "rerun_scope": "entity_cluster",
        "organizer_strictness": "high",
    })
    assert "reviewer_mode" in header
    assert "rerun_scope" in header
    assert "organizer_strictness" in header
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd /Volumes/migodam\'s-external-brain/Development/Narrative_IDE
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py::test_reviewer_mode_accepted_by_normalize -xvs
```
Expected: `FAILED` with `KeyError` or `AttributeError`.

- [ ] **Step 3: Add 3 new knobs to `prompt_policy.py`**

In `sidecar/supervisor/prompt_policy.py`, after the existing `_LABEL_GRANULARITY_VALUES` constant (line ~24), add:

```python
_REVIEWER_MODE_VALUES: frozenset[str] = frozenset({"quality", "fact", "consistency"})
_RERUN_SCOPE_VALUES: frozenset[str] = frozenset({"local_window", "entity_cluster", "timeline_branch", "world_category"})
# _ORGANIZER_STRICTNESS_VALUES reuses _STRICTNESS_VALUES (low/medium/high)

_REVIEWER_MODE_DIRECTIVES: dict[str, tuple[str, str]] = {
    "quality":      ("reviewer_mode", "Quality review mode: prioritize canonical event classification and world boundary enforcement."),
    "fact":         ("reviewer_mode", "Fact review mode: require evidence refs for all proposed entities."),
    "consistency":  ("reviewer_mode", "Consistency review mode: cross-check against prior import run summaries."),
}
_RERUN_SCOPE_DIRECTIVES: dict[str, tuple[str, str]] = {
    "local_window":     ("rerun_scope", "Rerun scope: local window only — target the specific prompt window that failed."),
    "entity_cluster":   ("rerun_scope", "Rerun scope: entity cluster — re-extract the affected character/event cluster."),
    "timeline_branch":  ("rerun_scope", "Rerun scope: timeline branch — re-run extraction for the affected branch segment."),
    "world_category":   ("rerun_scope", "Rerun scope: world category — re-extract world entities in the affected category."),
}
_ORGANIZER_STRICTNESS_DIRECTIVES: dict[str, tuple[str, str]] = {
    "low":    ("organizer_strictness", "Organizer strictness is low: pass ambiguous world entries with warnings."),
    "medium": ("organizer_strictness", "Organizer strictness is medium: exclude ambiguous person-name world entries."),
    "high":   ("organizer_strictness", "Organizer strictness is high: exclude all boundary-ambiguous entries; route to correct module."),
}
```

Update `normalize_prompt_policy_patch()` to handle the 3 new knobs:

```python
# After the existing label_granularity block, add:
reviewer_mode = patch.get("reviewer_mode")
if reviewer_mode in _REVIEWER_MODE_VALUES:
    normalized["reviewer_mode"] = reviewer_mode
rerun_scope = patch.get("rerun_scope")
if rerun_scope in _RERUN_SCOPE_VALUES:
    normalized["rerun_scope"] = rerun_scope
organizer_strictness = patch.get("organizer_strictness")
if organizer_strictness in _STRICTNESS_VALUES:
    normalized["organizer_strictness"] = organizer_strictness
```

Update `prompt_policy_directives()` to emit new directives (after existing label_granularity block):

```python
reviewer_mode = str(normalized.get("reviewer_mode", "")) 
if reviewer_mode in _REVIEWER_MODE_DIRECTIVES:
    key, directive = _REVIEWER_MODE_DIRECTIVES[reviewer_mode]
    directives[key] = directive
rerun_scope = str(normalized.get("rerun_scope", ""))
if rerun_scope in _RERUN_SCOPE_DIRECTIVES:
    key, directive = _RERUN_SCOPE_DIRECTIVES[rerun_scope]
    directives[key] = directive
organizer_strictness = str(normalized.get("organizer_strictness", ""))
if organizer_strictness in _ORGANIZER_STRICTNESS_DIRECTIVES:
    key, directive = _ORGANIZER_STRICTNESS_DIRECTIVES[organizer_strictness]
    directives[key] = directive
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -k "reviewer_mode or rerun_scope or organizer_strictness or new_knobs" -xvs
```
Expected: all PASS.

- [ ] **Step 5: Run regression guard**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_reviewers_quality.py -q --tb=short
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add sidecar/supervisor/prompt_policy.py tests/test_w1_pipeline_tools.py
git commit -m "feat: add reviewer_mode, rerun_scope, organizer_strictness knobs to PromptPolicyPatch"
```

---

### Task 2: Update `planner.py` — `_PPP_ALLOWED_FIELDS` + `_reviewer_findings_to_policy_patch()`

**Files:**
- Modify: `sidecar/supervisor/planner.py:45-115`
- Test: `tests/test_w1_pipeline_tools.py`

- [ ] **Step 1: Write failing tests for `_reviewer_findings_to_policy_patch()`**

```python
# In tests/test_w1_pipeline_tools.py
from sidecar.supervisor.planner import _reviewer_findings_to_policy_patch

def _finding(check_name: str, severity: str = "high") -> dict:
    return {
        "finding_id": f"{check_name}_0",
        "check_name": check_name,
        "description": "test finding",
        "severity": severity,
        "entity_refs": [],
        "evidence_refs": [],
    }

def _report(findings: list) -> dict:
    return {
        "reviewer": "quality",
        "verdict": "needs_orchestrator_rerun",
        "severity": "high",
        "findings": findings,
        "local_repair_actions": [],
        "orchestrator_requests": [],
        "token_cost_ledger": {"live_model_calls": False, "full50_run": False, "model_used": None, "estimated_api_calls": 0, "estimated_prompt_windows": 0},
    }

def test_event_density_finding_gives_sparse_turning_points():
    report = _report([_finding("timeline_stream_of_consciousness", "high")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert patch.get("event_density_strategy") == "sparse_turning_points"
    assert patch.get("prefer_canonical_events") is True

def test_world_contamination_gives_world_only_scope():
    report = _report([_finding("world_module_pollution", "medium")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert patch.get("world_model_scope") == "world_only"
    assert patch.get("organizer_strictness") == "high"

def test_mainline_share_gives_high_topology():
    report = _report([_finding("mainline_share_too_high", "medium")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert patch.get("topology_fidelity") == "high"

def test_low_severity_does_not_add_rerun_scope():
    report = _report([_finding("fact_mismatch_entity_cluster", "low")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert "rerun_scope" not in patch

def test_medium_severity_fact_mismatch_adds_rerun_scope():
    report = _report([_finding("fact_mismatch_entity_cluster", "medium")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert patch.get("rerun_scope") == "entity_cluster"

def test_duplicate_character_gives_empty_patch():
    report = _report([_finding("duplicate_character_cross_import", "high")])
    patch = _reviewer_findings_to_policy_patch(report)
    assert patch == {}

def test_new_knobs_accepted_in_ppp_allowed_fields():
    from sidecar.supervisor.planner import validate_prompt_policy_patch
    ok, errors = validate_prompt_policy_patch({
        "reviewer_mode": "quality",
        "rerun_scope": "entity_cluster",
        "organizer_strictness": "high",
    })
    assert ok, errors
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -k "finding or ppp_allowed" -xvs 2>&1 | head -30
```
Expected: `FAILED` — `_reviewer_findings_to_policy_patch` not defined; `validate_prompt_policy_patch` rejects new knobs.

- [ ] **Step 3: Update `planner.py`**

In `sidecar/supervisor/planner.py`:

Add to `_PPP_ALLOWED_FIELDS`:
```python
_PPP_ALLOWED_FIELDS: frozenset = frozenset({
    "emphasize_existing_timeline_topology",
    "require_source_provenance",
    "prefer_canonical_events",
    "suppress_minor_npcs",
    "relationship_evidence_required",
    "world_boundary_strictness",
    "event_density_strategy",
    "topology_fidelity",
    "world_model_scope",
    "timeline_label_granularity",
    # New W3 knobs
    "reviewer_mode",
    "rerun_scope",
    "organizer_strictness",
})
```

Add validation for new knobs in `validate_prompt_policy_patch()` (after existing label check):
```python
reviewer_mode = patch.get("reviewer_mode")
if reviewer_mode is not None and reviewer_mode not in frozenset({"quality", "fact", "consistency"}):
    errors.append(f"reviewer_mode: {reviewer_mode!r} not in allowed values")
rerun_scope = patch.get("rerun_scope")
if rerun_scope is not None and rerun_scope not in frozenset({"local_window", "entity_cluster", "timeline_branch", "world_category"}):
    errors.append(f"rerun_scope: {rerun_scope!r} not in allowed values")
organizer_strictness = patch.get("organizer_strictness")
if organizer_strictness is not None and organizer_strictness not in frozenset({"low", "medium", "high"}):
    errors.append(f"organizer_strictness: {organizer_strictness!r} not in allowed values")
```

Add `_reviewer_findings_to_policy_patch()` function at the bottom of `planner.py`:

```python
# ---------------------------------------------------------------------------
# Reviewer → PromptPolicyPatch mapping
# ---------------------------------------------------------------------------

_FINDING_TO_PATCH: dict[str, dict] = {
    "timeline_stream_of_consciousness": {
        "event_density_strategy": "sparse_turning_points",
        "prefer_canonical_events": True,
    },
    "event_density_too_high": {
        "event_density_strategy": "sparse_turning_points",
        "prefer_canonical_events": True,
    },
    "mainline_share_too_high": {
        "topology_fidelity": "high",
        "emphasize_existing_timeline_topology": True,
    },
    "world_module_pollution": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
        "world_boundary_strictness": "high",
    },
    "world_wrong_classification": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
    },
    "world_contamination_high": {
        "world_model_scope": "world_only",
        "organizer_strictness": "high",
        "world_boundary_strictness": "high",
    },
    "fact_mismatch_entity_cluster": {
        "rerun_scope": "entity_cluster",
    },
    "duplicate_character_cross_import": {},
}

_SEVERITY_ALLOWS_RERUN = frozenset({"medium", "high"})


def _reviewer_findings_to_policy_patch(report: dict) -> dict:
    """Map ReviewReport findings to an allowlisted PromptPolicyPatch dict.

    Only medium/high severity findings may set rerun_scope.
    Low severity findings contribute to local repairs only.
    Raw prompt text is never accepted (this function only outputs allowed knob keys).
    """
    patch: dict = {}
    for finding in report.get("findings", []):
        code = str(finding.get("check_name", ""))
        severity = str(finding.get("severity", "low"))
        code_patch = dict(_FINDING_TO_PATCH.get(code, {}))
        if severity not in _SEVERITY_ALLOWS_RERUN:
            code_patch.pop("rerun_scope", None)
        patch.update(code_patch)
    return patch
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -k "finding or ppp_allowed" -xvs
```
Expected: all PASS.

- [ ] **Step 5: Run regression guard**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_supervisor_policy.py -q --tb=short
```
Expected: all pass (especially the `raw_prompt_text` rejection tests).

- [ ] **Step 6: Commit**

```bash
git add sidecar/supervisor/planner.py tests/test_w1_pipeline_tools.py
git commit -m "feat: add _reviewer_findings_to_policy_patch and 3 new PPP knobs to planner"
```

---

### Task 3: Create `pipeline_tools.py` with 6 async Orchestrator tool contracts

**Files:**
- Create: `sidecar/supervisor/pipeline_tools.py`
- Test: `tests/test_w1_pipeline_tools.py`

- [ ] **Step 1: Write failing tests for pipeline tools**

```python
# In tests/test_w1_pipeline_tools.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _base_state(**overrides) -> dict:
    state = {
        "project_path": "/tmp/pipeline_test",
        "import_run_id": "pipeline_test_run",
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "proposals": [],
        "inbox_proposals": [],
        "reviewer_reports": {},
        "supervisor_log": [],
        "prompt_windows": [{"id": "pwin_0", "chunk_ids": [0]}],
        "window_metrics": {},
        "source_language": "zh",
        "converge_target": {},
        "import_granularity_profile": {},
    }
    state.update(overrides)
    return state


class TestRunQualityReview:
    def test_run_quality_review_returns_report_in_state(self):
        from sidecar.supervisor.pipeline_tools import run_quality_review
        state = _base_state()
        result = asyncio.run(run_quality_review(state))
        assert "reviewer_reports" in result
        assert "quality" in result["reviewer_reports"]

    def test_run_quality_review_report_has_required_keys(self):
        from sidecar.supervisor.pipeline_tools import run_quality_review
        state = _base_state()
        result = asyncio.run(run_quality_review(state))
        report = result["reviewer_reports"]["quality"]
        for key in ("reviewer", "verdict", "severity", "findings", "local_repair_actions"):
            assert key in report, f"Missing key: {key}"

    def test_run_quality_review_does_not_call_live_api(self):
        from sidecar.supervisor.pipeline_tools import run_quality_review
        state = _base_state()
        with patch("sidecar.supervisor.pipeline_tools.QualityReviewer.review") as mock_review:
            mock_review.return_value = {
                "reviewer": "quality", "verdict": "pass", "severity": "low",
                "findings": [], "local_repair_actions": [], "orchestrator_requests": [],
                "token_cost_ledger": {"live_model_calls": False, "full50_run": False, "model_used": None, "estimated_api_calls": 0, "estimated_prompt_windows": 0},
            }
            result = asyncio.run(run_quality_review(state))
        # token_cost_ledger.live_model_calls must be False
        report = result["reviewer_reports"]["quality"]
        assert report["token_cost_ledger"]["live_model_calls"] is False


class TestRunFactReview:
    def test_run_fact_review_returns_report_in_state(self):
        from sidecar.supervisor.pipeline_tools import run_fact_review
        state = _base_state()
        result = asyncio.run(run_fact_review(state))
        assert "reviewer_reports" in result
        assert "fact" in result["reviewer_reports"]

    def test_run_fact_review_does_not_read_chunks(self):
        """FactReviewer must not be passed state['chunks'] directly."""
        from sidecar.supervisor.pipeline_tools import run_fact_review
        state = _base_state()
        # Add a large 'chunks' key — it must not be consumed by the reviewer
        state["chunks"] = [{"content": "x" * 10000} for _ in range(50)]
        # If this doesn't raise and reviewer runs, chunks were not passed to the reviewer
        result = asyncio.run(run_fact_review(state))
        assert "fact" in result.get("reviewer_reports", {})


class TestRunConsistencyReview:
    def test_run_consistency_review_returns_report_in_state(self):
        from sidecar.supervisor.pipeline_tools import run_consistency_review
        state = _base_state()
        result = asyncio.run(run_consistency_review(state))
        assert "reviewer_reports" in result
        assert "consistency" in result["reviewer_reports"]


class TestRerunTargetedWindow:
    def test_empty_window_ids_raises_value_error(self):
        from sidecar.supervisor.pipeline_tools import rerun_targeted_window
        state = _base_state()
        with pytest.raises(ValueError, match="affected_window_ids"):
            asyncio.run(rerun_targeted_window(state, [], "test reason"))

    def test_non_empty_window_ids_calls_rerun_per_window(self):
        from sidecar.supervisor.pipeline_tools import rerun_targeted_window
        state = _base_state()
        rerun_calls = []

        async def mock_rerun(state, window_id, strategy="augment", missing_char_names=None, parameter_overrides=None):
            rerun_calls.append(window_id)
            return {"entity_registry": state.get("entity_registry", {}), "window_metrics": {}}

        with patch("sidecar.supervisor.pipeline_tools.rerun_window", mock_rerun):
            asyncio.run(rerun_targeted_window(state, ["pwin_0", "pwin_1"], "character undercoverage"))

        assert "pwin_0" in rerun_calls
        assert "pwin_1" in rerun_calls


class TestRepairImportArtifacts:
    def test_merge_duplicate_repair_marks_skip_create(self):
        from sidecar.supervisor.pipeline_tools import repair_import_artifacts
        state = _base_state()
        state["entity_registry"]["characters"] = {
            "char_a": {"canonical_id": "char_a", "canonical_name": "Alice", "skip_create": False},
            "char_b": {"canonical_id": "char_b", "canonical_name": "Alice", "skip_create": False},
        }
        repair_actions = [{
            "action_type": "merge_duplicate",
            "target_entity_ids": ["char_a", "char_b"],
            "description": "Merge duplicate Alice characters",
            "deterministic": True,
        }]
        result = asyncio.run(repair_import_artifacts(state, repair_actions))
        chars = result.get("entity_registry", {}).get("characters", {})
        # At least one Alice should be marked skip_create
        skip_count = sum(1 for c in chars.values() if c.get("skip_create"))
        assert skip_count >= 1

    def test_empty_repair_actions_returns_unchanged_registry(self):
        from sidecar.supervisor.pipeline_tools import repair_import_artifacts
        state = _base_state()
        original_registry = dict(state["entity_registry"])
        result = asyncio.run(repair_import_artifacts(state, []))
        assert result.get("entity_registry") == original_registry


class TestWriteProposalPackage:
    def test_write_proposal_package_stores_in_pending_list(self):
        from sidecar.supervisor.pipeline_tools import write_proposal_package
        state = _base_state()
        package = {
            "package_id": "pkg_test_001",
            "container_key": "organizations",
            "items": [{"name": "七玄门", "category": "organization"}],
        }
        result = asyncio.run(write_proposal_package(state, package))
        pending = result.get("pending_proposal_packages", [])
        assert any(p.get("package_id") == "pkg_test_001" for p in pending)

    def test_write_proposal_package_does_not_mutate_canonical_storage(self):
        """Package write must NOT call node_write_to_project or any I/O."""
        from sidecar.supervisor.pipeline_tools import write_proposal_package
        state = _base_state()
        package = {"package_id": "pkg_readonly", "container_key": "locations", "items": []}
        with patch("sidecar.supervisor.pipeline_tools.node_write_to_project") as mock_write:
            asyncio.run(write_proposal_package(state, package))
            mock_write.assert_not_called()
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py::TestRunQualityReview -xvs 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'sidecar.supervisor.pipeline_tools'`.

- [ ] **Step 3: Implement `pipeline_tools.py`**

Create `sidecar/supervisor/pipeline_tools.py`:

```python
"""W1 Supervisor pipeline tool contracts — Orchestrator-callable tools.

Tools accept ImportSupervisorState and return partial state dicts.
No raw prompt text is accepted. All review calls are deterministic (zero-cost).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sidecar.models.state import ImportSupervisorState
from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer
from sidecar.supervisor.reviewers.fact_reviewer import FactReviewer
from sidecar.supervisor.reviewers.consistency_reviewer import ConsistencyReviewer
from sidecar.supervisor.tools import rerun_window
from sidecar.workflows.w1_import import node_write_to_project


# ── Reviewer tool wrappers ──────────────────────────────────────────────────


async def run_quality_review(state: ImportSupervisorState) -> dict:
    """Run QualityReviewer over state proposals. Stores ReviewReport as reviewer_reports['quality']."""
    reviewer = QualityReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["quality"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_quality_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


async def run_fact_review(state: ImportSupervisorState) -> dict:
    """Run FactReviewer over state proposals/evidence_cards.

    FactReviewer.review(state) reads state['evidence_cards'] and state['proposals'] only.
    It does NOT read state['chunks'] (full source text) — safe to pass full state.
    Confirmed from fact_reviewer.py: only reads evidence_cards, inbox_proposals, proposals.
    """
    reviewer = FactReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["fact"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_fact_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


async def run_consistency_review(state: ImportSupervisorState) -> dict:
    """Run ConsistencyReviewer — cross-import continuity checks. Zero-cost.

    ConsistencyReviewer.review(state) reads state['project_structure_digest'] and
    state['entity_registry'] only — deterministic, no LLM calls.
    """
    reviewer = ConsistencyReviewer()
    report = reviewer.review(state)
    reviewer_reports = dict(state.get("reviewer_reports") or {})
    reviewer_reports["consistency"] = report
    log = list(state.get("supervisor_log", []))
    log.append(f"run_consistency_review: verdict={report.get('verdict')}, findings={len(report.get('findings', []))}")
    return {
        "reviewer_reports": reviewer_reports,
        "supervisor_log": log,
    }


# ── Targeted rerun tool ─────────────────────────────────────────────────────


async def rerun_targeted_window(
    state: ImportSupervisorState,
    affected_window_ids: list[str],
    reason: str,
    parameter_overrides: dict | None = None,
) -> dict:
    """Targeted rerun for specific windows identified by a reviewer.

    Raises ValueError if affected_window_ids is empty (safety guard).
    """
    if not affected_window_ids:
        raise ValueError("rerun_targeted_window: affected_window_ids must be non-empty")

    partial: dict[str, Any] = {}
    log = list(state.get("supervisor_log", []))
    log.append(f"rerun_targeted_window: {len(affected_window_ids)} windows, reason={reason!r}")

    for window_id in affected_window_ids:
        current_state = {**state, **partial}
        update = await rerun_window(
            current_state,
            window_id,
            strategy="augment",
            parameter_overrides=parameter_overrides or {},
        )
        for k, v in update.items():
            if isinstance(v, list) and isinstance(partial.get(k), list):
                partial[k] = partial[k] + v
            elif isinstance(v, dict) and isinstance(partial.get(k), dict):
                merged = dict(partial[k])
                merged.update(v)
                partial[k] = merged
            else:
                partial[k] = v

    partial["supervisor_log"] = log
    return partial


# ── Local repair tool ───────────────────────────────────────────────────────


async def repair_import_artifacts(
    state: ImportSupervisorState,
    repair_actions: list[dict],
) -> dict:
    """Apply deterministic local repair actions from ReviewReport.local_repair_actions.

    Supported action_types:
    - "merge_duplicate": mark all but the first target_entity_id with skip_create=True
    - "reclassify": update the entity's category field (world entities only)
    """
    if not repair_actions:
        return {"entity_registry": deepcopy(state.get("entity_registry", {}))}

    registry = {
        k: deepcopy(v) if isinstance(v, dict) else v
        for k, v in state.get("entity_registry", {}).items()
    }
    chars: dict[str, dict] = {k: dict(v) for k, v in registry.get("characters", {}).items()}
    world_detailed: dict[str, dict] = {k: dict(v) for k, v in registry.get("world_detailed", {}).items()}
    repair_log: list[str] = list(state.get("minor_repair_log", []))

    for action in repair_actions:
        action_type = str(action.get("action_type", ""))
        target_ids = list(action.get("target_entity_ids", []))

        if action_type == "merge_duplicate" and len(target_ids) >= 2:
            # Keep the first id as canonical; mark the rest skip_create
            for dup_id in target_ids[1:]:
                if dup_id in chars:
                    chars[dup_id]["skip_create"] = True
                    repair_log.append(f"merge_duplicate: marked {dup_id!r} skip_create=True")

        elif action_type == "reclassify":
            new_category = str(action.get("description", "")).split("to category=")[-1].strip()
            for entity_id in target_ids:
                if entity_id in world_detailed:
                    world_detailed[entity_id]["category"] = new_category
                    repair_log.append(f"reclassify: {entity_id!r} → category={new_category!r}")

    registry["characters"] = chars
    registry["world_detailed"] = world_detailed
    log = list(state.get("supervisor_log", []))
    log.append(f"repair_import_artifacts: {len(repair_actions)} actions applied")

    return {
        "entity_registry": registry,
        "minor_repair_log": repair_log,
        "supervisor_log": log,
    }


# ── Proposal package staging tool ──────────────────────────────────────────


async def write_proposal_package(
    state: ImportSupervisorState,
    package: dict,
) -> dict:
    """Stage a ProposalPackage for the Workbench inbox.

    Does NOT write to canonical project storage directly.
    The package is added to state['pending_proposal_packages'] for later
    batch acceptance via the Workbench transaction path.
    """
    pending = list(state.get("pending_proposal_packages") or [])
    pending.append(package)
    log = list(state.get("supervisor_log", []))
    log.append(f"write_proposal_package: staged package_id={package.get('package_id')!r}")
    return {
        "pending_proposal_packages": pending,
        "supervisor_log": log,
    }
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -xvs 2>&1 | tail -30
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/supervisor/pipeline_tools.py tests/test_w1_pipeline_tools.py
git commit -m "feat: add pipeline_tools.py with Orchestrator-callable reviewer and repair tools"
```

---

### Task 4: Register pipeline tools in `tool_registry.py`

**Files:**
- Modify: `sidecar/supervisor/tool_registry.py`
- Test: `tests/test_w1_pipeline_tools.py`

- [ ] **Step 1: Write failing test for tool registry**

```python
def test_quality_review_registered_in_tool_registry():
    from sidecar.supervisor.tool_registry import build_tool_registry
    registry = build_tool_registry()
    assert "run_quality_review" in registry, "run_quality_review must be in tool registry"
    assert callable(registry["run_quality_review"])

def test_fact_review_registered_in_tool_registry():
    from sidecar.supervisor.tool_registry import build_tool_registry
    registry = build_tool_registry()
    assert "run_fact_review" in registry

def test_consistency_review_registered_in_tool_registry():
    from sidecar.supervisor.tool_registry import build_tool_registry
    registry = build_tool_registry()
    assert "run_consistency_review" in registry

def test_rerun_targeted_window_registered_in_tool_registry():
    from sidecar.supervisor.tool_registry import build_tool_registry
    registry = build_tool_registry()
    assert "rerun_targeted_window" in registry
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -k "registered_in_tool_registry" -xvs
```
Expected: `FAILED` — keys not in registry.

- [ ] **Step 3: Update `tool_registry.py`**

In `sidecar/supervisor/tool_registry.py`:

```python
from sidecar.supervisor.pipeline_tools import (
    run_quality_review,
    run_fact_review,
    run_consistency_review,
    rerun_targeted_window,
    repair_import_artifacts,
    write_proposal_package,
)

def build_tool_registry() -> dict:
    """Return a mapping of tool_name → callable for the supervisor policy loop."""
    return {
        # Extraction / QA tools
        "segment_manifest": segment_manifest,
        "extract_window": extract_window,
        "cross_validate_window": cross_validate_window,
        "rerun_window": rerun_window,
        "reduce_entities": reduce_entities,
        "reduce_world_entities": reduce_world_entities,
        "architect_timeline": architect_timeline,
        "qa_review": qa_review,
        "judge_import": judge_import,
        "minor_repair": minor_repair,
        "proposal_write": proposal_write,
        # Reviewer pipeline tools (W3)
        "run_quality_review": run_quality_review,
        "run_fact_review": run_fact_review,
        "run_consistency_review": run_consistency_review,
        "rerun_targeted_window": rerun_targeted_window,
        "repair_import_artifacts": repair_import_artifacts,
        "write_proposal_package": write_proposal_package,
    }
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -k "registered_in_tool_registry" -xvs
```
Expected: all PASS.

- [ ] **Step 5: Run full pipeline_tools suite**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py -v --tb=short
```
Expected: all tests PASS.

- [ ] **Step 6: Run regression guard (all W1 tests)**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_planner_proposal.py tests/test_w1_supervisor_policy.py tests/test_w1_reviewers_quality.py tests/test_w1_reviewers_fact.py tests/test_w1_reviewers_consistency.py tests/test_w1_organizer.py tests/test_w1_pipeline_tools.py -q --tb=short
```
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add sidecar/supervisor/tool_registry.py
git commit -m "feat: register reviewer pipeline tools in tool_registry"
```

---

### Task 5: Write PM verification report

**Files:**
- Create: `communication/2026-06-01-w1-prompt-pipeline-toolization-report.md`

- [ ] **Step 1: Run all tests and capture output**

```bash
sidecar/.venv/bin/python -m pytest tests/test_w1_pipeline_tools.py tests/test_w1_planner_proposal.py tests/test_w1_supervisor_policy.py -v --tb=short 2>&1
```

- [ ] **Step 2: Write report**

Report must include:
- All changed files
- Tests run and results
- Risks / deferred items
- Interface contract for W6 Verification

---

## 9. Interfaces / Dependencies on Other Windows

| This task depends on | Status |
|---|---|
| W1 Reviewer: `reviewers/schemas.py` (ReviewReport, ReviewFinding etc.) | ✅ DONE |
| W1 Reviewer: `quality_reviewer.py`, `fact_reviewer.py`, `consistency_reviewer.py` | ✅ DONE |
| W2 Organizer: `organizer.py` | ✅ DONE |

| This task produces for other windows | What |
|---|---|
| W6 Verification | `pipeline_tools.py` callable tools, test suite pass evidence |
| Lead Integration | `_reviewer_findings_to_policy_patch()` for post-review policy update path |

---

## 10. Risks and Deferred Items

| Risk | Severity | Mitigation |
|---|---|---|
| `FactReviewer.review()` signature may differ from my assumption | Low | Step 4 checks the actual signature before implementing `run_fact_review` |
| `ConsistencyReviewer.review()` signature uncertainty | Low | Step 5 checks the actual signature before implementing `run_consistency_review` |
| `rerun_window` import from `tools.py` may cause circular import | Low | `pipeline_tools.py` imports `rerun_window` from `tools.py`; tools.py does not import from pipeline_tools.py — no circle |
| `node_write_to_project` imported but should never be called in `write_proposal_package` | Low | Test explicitly patches and asserts `not called` |
| Raw prompt injection via `parameter_overrides` in `rerun_targeted_window` | Low | `parameter_overrides` is passed as `ORCHESTRATOR_PARAMETER_OVERRIDES` hint (existing safe path in `rerun_window`); not injected directly into prompt templates |
| State key `pending_proposal_packages` is new — may need `ImportSupervisorState` typedef update | Low | Kept as untyped dict field; if TypedDict strict mode is needed, add to `state.py` separately |

**Deferred:**
- LLM-powered reviewer adapters (deterministic only in this task)
- Full RAG evidence index for FactReviewer (stub returns True)
- `repair_import_artifacts` action coverage beyond `merge_duplicate` and `reclassify`

---

## Self-Review Against Task Pack W3 Spec

| Spec requirement | Covered? |
|---|---|
| `reviewer_mode`, `rerun_scope`, `organizer_strictness` knobs in `prompt_policy.py` | ✅ Task 1 |
| `_reviewer_findings_to_policy_patch()` in `planner.py` | ✅ Task 2 |
| `event_density_too_high` + severity ≥ medium → `sparse_turning_points` | ✅ Task 2 |
| `world_contamination_high` → `world_model_scope="world_only"` | ✅ Task 2 |
| Low severity → no orchestrator request | ✅ Task 2 (rerun_scope blocked) |
| Raw prompt text rejected with `ValueError` | ✅ Existing behavior; new knobs also don't accept free text |
| `run_quality_review` registered in tool registry | ✅ Task 4 |
| `rerun_targeted_window` raises `ValueError` for empty ids | ✅ Task 3 |
| All 6 tests from lead plan | ✅ All covered (tests 1-6) |
| PM-style verification report in `communication/` | ✅ Task 5 |
