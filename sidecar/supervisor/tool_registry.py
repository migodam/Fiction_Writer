"""W1 Supervisor tool registry."""
from __future__ import annotations

from sidecar.supervisor.tools import (
    architect_timeline,
    cross_validate_window,
    extract_window,
    minor_repair,
    proposal_write,
    qa_review,
    reduce_entities,
    rerun_window,
    segment_manifest,
)


def build_tool_registry() -> dict:
    """Return a mapping of tool_name → callable for the supervisor policy loop."""
    return {
        "segment_manifest": segment_manifest,
        "extract_window": extract_window,
        "cross_validate_window": cross_validate_window,
        "rerun_window": rerun_window,
        "reduce_entities": reduce_entities,
        "architect_timeline": architect_timeline,
        "qa_review": qa_review,
        "minor_repair": minor_repair,
        "proposal_write": proposal_write,
    }
