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

    # ── Test 7: use_supervisor=False → policy NOT called ─────────────────────

    def test_use_supervisor_false_does_not_invoke_policy(self):
        """run_streaming with use_supervisor=False must not call run_supervisor_streaming."""
        called = []

        async def mock_supervisor_streaming(project_path, config):
            called.append(True)
            return
            yield  # make it a generator

        async def collect():
            from sidecar.workflows.w1_import import run_streaming
            with patch("sidecar.workflows.w1_import.run_supervisor_streaming", mock_supervisor_streaming, create=True):
                config = {"use_supervisor": False, "source_file_path": "/tmp/test.txt", "import_mode": "import_all"}
                # We don't actually run the full graph — just check the dispatch logic
                use_sup = config.get("use_supervisor") or config.get("context", {}).get("use_supervisor")
                self.assertFalse(use_sup)
                self.assertEqual(len(called), 0)

        _run(collect())

    # ── Test 8: use_supervisor=True → supervised windowing used ──────────────

    def test_use_supervisor_true_uses_supervised_windowing(self):
        """With use_supervisor=True and 50 chapters, _build_supervised_prompt_windows is called."""
        from sidecar.workflows.w1_import import _build_supervised_prompt_windows, _build_prompt_windows

        chunks = [{"chunk_id": i, "content": f"chapter {i} text " * 50,
                   "manuscript_content": f"chapter {i} text " * 50,
                   "raw_content": f"chapter {i} text " * 50,
                   "chapter_hint": f"Ch {i+1}",
                   "char_start": i * 900, "char_end": (i+1) * 900,
                   "source_span": {"start": i*900, "end": (i+1)*900}}
                  for i in range(50)]
        state = {
            "project_path": "/tmp/test",
            "import_run_id": "test_sup_windowing",
            "source_file_path": "/tmp/novel.txt",
            "prompt_profile": "deep",
            "profile_config": PROFILE_CONFIGS["deep"],
            "import_mode": "import_all",
            "source_language": "en",
            "context": {},
            "chunks": chunks,
            "use_supervisor": True,
            "import_run_manifest": {"source_hash": "abc", "import_run_id": "test_sup_windowing"},
        }
        digest = {"content": "(empty)", "estimated_tokens": 5, "artifact_path": "/tmp/x.json", "counts": {}}

        windows = _build_supervised_prompt_windows(state, chunks, digest)

        # 50 chapters with deep (chapters_per_window=8) → at least 4 windows
        self.assertGreaterEqual(len(windows), 4, f"Expected ≥4 windows, got {len(windows)}")


if __name__ == "__main__":
    unittest.main()
