"""Focused W1 backend contract tests for source provenance and orchestration."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from sidecar.models.state import (
    make_source_span,
    reconstruct_source_span,
    validate_source_span,
)
from sidecar.supervisor.planner import resolve_planner_next_action, validate_planner_proposal
from sidecar.supervisor.policy import _apply_initial_planner_action, run_supervisor_policy
from sidecar.workflows import w1_import
from sidecar.workflows import w1_run_events


def test_source_span_reconstructs_the_original_source_substring():
    raw_source = "Chapter 1\nAlice enters.\n\nChapter 2\nBob leaves."
    span = make_source_span(raw_source, 10, 23)

    assert span["raw_source_hash"]
    assert span["absolute_start"] == 10
    assert span["absolute_end"] == 23
    assert validate_source_span(span, raw_source) == (True, [])
    assert reconstruct_source_span(span, raw_source) == raw_source[10:23]


def test_source_span_rejects_tampered_offsets_and_hashes():
    raw_source = "Chapter 1\nAlice enters."
    span = make_source_span(raw_source, 0, len(raw_source))
    span["substring_hash"] = "not-a-real-hash"

    ok, errors = validate_source_span(span, raw_source)

    assert not ok
    assert any("substring_hash" in error for error in errors)


def test_import_all_chapter_body_comes_from_raw_source_not_llm_output(tmp_path):
    raw_source = "Chapter 1\nCanonical manuscript prose."
    span = make_source_span(raw_source, 0, len(raw_source))
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "import_mode": "import_all",
        "source_text": raw_source,
        "chunks": [{
            "chunk_id": 0,
            "chapter_hint": "Chapter 1",
            "manuscript_content": raw_source,
            "source_span": span,
        }],
        "chunk_extractions": [{
            "chunk_id": 0,
            "manuscript_content": "LLM-invented chapter body",
        }],
    }

    result = asyncio.run(w1_import.node_build_manuscript(state))

    chapter = result["manuscript_chapters"][0]
    assert chapter["manuscript_content"] == raw_source
    assert chapter["source_span"] == span


def test_preaccept_import_stages_manuscript_without_canonical_writes(tmp_path, monkeypatch):
    raw_source = "Chapter 1\nCanonical manuscript prose."
    source_path = tmp_path / "novel.txt"
    source_path.write_text(raw_source, encoding="utf-8")
    span = make_source_span(raw_source, 0, len(raw_source))
    staged_chapter = {
        "chapter_id": "chap_import_1",
        "title": "Chapter 1",
        "chunk_ids": [0],
        "manuscript_content": raw_source,
        "source_span": span,
    }
    proposals: list[dict] = []

    async def capture_proposal(operation, _project_path):
        proposals.append(operation)
        return {"id": f"proposal_{len(proposals)}", "status": "pending"}

    monkeypatch.setattr(w1_import.s2_memory_writer, "propose_write", capture_proposal)
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(source_path),
        "source_text": raw_source,
        "import_run_id": "import_contract",
        "source_language": "en",
        "entity_registry": {"characters": {}, "events": {}, "world": {}},
        "manuscript_chapters": [staged_chapter],
        "relationships": [],
        "character_tags": [],
        "world_settings": {},
        "timeline_branches": [],
        "world_containers": [],
    }

    asyncio.run(w1_import.node_write_to_project(state))

    staged_path = tmp_path / "system" / "imports" / "import_contract" / "staged_manuscript_projection.json"
    assert staged_path.exists()
    staged = json.loads(staged_path.read_text(encoding="utf-8"))
    assert staged["acceptance_required"] is True
    assert staged["chapters"][0]["source_span"] == span
    assert not (tmp_path / "manuscript.json").exists()
    assert not (tmp_path / "writing" / "manuscript" / "nodes.json").exists()
    chapter_proposal = next(p for p in proposals if p["entity_type"] == "chapter")
    assert chapter_proposal["data"]["stagedManuscriptProjection"]["artifact_path"].endswith(
        "staged_manuscript_projection.json"
    )


def test_planner_next_action_rejects_unregistered_tools_and_bounds_reruns():
    proposal = {
        "planner_kind": "llm_proposed",
        "proposed_source_type": "balanced_novel",
        "next_action": {"kind": "tool", "tool": "delete_project"},
    }
    ok, errors = validate_planner_proposal(proposal)
    assert not ok
    assert any("next_action.tool" in error for error in errors)

    bounded = resolve_planner_next_action(
        {"next_action": {"kind": "rerun", "window_id": "pwin_1"}},
        registered_tools={"rerun_window"},
        default_tool="proposal_write",
        iteration=2,
        max_iterations=2,
        budget_exhausted=False,
    )
    assert bounded == {"kind": "tool", "tool": "proposal_write", "reason": "rerun_bound_reached"}


def test_validated_planner_stop_happens_before_any_supervisor_tool(tmp_path):
    segment_manifest = AsyncMock()
    state = {
        "project_path": str(tmp_path),
        "source_file_path": str(tmp_path / "novel.txt"),
        "prompt_profile": "balanced",
        "chunks": [],
        "context": {"planner_proposal": {
            "planner_kind": "llm_proposed",
            "proposed_source_type": "balanced_novel",
            "next_action": {"kind": "stop", "reason": "human review requested"},
        }},
        "planner_proposal": {
            "planner_kind": "llm_proposed",
            "proposed_source_type": "balanced_novel",
            "next_action": {"kind": "stop", "reason": "human review requested"},
        },
        "supervisor_iteration": 0,
        "max_supervisor_iterations": 2,
        "budget_exhausted": False,
    }

    result = asyncio.run(run_supervisor_policy(state, {"segment_manifest": segment_manifest}))

    segment_manifest.assert_not_awaited()
    assert result["planner_next_action"]["kind"] == "stop"


def test_planner_rerun_executes_registered_tool_and_out_of_order_tool_falls_back():
    rerun = AsyncMock(return_value={"supervisor_log": ["rerun executed"]})
    state = {"prompt_windows": [{"id": "pwin_1"}], "supervisor_log": [], "supervisor_decisions": []}

    result = asyncio.run(_apply_initial_planner_action(
        state, {"rerun_window": rerun},
        {"kind": "rerun", "window_id": "pwin_1"},
    ))

    rerun.assert_awaited_once()
    assert any(decision["tool_called"] == "rerun_window" for decision in result["supervisor_decisions"])

    fallback = asyncio.run(_apply_initial_planner_action(
        {"prompt_windows": [], "supervisor_log": []}, {"segment_manifest": AsyncMock()},
        {"kind": "tool", "tool": "proposal_write"},
    ))
    assert fallback["planner_next_action"]["reason"] == "out_of_order_tool_fallback"


def test_budget_policy_missing_usage_fails_the_completed_provider_call_closed():
    session_id = "f1-budget-missing-usage"
    w1_run_events.clear_session(session_id)
    w1_import.configure_w1_budget(
        {"budget_policy": {"max_calls": 3}, "context": {"model": "deepseek-v4-flash"}}, session_id,
    )

    class Response:
        usage_metadata = None
        response_metadata = {}
        content = "{}"

    llm = MagicMock(model_name="deepseek-v4-flash")
    llm.ainvoke = AsyncMock(return_value=Response())
    try:
        asyncio.run(w1_import._ainvoke_with_budget(llm, [], session_id=session_id))
        assert False, "missing provider usage must fail the completed call"
    except RuntimeError as exc:
        assert "missing_usage" in str(exc)
    assert llm.ainvoke.await_count == 1
    w1_run_events.clear_session(session_id)


def test_usage_ledger_artifact_is_authoritative_and_non_secret(tmp_path):
    session_id = "f1-usage-artifact"
    w1_run_events.clear_session(session_id)
    w1_import.configure_w1_budget(
        {"budget_policy": {"max_calls": 3}, "context": {"model": "deepseek-v4-flash"}}, session_id,
    )
    assert w1_run_events.record_call_usage(session_id, 321, 123, model="deepseek-v4-flash")

    ledger = w1_import.persist_w1_usage_ledger({
        "project_path": str(tmp_path),
        "import_run_id": "run_usage",
        "session_id": session_id,
        "context": {"model": "deepseek-v4-flash"},
    })

    artifact = json.loads((tmp_path / "system" / "imports" / "run_usage" / "usage_ledger.json").read_text(encoding="utf-8"))
    assert artifact == ledger
    assert artifact["actual_input_tokens"] == 321
    assert artifact["actual_output_tokens"] == 123
    assert artifact["actual_calls"] == artifact["api_call_count"] == 1
    assert artifact["budget_status"]["exhausted"] is False
    assert "api_key" not in json.dumps(artifact).lower()
    assert not list((tmp_path / "system" / "imports" / "run_usage").glob(".usage_ledger.json.*.tmp"))
    w1_run_events.clear_session(session_id)
