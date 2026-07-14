"""Focused contracts for supervisor post-architect density and staging semantics."""
from sidecar.supervisor.timeline_density import enforce_timeline_density
from sidecar.supervisor.policy import _prepare_reviewer_staging_state
from sidecar.supervisor.reviewers.quality_reviewer import QualityReviewer


def _event(index: int, chapter: int, title: str, importance: int) -> dict:
    return {
        "id": f"event_{index}", "title": title, "branchId": "branch_import_main",
        "orderIndex": index, "sourceOrder": index, "chapterRange": {"start": str(chapter), "end": str(chapter)},
        "importanceScore": importance, "confidence": 0.9, "causalRole": "turning_point",
        "sourceSpan": {"absolute_start": index * 10, "absolute_end": index * 10 + 9},
    }


def test_density_caps_real_shape_preserves_chapter_coverage_and_provenance():
    events = [_event(index, index + 1, f"Chapter {index + 1} turning point {index}", 100 - index) for index in range(10)]
    events.extend([
        _event(10, 1, "Chapter 1 mentor accepts disciple", 80),
        _event(11, 1, "Chapter 1 quiet departure", 79),
        _event(12, 8, "Chapter 8 side conversation", 78),
        _event(13, 8, "Chapter 8 minor discovery", 77),
    ])
    events[0]["title"] = "Chapter 1 mentor accepts novice"
    state = {"timeline_architecture": {"canonical_events": events, "scene_beats": [], "density_policy": {"max_events_per_branch": 36}}, "entity_registry": {"events": {event["id"]: dict(event) for event in events}}}

    result = enforce_timeline_density(state)
    architecture = result["timeline_architecture"]
    retained = architecture["canonical_events"]

    assert len(retained) == 10
    assert {event["chapterRange"]["start"] for event in retained} == {str(i) for i in range(1, 11)}
    assert [event["orderIndex"] for event in retained] == list(range(10))
    assert architecture["density_policy"]["max_events_per_branch"] == 10
    assert architecture["density_policy"]["post_architect_enforced"] is True
    assert any(change["action"] == "merged" for change in architecture["density_adjustments"])
    assert any(change["action"] == "demoted" for change in architecture["density_adjustments"])
    assert any(event.get("contributingSourceSpans") for event in retained)
    assert all(event.get("timelineClass") == "scene_beat" for event in architecture["scene_beats"])


def test_quality_reviewer_accepts_preproposal_staged_projection_inputs():
    report = QualityReviewer().review({
        "proposals": [], "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "converge_target": {}, "manuscript_chapters": [],
        "reviewer_staged_projection_metrics": {"phase": "preproposal", "source": "staged_projection", "inputs_present": True, "chapter_count": 10, "node_count": 20},
    })

    assert "manuscript_empty" not in [finding["check_name"] for finding in report["findings"]]


def test_policy_prepares_chunk_backed_staged_projection_metrics():
    state = _prepare_reviewer_staging_state({
        "manuscript_chapters": [],
        "chunks": [{"content": f"chapter {index}"} for index in range(10)],
    })

    assert state["reviewer_staged_projection_metrics"] == {
        "phase": "preproposal", "source": "chunk_projection_inputs", "inputs_present": True,
        "chapter_count": 10, "node_count": 20,
    }
