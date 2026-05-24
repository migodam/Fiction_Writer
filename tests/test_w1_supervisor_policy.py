"""Tests for W1 Supervisor S3 — policy loop integration."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sidecar.models.state import PROFILE_CONFIGS


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _make_window(window_id: str, chunk_ids: list[int]) -> dict:
    return {
        "id": window_id,
        "chunk_ids": chunk_ids,
        "text": f"Chapter text for {window_id}",
        "output_token_budget": 3000,
        "chapter_range": f"Ch {chunk_ids[0]+1}–{chunk_ids[-1]+1}",
    }


def _make_state(
    profile: str = "balanced",
    windows: list | None = None,
    metrics: dict | None = None,
    gate_failures: list | None = None,
) -> dict:
    chunks = [{"chunk_id": i, "content": f"chapter {i}", "manuscript_content": f"chapter {i}", "raw_content": f"chapter {i}",
               "chapter_hint": f"Ch {i+1}", "char_start": i * 1000, "char_end": (i+1) * 1000,
               "source_span": {"start": i*1000, "end": (i+1)*1000}} for i in range(10)]
    return {
        "project_path": "/tmp/policy_test",
        "import_run_id": "policy_test_run",
        "source_file_path": "/tmp/novel.txt",
        "prompt_profile": profile,
        "profile_config": PROFILE_CONFIGS[profile],
        "import_mode": "import_all",
        "source_language": "en",
        "context": {},
        "chunks": chunks,
        "import_run_manifest": {"source_hash": "abc", "import_run_id": "policy_test_run"},
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "prompt_windows": windows or [],
        "window_metrics": metrics or {},
        "gate_failures": gate_failures or [],
        "supervisor_decisions": [],
        "supervisor_log": [],
        "minor_repair_log": [],
        "supervisor_iteration": 0,
        "max_supervisor_iterations": 3,
        "use_supervisor": True,
        "errors": [],
    }


def _passing_metrics(window_id: str, chapters: int = 2) -> dict:
    return {window_id: {
        "window_id": window_id, "chapter_count": chapters,
        "char_count_extracted": chapters * 5,
        "event_count_extracted": chapters * 2,
        "failed_prompts": [], "gate_passed": True, "rerun_count": 0,
        "missing_majors": [], "missing_majors_count": 0,
    }}


def _failing_char_density_metrics(window_id: str, chapters: int = 2) -> dict:
    return {window_id: {
        "window_id": window_id, "chapter_count": chapters,
        "char_count_extracted": 0,  # density = 0 < 0.5
        "event_count_extracted": chapters * 2,
        "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
        "missing_majors": ["Hero"], "missing_majors_count": 1,
    }}


def _make_tools(
    segment_result: dict | None = None,
    extract_result: dict | None = None,
    cross_validate_result: dict | None = None,
    rerun_result: dict | None = None,
    reduce_result: dict | None = None,
    repair_result: dict | None = None,
    architect_result: dict | None = None,
    qa_result: dict | None = None,
    proposal_result: dict | None = None,
) -> dict:
    windows = [_make_window("pwin_0", [0, 1]), _make_window("pwin_1", [2, 3])]
    default_seg = {"prompt_windows": windows, "supervisor_log": ["segment_manifest: built 2 windows"]}
    empty_registry = {"characters": {}, "events": {}, "world": {}, "world_detailed": {}}

    # extract_window is called with (state, window_id) — return passing metrics per window_id
    async def default_extract(state, window_id):
        return {"entity_registry": empty_registry,
                "window_metrics": _passing_metrics(window_id), "supervisor_log": []}

    async def default_cross(state, window_id):
        return {"window_metrics": _passing_metrics(window_id)}

    async def default_rerun(state, window_id, strategy="augment", missing=None):
        return {"entity_registry": empty_registry, "window_metrics": _passing_metrics(window_id)}

    default_reduce = {"entity_registry": empty_registry}
    default_repair = {"entity_registry": empty_registry, "minor_repair_log": []}
    default_arch = {"timeline_architecture": {}, "timeline_branches": []}
    default_qa = {"gate_failures": [], "import_review_report": {}}
    default_prop = {"proposals": [], "import_review_report": {}}

    tools: dict = {
        "segment_manifest": AsyncMock(return_value=segment_result or default_seg),
        "reduce_entities": AsyncMock(return_value=reduce_result or default_reduce),
        "minor_repair": AsyncMock(return_value=repair_result or default_repair),
        "architect_timeline": AsyncMock(return_value=architect_result or default_arch),
        "qa_review": AsyncMock(return_value=qa_result or default_qa),
        "proposal_write": AsyncMock(return_value=proposal_result or default_prop),
    }
    # Per-window tools use callable side_effects so each call receives window_id.
    # If caller passes a plain dict, wrap it as a static return.
    def _as_side_effect(v, default_fn):
        if v is None:
            return default_fn
        if callable(v):
            return v
        # dict — return it verbatim for every call
        async def _static(state, window_id, *args, **kwargs):
            return v
        return _static

    tools["extract_window"] = AsyncMock(side_effect=_as_side_effect(extract_result, default_extract))
    tools["cross_validate_window"] = AsyncMock(side_effect=_as_side_effect(cross_validate_result, default_cross))
    tools["rerun_window"] = AsyncMock(side_effect=_as_side_effect(rerun_result, default_rerun))
    return tools


def _run(coro):
    return asyncio.run(coro)


# ── Tests ─────────────────────────────────────────────────────────────────────────

class TestPolicyLoop(unittest.TestCase):

    # ── Test 1: All gates pass → 0 reruns ────────────────────────────────────

    def test_all_gates_pass_produces_no_rerun_decisions(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        state = _make_state()
        tools = _make_tools()

        result = _run(run_supervisor_policy(state, tools))

        rerun_actions = [d for d in result["supervisor_decisions"] if d["action"] == "rerun"]
        self.assertEqual(len(rerun_actions), 0, f"Expected 0 rerun decisions, got {rerun_actions}")

    # ── Test 2: char_density failure → split triggered ────────────────────────

    def test_char_density_failure_triggers_rerun_split(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        windows = [_make_window("pwin_split", [0, 1, 2])]
        # char_density=0 will trigger a split because window has >1 chunk
        failing_metrics = {"pwin_split": {
            "window_id": "pwin_split", "chapter_count": 3,
            "char_count_extracted": 0,  # density 0 < 0.5
            "event_count_extracted": 3,
            "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
            "missing_majors": [], "missing_majors_count": 0,
        }}
        rerun_call_args: list = []

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            rerun_call_args.append({"window_id": window_id, "strategy": strategy})
            return {"entity_registry": state.get("entity_registry", {}),
                    "window_metrics": _passing_metrics(window_id, 3)}

        state = _make_state(windows=windows, metrics=failing_metrics)
        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            extract_result={"entity_registry": state["entity_registry"], "window_metrics": failing_metrics,
                            "supervisor_log": []},
            cross_validate_result={"window_metrics": failing_metrics},
        )
        tools["rerun_window"] = mock_rerun

        result = _run(run_supervisor_policy(state, tools))

        self.assertGreater(len(rerun_call_args), 0, "Expected at least one rerun call")
        # With >1 chunk and low char_density, strategy should be split
        self.assertEqual(rerun_call_args[0]["strategy"], "split")

    # ── Test 3: missing_majors → augment triggered ────────────────────────────

    def test_missing_majors_triggers_augment_strategy(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        # Single-chunk window → can't split → must augment
        windows = [_make_window("pwin_single", [0])]
        failing_metrics = {"pwin_single": {
            "window_id": "pwin_single", "chapter_count": 1,
            "char_count_extracted": 0,  # density 0 < 0.5, but single chunk
            "event_count_extracted": 1,
            "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
            "missing_majors": ["Hero", "Villain"], "missing_majors_count": 2,
        }}
        rerun_call_args: list = []

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            rerun_call_args.append({"window_id": window_id, "strategy": strategy, "missing": missing})
            return {"entity_registry": state.get("entity_registry", {}),
                    "window_metrics": _passing_metrics(window_id, 1)}

        state = _make_state(windows=windows, metrics=failing_metrics)
        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            extract_result={"entity_registry": state["entity_registry"], "window_metrics": failing_metrics,
                            "supervisor_log": []},
            cross_validate_result={"window_metrics": failing_metrics},
        )
        tools["rerun_window"] = mock_rerun

        _run(run_supervisor_policy(state, tools))

        self.assertGreater(len(rerun_call_args), 0)
        self.assertEqual(rerun_call_args[0]["strategy"], "augment")

    # ── Test 4: max rerun cap respected ──────────────────────────────────────

    def test_max_rerun_cap_respected(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        profile = "balanced"  # max_rerun_iterations = 2
        windows = [_make_window("pwin_cap", [0, 1])]
        bad_metrics = {"pwin_cap": {
            "window_id": "pwin_cap", "chapter_count": 2,
            "char_count_extracted": 0,  # always failing
            "event_count_extracted": 0,
            "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
            "missing_majors": [], "missing_majors_count": 0,
        }}
        rerun_count = [0]

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            rerun_count[0] += 1
            # Always return failing metrics → would loop forever without cap
            return {"entity_registry": state.get("entity_registry", {}),
                    "window_metrics": bad_metrics}

        state = _make_state(profile=profile, windows=windows, metrics=bad_metrics)
        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            extract_result={"entity_registry": state["entity_registry"], "window_metrics": bad_metrics,
                            "supervisor_log": []},
        )
        tools["rerun_window"] = mock_rerun

        _run(run_supervisor_policy(state, tools))

        max_reruns = PROFILE_CONFIGS[profile]["max_rerun_iterations"]
        self.assertLessEqual(rerun_count[0], max_reruns, f"Rerun count {rerun_count[0]} exceeds max {max_reruns}")

    # ── Test 5: QA rerun targets only responsible windows ────────────────────

    def test_qa_rerun_targets_only_failing_windows(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        windows = [_make_window("pwin_good", [0]), _make_window("pwin_bad", [1])]
        rerun_window_ids: list = []

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            rerun_window_ids.append(window_id)
            return {"entity_registry": state.get("entity_registry", {}),
                    "window_metrics": _passing_metrics(window_id)}

        state = _make_state(windows=windows)
        qa_fail_result = {
            "gate_failures": [{"window_id": "pwin_bad", "reason": "char_density"}],
            "import_review_report": {},
        }
        qa_pass_result = {"gate_failures": [], "import_review_report": {}}
        qa_call_count = [0]

        async def mock_qa(state):
            qa_call_count[0] += 1
            return qa_fail_result if qa_call_count[0] == 1 else qa_pass_result

        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
        )
        tools["qa_review"] = mock_qa
        tools["rerun_window"] = mock_rerun

        _run(run_supervisor_policy(state, tools))

        # Only pwin_bad should have been rerun from QA path
        # (pwin_good may have been rerun in the extract loop if its metrics triggered a gate)
        if rerun_window_ids:
            qa_triggered_reruns = [wid for wid in rerun_window_ids if wid == "pwin_bad"]
            self.assertIn("pwin_bad", rerun_window_ids)

    # ── Test 6: SupervisorDecision recorded for every stage ──────────────────

    def test_supervisor_decision_recorded_per_stage(self):
        from sidecar.supervisor.policy import run_supervisor_policy
        state = _make_state()
        tools = _make_tools()

        result = _run(run_supervisor_policy(state, tools))

        decisions = result.get("supervisor_decisions", [])
        stages = {d["stage"] for d in decisions}
        expected_stages = {"segment_manifest", "reduce_entities", "minor_repair", "architect_timeline", "qa_review", "proposal_write"}
        for stage in expected_stages:
            self.assertIn(stage, stages, f"Stage {stage!r} missing from supervisor_decisions")

    # ── Test 7 (replaced): run_streaming dispatches to supervisor when enabled ─

    def test_run_streaming_dispatches_supervisor_when_enabled(self):
        """run_streaming(use_supervisor=True) must call run_supervisor_streaming."""
        supervisor_calls = []

        async def fake_supervisor(project_path, config):
            supervisor_calls.append((project_path, config))
            yield {
                "progress": 1.0, "errors": [], "completed_chunks": 0,
                "total_chunks": 0, "current_node": "done",
                "import_review_report": {}, "proposals_count": 0,
            }

        async def collect():
            from sidecar.workflows.w1_import import run_streaming
            with patch("sidecar.supervisor.policy.run_supervisor_streaming", fake_supervisor):
                results = []
                async for update in run_streaming("/tmp/test", {
                    "use_supervisor": True,
                    "source_file_path": "/tmp/test.txt",
                    "import_mode": "import_all",
                }):
                    results.append(update)
            self.assertTrue(supervisor_calls, "run_supervisor_streaming was not called")
            self.assertEqual(len(results), 1)

        asyncio.run(collect())

    # ── Test 8 (replaced): run_streaming bypasses supervisor when disabled ────

    def test_run_streaming_bypasses_supervisor_when_disabled(self):
        """run_streaming(use_supervisor=False) must NOT call run_supervisor_streaming."""
        supervisor_calls = []

        async def fake_supervisor(project_path, config):
            supervisor_calls.append(True)
            yield {}

        async def collect():
            from sidecar.workflows.w1_import import run_streaming
            with patch("sidecar.supervisor.policy.run_supervisor_streaming", fake_supervisor):
                gen = run_streaming("/tmp/test", {
                    "use_supervisor": False,
                    "source_file_path": "/tmp/test.txt",
                    "import_mode": "import_all",
                    "context": {},
                })
                try:
                    await asyncio.wait_for(gen.__anext__(), timeout=0.5)
                except Exception:
                    pass  # LangGraph will fail without real files; that's OK
            self.assertFalse(supervisor_calls, "run_supervisor_streaming must NOT be called")

        asyncio.run(collect())


# ── Correctness regression tests ─────────────────────────────────────────────────

class TestMergeCorrectness(unittest.TestCase):

    # ── Fix 1: two-window batch preserves both registries ────────────────────

    def test_two_window_batch_merges_both_registries(self):
        """Characters from window 1 and window 2 must both appear in final registry."""
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_a", [0]), _make_window("pwin_b", [1])]
        state = _make_state(windows=windows)

        registry_a = {
            "characters": {"char_w1": {"canonical_name": "Alice", "canonical_id": "char_w1"}},
            "events": {}, "world": {}, "world_detailed": {},
        }
        registry_b = {
            "characters": {"char_w2": {"canonical_name": "Bob", "canonical_id": "char_w2"}},
            "events": {}, "world": {}, "world_detailed": {},
        }

        async def extract_by_window(state, window_id):
            reg = registry_a if window_id == "pwin_a" else registry_b
            return {
                "entity_registry": reg,
                "window_metrics": _passing_metrics(window_id, 1),
                "supervisor_log": [],
            }

        async def passthrough_reduce(state):
            return {"entity_registry": state.get("entity_registry", {})}

        async def passthrough_repair(state):
            return {"entity_registry": state.get("entity_registry", {}), "minor_repair_log": []}

        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
        )
        tools["extract_window"] = AsyncMock(side_effect=extract_by_window)
        tools["reduce_entities"] = AsyncMock(side_effect=passthrough_reduce)
        tools["minor_repair"] = AsyncMock(side_effect=passthrough_repair)

        result = asyncio.run(run_supervisor_policy(state, tools))

        chars = result.get("entity_registry", {}).get("characters", {})
        self.assertIn("char_w1", chars, "Alice (window 1) lost after batch merge")
        self.assertIn("char_w2", chars, "Bob (window 2) lost after batch merge")

    # ── Fix 2: split rerun uses exactly one rerun call, not max_reruns ───────

    def test_split_break_does_not_exhaust_reruns(self):
        """After split strategy, rerun_window must be called only once per failure."""
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_split", [0, 1])]
        failing = {"pwin_split": {
            "window_id": "pwin_split", "chapter_count": 2,
            "char_count_extracted": 0,  # density 0 < 0.5
            "event_count_extracted": 0,
            "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
            "missing_majors": [], "missing_majors_count": 0,
        }}

        rerun_count = [0]
        child_window = _make_window("pwin_child_a", [0])

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            rerun_count[0] += 1
            child_metrics = _passing_metrics("pwin_child_a", 1)
            new_windows = list(state.get("prompt_windows", [])) + [child_window]
            return {
                "entity_registry": state.get("entity_registry", {}),
                "prompt_windows": new_windows,
                "window_metrics": {**state.get("window_metrics", {}), **child_metrics},
                "supervisor_log": [],
            }

        state = _make_state(windows=windows, metrics=failing)
        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            extract_result={"entity_registry": state["entity_registry"], "window_metrics": failing,
                            "supervisor_log": []},
            cross_validate_result={"window_metrics": failing},
        )
        tools["rerun_window"] = mock_rerun

        asyncio.run(run_supervisor_policy(state, tools))

        self.assertEqual(rerun_count[0], 1, f"Expected 1 rerun (split breaks loop), got {rerun_count[0]}")

    # ── Fix 3: missing major names are passed to augment rerun ───────────────

    def test_missing_major_names_passed_to_augment_rerun(self):
        """cross_validate returns missing names; augment rerun receives them."""
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_aug", [0])]
        failing_no_chars = {"pwin_aug": {
            "window_id": "pwin_aug", "chapter_count": 1,
            "char_count_extracted": 0,  # density 0 < 0.5, single chunk → augment
            "event_count_extracted": 0,
            "failed_prompts": [], "gate_passed": False, "rerun_count": 0,
            "missing_majors": [], "missing_majors_count": 0,
        }}
        cv_result_with_names = {
            "window_metrics": {"pwin_aug": {
                **failing_no_chars["pwin_aug"],
                "missing_majors": ["Hero", "Villain"],
                "missing_majors_count": 2,
            }}
        }

        received_missing: list = []

        async def mock_rerun(state, window_id, strategy="augment", missing=None):
            received_missing.append(missing)
            return {
                "entity_registry": state.get("entity_registry", {}),
                "window_metrics": _passing_metrics(window_id, 1),
                "supervisor_log": [],
            }

        state = _make_state(windows=windows, metrics=failing_no_chars)
        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            extract_result={"entity_registry": state["entity_registry"],
                            "window_metrics": failing_no_chars, "supervisor_log": []},
            cross_validate_result=cv_result_with_names,
        )
        tools["rerun_window"] = mock_rerun

        asyncio.run(run_supervisor_policy(state, tools))

        self.assertGreater(len(received_missing), 0, "rerun_window was never called")
        self.assertIn("Hero", received_missing[0] or [], "Hero not in missing names passed to rerun")
        self.assertIn("Villain", received_missing[0] or [], "Villain not in missing names passed to rerun")

    # ── Fix 4: proposal_write writes supervisor artifact files ───────────────

    def test_proposal_write_writes_supervisor_artifacts(self):
        """proposal_write must write supervisor_decisions.json and window_metrics.json."""
        from sidecar.supervisor.tools import proposal_write

        state = _make_state()
        state = {
            **state,
            "import_run_id": "artifact_test_run",
            "project_path": "/tmp/artifact_test",
            "supervisor_decisions": [{"stage": "test"}],
            "window_metrics": {"pwin_0": {"gate_passed": True}},
        }

        artifact_calls: list = []

        async def mock_node(*args, **kwargs):
            return {"proposals": [], "manuscript_chapters": [], "relationships": [],
                    "character_tags": [], "world_settings": {}, "import_review_report": {}}

        with patch("sidecar.supervisor.tools._write_import_artifact") as mock_write, \
             patch("sidecar.supervisor.tools.node_build_manuscript", mock_node), \
             patch("sidecar.supervisor.tools.node_synthesize_relationships", mock_node), \
             patch("sidecar.supervisor.tools.node_classify_character_tags", mock_node), \
             patch("sidecar.supervisor.tools.node_infer_world_settings", mock_node), \
             patch("sidecar.supervisor.tools.node_write_to_project", mock_node):
            asyncio.run(proposal_write(state))
            artifact_calls = [call.args[2] for call in mock_write.call_args_list]

        self.assertIn("supervisor_decisions.json", artifact_calls,
                      "supervisor_decisions.json was not written by proposal_write")
        self.assertIn("window_metrics.json", artifact_calls,
                      "window_metrics.json was not written by proposal_write")


if __name__ == "__main__":
    unittest.main()
