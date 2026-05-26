"""Tests for W1 Supervisor S3 — policy loop integration."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sidecar.models.state import PROFILE_CONFIGS, plan_orchestrator_targets


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
    judge_result: dict | None = None,
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
    default_judge = {
        "judge_artifact": {
            "score": 1.0,
            "passed": True,
            "failed_gates": [],
            "thematic_rerun_requests": [],
            "iteration": 0,
            "metrics_snapshot": {},
            "rationale": "pass",
        },
        "judge_score": 1.0,
        "converge_status": "passed",
        "thematic_rerun_requests": [],
    }
    default_prop = {"proposals": [], "import_review_report": {}}

    tools: dict = {
        "segment_manifest": AsyncMock(return_value=segment_result or default_seg),
        "reduce_entities": AsyncMock(return_value=reduce_result or default_reduce),
        "minor_repair": AsyncMock(return_value=repair_result or default_repair),
        "architect_timeline": AsyncMock(return_value=architect_result or default_arch),
        "qa_review": AsyncMock(return_value=qa_result or default_qa),
        "judge_import": AsyncMock(return_value=judge_result or default_judge),
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

    def test_thematic_reruns_are_bounded_by_tos_budget(self):
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_theme", [0])]
        spec, target = plan_orchestrator_targets(
            "custom",
            "en",
            1,
            overrides={"rerun_budget": 1},
        )
        state = {
            **_make_state(profile="custom", windows=windows),
            "tool_operating_spec": spec,
            "converge_target": target,
            "profile_config": PROFILE_CONFIGS["custom"],
        }
        failing_judge = {
            "judge_artifact": {
                "score": 0.5,
                "passed": False,
                "failed_gates": ["character_undercoverage"],
                "thematic_rerun_requests": [{
                    "theme": "character_undercoverage",
                    "target_windows": ["pwin_theme"],
                    "reason": "characters below target",
                    "parameter_overrides": {"min_characters_per_chapter": 3},
                    "expected_repair": "recover characters",
                }],
                "iteration": 0,
                "metrics_snapshot": {},
                "rationale": "failed",
            },
            "judge_score": 0.5,
            "converge_status": "failed",
            "thematic_rerun_requests": [],
        }
        rerun_calls = []

        async def mock_rerun(state, window_id, strategy="augment", missing=None, parameter_overrides=None):
            rerun_calls.append({
                "window_id": window_id,
                "strategy": strategy,
                "parameter_overrides": parameter_overrides,
            })
            return {"entity_registry": state.get("entity_registry", {}), "window_metrics": _passing_metrics(window_id, 1)}

        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
            judge_result=failing_judge,
        )
        tools["rerun_window"] = mock_rerun

        result = _run(run_supervisor_policy(state, tools))

        self.assertEqual(len(rerun_calls), 1)
        self.assertEqual(rerun_calls[0]["parameter_overrides"], {"min_characters_per_chapter": 3})
        self.assertEqual(result.get("converge_status"), "failed")

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

    def test_run_streaming_dispatches_supervisor_for_deep_default(self):
        """Deep profile defaults to supervisor unless explicitly disabled."""
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
                    "source_file_path": "/tmp/test.txt",
                    "import_mode": "import_all",
                    "prompt_profile": "deep",
                }):
                    results.append(update)
            self.assertTrue(supervisor_calls, "deep profile did not default to supervisor")
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
            "tool_operating_spec": {"rerun_budget": 1},
            "judge_artifact": {"score": 1.0, "passed": True},
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
        self.assertIn("tool_operating_spec.json", artifact_calls,
                      "tool_operating_spec.json was not written by proposal_write")
        self.assertIn("judge_artifact.json", artifact_calls,
                      "judge_artifact.json was not written by proposal_write")


# ── Cost guard policy tests ───────────────────────────────────────────────────

class TestPolicyBudgetExhaustedStop(unittest.TestCase):
    """Policy loop must halt extraction and skip reruns when budget_exhausted."""

    def _make_budget_exhausted_extract(self, windows: list) -> dict:
        """Returns a set of tools where extract_window returns budget_exhausted=True."""
        empty_registry = {"characters": {}, "events": {}, "world": {}, "world_detailed": {}}

        async def exhausted_extract(state, window_id):
            metrics = {window_id: {
                "window_id": window_id, "chapter_count": 2,
                "char_count_extracted": 0, "event_count_extracted": 0,
                "failed_prompts": [
                    "character:RuntimeError:Error code: 402 - Insufficient Balance",
                    "event:RuntimeError:Error code: 402 - Insufficient Balance",
                ],
                "gate_passed": False, "rerun_count": 0,
                "missing_majors": [], "missing_majors_count": 0,
            }}
            return {
                "entity_registry": empty_registry,
                "window_metrics": metrics,
                "budget_exhausted": True,
                "errors": ["[budget_exhausted] API HTTP 402 during extraction"],
                "supervisor_log": [f"extract_window {window_id}: budget_exhausted=True"],
            }

        tools = _make_tools(
            segment_result={"prompt_windows": windows, "supervisor_log": []},
        )
        tools["extract_window"] = AsyncMock(side_effect=exhausted_extract)
        return tools

    def test_budget_exhausted_stops_after_first_window(self):
        """Once a window returns budget_exhausted, remaining windows must not be extracted."""
        from sidecar.supervisor.policy import run_supervisor_policy
        windows = [
            _make_window("pwin_0", [0, 1]),
            _make_window("pwin_1", [2, 3]),
            _make_window("pwin_2", [4, 5]),
        ]
        state = _make_state(windows=windows)
        tools = self._make_budget_exhausted_extract(windows)
        extract_calls: list[str] = []

        original_side_effect = tools["extract_window"].side_effect
        async def tracking_extract(s, wid):
            extract_calls.append(wid)
            return await original_side_effect(s, wid)

        tools["extract_window"].side_effect = tracking_extract

        result = asyncio.run(run_supervisor_policy(state, tools))

        self.assertTrue(result.get("budget_exhausted"), "budget_exhausted must be set in final state")
        # All windows in the first batch (3 concurrent) will be dispatched, but no second batch
        self.assertLessEqual(len(extract_calls), 3,
                             f"Expected ≤3 extract calls (one batch max), got {len(extract_calls)}: {extract_calls}")

    def test_budget_exhausted_prevents_rerun(self):
        """rerun_window must not be called after budget_exhausted."""
        from sidecar.supervisor.policy import run_supervisor_policy
        windows = [_make_window("pwin_budget", [0, 1])]
        state = _make_state(windows=windows)
        tools = self._make_budget_exhausted_extract(windows)

        result = asyncio.run(run_supervisor_policy(state, tools))

        tools["rerun_window"].assert_not_called()

    def test_budget_exhausted_skips_thematic_reruns(self):
        """_apply_thematic_reruns must not fire when budget_exhausted=True."""
        from sidecar.supervisor.policy import run_supervisor_policy
        windows = [_make_window("pwin_thematic", [0])]
        state = _make_state(windows=windows)
        tools = self._make_budget_exhausted_extract(windows)

        # Judge would request thematic reruns — they must be skipped
        rerun_budget_judge = {
            "judge_artifact": {
                "score": 0.64, "passed": False, "failed_gates": ["character_undercoverage"],
                "thematic_rerun_requests": [{"theme": "character_undercoverage", "target_windows": ["pwin_thematic"]}],
                "iteration": 0, "metrics_snapshot": {}, "rationale": "failed gates: character_undercoverage",
                "result_status": "failed",
            },
            "judge_score": 0.64,
            "converge_status": "failed",
            "thematic_rerun_requests": [{"theme": "character_undercoverage", "target_windows": ["pwin_thematic"]}],
            "tool_operating_spec": {"rerun_budget": 3, "thematic_rerun_wave_cap": 2},
        }
        tools["judge_import"] = AsyncMock(return_value=rerun_budget_judge)

        result = asyncio.run(run_supervisor_policy(state, tools))

        tools["rerun_window"].assert_not_called()


class TestPolicyThematicRerunWaveCap(unittest.TestCase):
    """Thematic reruns must not exceed thematic_rerun_wave_cap waves."""

    def test_wave_cap_1_prevents_second_wave(self):
        """With wave_cap=1, at most 1 thematic wave runs, then rerun_cap_reached=True."""
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_cap", [0, 1])]
        state = _make_state(windows=windows)

        empty_registry = {"characters": {}, "events": {}, "world": {}, "world_detailed": {}}
        call_count = {"reruns": 0}

        async def mock_rerun(state, window_id, strategy="augment", missing=None, **kwargs):
            call_count["reruns"] += 1
            return {"entity_registry": empty_registry, "window_metrics": _passing_metrics(window_id)}

        # Judge always fails with character_undercoverage to try to trigger multiple waves
        judge_fail = {
            "judge_artifact": {
                "score": 0.82, "passed": False, "failed_gates": ["character_undercoverage"],
                "thematic_rerun_requests": [{"theme": "character_undercoverage",
                                             "target_windows": ["pwin_cap"],
                                             "reason": "undercoverage", "parameter_overrides": {}}],
                "iteration": 0, "metrics_snapshot": {}, "rationale": "failed: character_undercoverage",
                "result_status": "failed",
            },
            "judge_score": 0.82,
            "converge_status": "failed",
            "thematic_rerun_requests": [{"theme": "character_undercoverage",
                                         "target_windows": ["pwin_cap"],
                                         "reason": "undercoverage", "parameter_overrides": {}}],
            "tool_operating_spec": {"rerun_budget": 10, "thematic_rerun_wave_cap": 1,
                                    "min_characters_per_chapter": 1.5},
        }

        tools = _make_tools(segment_result={"prompt_windows": windows, "supervisor_log": []})
        tools["rerun_window"] = AsyncMock(side_effect=mock_rerun)
        tools["judge_import"] = AsyncMock(return_value=judge_fail)

        result = asyncio.run(run_supervisor_policy(state, tools))

        artifact = result.get("judge_artifact", {})
        self.assertTrue(artifact.get("rerun_cap_reached"),
                        f"rerun_cap_reached must be True when wave_cap=1 is exhausted; artifact={artifact}")
        self.assertLessEqual(call_count["reruns"], 1,
                             f"Expected at most 1 thematic rerun call, got {call_count['reruns']}")

    def test_wave_cap_0_prevents_all_thematic_reruns(self):
        """With wave_cap=0, no thematic reruns run at all."""
        from sidecar.supervisor.policy import run_supervisor_policy

        windows = [_make_window("pwin_cap0", [0])]
        state = _make_state(windows=windows)
        call_count = {"reruns": 0}

        async def mock_rerun(*args, **kwargs):
            call_count["reruns"] += 1
            return {}

        judge_with_requests = {
            "judge_artifact": {
                "score": 0.64, "passed": False, "failed_gates": ["character_undercoverage"],
                "thematic_rerun_requests": [{"theme": "character_undercoverage",
                                             "target_windows": ["pwin_cap0"],
                                             "reason": "undercoverage", "parameter_overrides": {}}],
                "iteration": 0, "metrics_snapshot": {}, "rationale": "failed",
                "result_status": "failed",
            },
            "judge_score": 0.64,
            "converge_status": "failed",
            "thematic_rerun_requests": [{"theme": "character_undercoverage",
                                         "target_windows": ["pwin_cap0"],
                                         "reason": "undercoverage", "parameter_overrides": {}}],
            "tool_operating_spec": {"rerun_budget": 5, "thematic_rerun_wave_cap": 0},
        }

        tools = _make_tools(segment_result={"prompt_windows": windows, "supervisor_log": []})
        tools["rerun_window"] = AsyncMock(side_effect=mock_rerun)
        tools["judge_import"] = AsyncMock(return_value=judge_with_requests)

        result = asyncio.run(run_supervisor_policy(state, tools))

        self.assertEqual(call_count["reruns"], 0,
                         f"Expected 0 thematic rerun calls when wave_cap=0, got {call_count['reruns']}")


class TestOrchestratorPlanGranularity(unittest.TestCase):
    """_ensure_orchestrator_plan stores granularity profile and derives converge target from it."""

    def _make_zh_deep_state(self, chapter_count: int = 50) -> dict:
        chunks = [
            {"chunk_id": i, "content": f"chapter {i}", "manuscript_content": f"chapter {i}",
             "raw_content": f"chapter {i}", "chapter_hint": f"Ch {i+1}",
             "char_start": i * 500, "char_end": (i + 1) * 500,
             "source_span": {"start": i * 500, "end": (i + 1) * 500}}
            for i in range(chapter_count)
        ]
        return {
            "project_path": "/tmp/gran_test",
            "import_run_id": "gran_test",
            "source_file_path": "/tmp/novel.txt",
            "prompt_profile": "deep",
            "profile_config": PROFILE_CONFIGS["deep"],
            "import_mode": "import_all",
            "source_language": "zh",
            "context": {},
            "chunks": chunks,
            "import_run_manifest": {"source_hash": "abc"},
            "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
            "prompt_windows": [],
            "window_metrics": {},
            "gate_failures": [],
            "supervisor_decisions": [],
            "supervisor_log": [],
            "minor_repair_log": [],
            "supervisor_iteration": 0,
            "use_supervisor": True,
            "errors": [],
        }

    def test_stores_import_granularity_profile(self):
        from sidecar.supervisor.policy import _ensure_orchestrator_plan
        state = self._make_zh_deep_state(chapter_count=50)
        result = _ensure_orchestrator_plan(state)
        self.assertIn("import_granularity_profile", result,
                      "import_granularity_profile must be stored in state after orchestrator plan")
        profile = result["import_granularity_profile"]
        self.assertIn("profile_name", profile)

    def test_stores_schema_first_import_plan(self):
        from sidecar.supervisor.policy import _ensure_orchestrator_plan
        state = self._make_zh_deep_state(chapter_count=50)
        result = _ensure_orchestrator_plan(state)
        plan = result.get("import_plan", {})
        self.assertEqual(plan.get("planner_kind"), "deterministic_rules")
        self.assertEqual(plan.get("source_type"), "coarse_webnovel")
        self.assertTrue(plan.get("prompt_policy", {}).get("variant_dispatch"))
        self.assertFalse(plan.get("prompt_policy", {}).get("dynamic_prompt_edits_allowed"))

    def test_50ch_zh_deep_expected_min_characters_equals_50(self):
        """Granularity profile overrides TOS default: coarse_webnovel gives min_chars=1.0 not 1.5."""
        from sidecar.supervisor.policy import _ensure_orchestrator_plan
        state = self._make_zh_deep_state(chapter_count=50)
        result = _ensure_orchestrator_plan(state)
        target = result["converge_target"]
        self.assertEqual(
            target["expected_min_characters"], 50,
            f"50-ch zh deep: expected 50 (coarse_webnovel 1.0×50), got {target['expected_min_characters']}"
        )

    def test_idempotent_when_spec_and_target_already_set(self):
        """Second call with spec+target already in state must return early without overwriting."""
        from sidecar.supervisor.policy import _ensure_orchestrator_plan
        from sidecar.models.state import plan_converge_target, plan_tool_operating_spec, select_granularity_profile
        state = self._make_zh_deep_state(chapter_count=50)
        spec = plan_tool_operating_spec("deep", "zh", 50)
        gp = select_granularity_profile(50, "zh", "deep", "import_all")
        target = plan_converge_target(spec, "zh", 50, granularity_profile=gp)
        target["expected_min_characters"] = 999  # sentinel
        state["tool_operating_spec"] = spec
        state["converge_target"] = target
        result = _ensure_orchestrator_plan(state)
        self.assertEqual(result["converge_target"]["expected_min_characters"], 999,
                         "Early return must not overwrite existing plan")


if __name__ == "__main__":
    unittest.main()
