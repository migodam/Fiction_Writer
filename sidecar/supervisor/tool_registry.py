"""W1 Supervisor tool registry."""
from __future__ import annotations

from sidecar.supervisor.tools import (
    architect_timeline,
    cross_validate_window,
    extract_window,
    judge_import,
    minor_repair,
    proposal_write,
    qa_review,
    reduce_entities,
    reduce_world_entities,
    rerun_window,
    segment_manifest,
)
from sidecar.supervisor.pipeline_tools import (
    repair_import_artifacts,
    run_consistency_review,
    run_fact_review,
    run_quality_review,
    rerun_targeted_window,
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
