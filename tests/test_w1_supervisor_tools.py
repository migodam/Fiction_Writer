"""Tests for W1 Supervisor tool implementations (S1)."""
from __future__ import annotations

import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sidecar.models.state import PROFILE_CONFIGS, ImportSupervisorState, plan_orchestrator_targets
from sidecar.supervisor.tool_registry import build_tool_registry
from sidecar.supervisor.tools import (
    _symptom_flags,
    extract_window,
    cross_validate_window,
    minor_repair,
    judge_import,
    qa_review,
    reduce_entities,
    rerun_window,
    segment_manifest,
    estimate_window_output_tokens,
    window_exceeds_output_budget,
    _OUTPUT_BUDGET_SPLIT_THRESHOLD,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> ImportSupervisorState:
    base: ImportSupervisorState = {
        "project_path": "/tmp/test_project",
        "source_file_path": "/tmp/test_project/novel.txt",
        "import_run_id": "import_test001",
        "prompt_profile": "balanced",
        "import_mode": "import_all",
        "source_language": "en",
        "profile_config": PROFILE_CONFIGS["balanced"],
        "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
        "chunks": [
            {"chunk_id": 0, "content": "Chapter 1 text.", "chapter_hint": "Chapter 1", "char_start": 0, "char_end": 100},
            {"chunk_id": 1, "content": "Chapter 2 text.", "chapter_hint": "Chapter 2", "char_start": 100, "char_end": 200},
        ],
        "prompt_windows": [],
        "window_metrics": {},
        "supervisor_decisions": [],
        "supervisor_log": [],
        "minor_repair_log": [],
        "supervisor_iteration": 0,
        "max_supervisor_iterations": 3,
        "gate_failures": [],
        "rerun_candidates": [],
        "raw_relationships": [],
        "errors": [],
        "import_run_manifest": {"source_hash": "abc123", "import_run_id": "import_test001"},
        "project_structure_digest": {"content": "(empty)", "estimated_tokens": 5, "counts": {}},
    }
    base.update(overrides)
    return base


def _make_window(window_id: str, chunk_ids: list[int], chapters: int = 2) -> dict:
    return {
        "id": window_id,
        "chunk_ids": chunk_ids,
        "chapter_range": f"Ch {chunk_ids[0]+1}–{chunk_ids[-1]+1}",
        "text": "PROJECT_STRUCTURE_DIGEST:\n(empty)\n\nSOURCE_CHAPTERS:\nsome text",
        "estimated_tokens": 500,
        "source_chars": 200,
        "digest_token_estimate": 10,
        "validation_token_estimate": 5,
        "split_reason": "complete_chapter",
        "output_token_budget": 3000,
    }


def _run(coro):
    return asyncio.run(coro)


# ── Test 1: segment_manifest idempotency ──────────────────────────────────────

class TestSegmentManifest(unittest.TestCase):
    def test_idempotency_skips_when_windows_exist(self):
        win = _make_window("pwin_existing", [0])
        state = _make_state(prompt_windows=[win])

        with patch("sidecar.supervisor.tools._build_prompt_windows") as mock_build:
            result = _run(segment_manifest(state))

        # Should not rebuild — cache hit
        mock_build.assert_not_called()
        # Returns a log entry noting the cache hit
        log_text = " ".join(result.get("supervisor_log", []))
        self.assertIn("cache hit", log_text)

    def test_builds_windows_when_none_exist(self):
        state = _make_state()
        built_win = _make_window("pwin_new", [0])

        with patch("sidecar.supervisor.tools._build_prompt_windows", return_value=[built_win]):
            result = _run(segment_manifest(state))

        windows = result.get("prompt_windows", [])
        self.assertGreater(len(windows), 0)


# ── Test 2: extract_window metrics populated ─────────────────────────────────

class TestExtractWindow(unittest.TestCase):
    def test_metrics_populated_on_success(self):
        win = _make_window("pwin_a", [0, 1])
        state = _make_state(prompt_windows=[win])

        char_output = {"new_characters": [{"canonical_name": "Alice", "confidence": 0.9, "importance": "core"}], "existing_character_updates": []}
        event_output = {"events": [{"title": "Battle", "description": "A fight", "confidence": 0.85}]}
        world_output = {"world_mentions": [{"name": "Rivendell", "category": "location"}]}
        rel_output = {"relationships": []}
        scene_output = {"scenes": []}

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock) as mock_invoke,
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            mock_invoke.side_effect = [char_output, event_output, world_output, rel_output, scene_output]
            result = _run(extract_window(state, "pwin_a"))

        metrics = result.get("window_metrics", {}).get("pwin_a", {})
        self.assertEqual(metrics.get("window_id"), "pwin_a")
        self.assertEqual(metrics.get("char_count_extracted"), 1)
        self.assertEqual(metrics.get("event_count_extracted"), 1)
        self.assertEqual(metrics.get("world_count_extracted"), 1)
        self.assertIsInstance(metrics.get("failed_prompts"), list)

    def test_failed_prompts_captured(self):
        win = _make_window("pwin_b", [0])
        state = _make_state(prompt_windows=[win])

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock) as mock_invoke,
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            mock_invoke.side_effect = [Exception("API Error"), {}, {}, {}, {}]
            result = _run(extract_window(state, "pwin_b"))

        metrics = result.get("window_metrics", {}).get("pwin_b", {})
        self.assertGreater(len(metrics.get("failed_prompts", [])), 0)


# ── Test 3: cross_validate non-fatal on failure ───────────────────────────────

class TestCrossValidateWindow(unittest.TestCase):
    def test_non_fatal_on_llm_failure(self):
        state = _make_state()

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
        ):
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
            with patch("sidecar.supervisor.tools._get_llm", return_value=mock_llm):
                result = _run(cross_validate_window(state, "pwin_x"))

        # Should return without raising; may have a log entry
        self.assertIsInstance(result, dict)
        # cross_validation and window_metrics are NOT required in error path
        log = result.get("supervisor_log", [])
        self.assertTrue(any("non-fatal" in entry for entry in log))

    def test_updates_window_metrics_on_success(self):
        win = _make_window("pwin_c", [0])
        state = _make_state(
            prompt_windows=[win],
            window_metrics={"pwin_c": {"window_id": "pwin_c", "chapter_count": 1}},
        )
        cv_result = {
            "duplicate_characters": [{"candidate_ids": ["c1", "c2"], "confidence": 0.8}],
            "duplicate_events": [],
            "missing_major_characters": [{"name_or_alias": "Bob", "confidence": 0.7}],
            "suspicious_groups": [], "contradictory_aliases": [],
            "event_merge_recommendations": [], "warnings": [],
        }

        with patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()):
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"duplicate_characters":[{"candidate_ids":["c1","c2"],"confidence":0.8}],"duplicate_events":[],"missing_major_characters":[{"name_or_alias":"Bob","confidence":0.7}],"suspicious_groups":[],"contradictory_aliases":[],"event_merge_recommendations":[],"warnings":[]}'))
            with patch("sidecar.supervisor.tools._get_llm", return_value=mock_llm):
                result = _run(cross_validate_window(state, "pwin_c"))

        wm = result.get("window_metrics", {}).get("pwin_c", {})
        self.assertEqual(wm.get("missing_majors_count"), 1)
        self.assertEqual(wm.get("duplicate_count"), 1)


# ── Test 4: rerun_window split creates two sub-windows ───────────────────────

class TestRerunWindowSplit(unittest.TestCase):
    def test_split_creates_two_sub_windows_with_new_ids(self):
        parent = _make_window("pwin_parent", [0, 1, 2, 3])
        state = _make_state(
            prompt_windows=[parent],
            chunks=[
                {"chunk_id": 0, "content": "Ch1", "chapter_hint": "Chapter 1", "char_start": 0, "char_end": 50},
                {"chunk_id": 1, "content": "Ch2", "chapter_hint": "Chapter 2", "char_start": 50, "char_end": 100},
                {"chunk_id": 2, "content": "Ch3", "chapter_hint": "Chapter 3", "char_start": 100, "char_end": 150},
                {"chunk_id": 3, "content": "Ch4", "chapter_hint": "Chapter 4", "char_start": 150, "char_end": 200},
            ],
        )

        sub_win_a = _make_window("pwin_sub_a", [0, 1])
        sub_win_b = _make_window("pwin_sub_b", [2, 3])

        with (
            patch("sidecar.supervisor.tools._build_prompt_windows") as mock_build,
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock, return_value={}),
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            mock_build.side_effect = [[sub_win_a], [sub_win_b]]
            result = _run(rerun_window(state, "pwin_parent", strategy="split"))

        new_windows = result.get("prompt_windows", [])
        new_ids = [w["id"] for w in new_windows if w["id"] != "pwin_parent"]
        self.assertEqual(len(new_ids), 2, f"Expected 2 sub-windows, got {new_ids}")
        # Both IDs must differ from the parent
        for nid in new_ids:
            self.assertNotEqual(nid, "pwin_parent")
        # Both must differ from each other
        self.assertNotEqual(new_ids[0], new_ids[1])


# ── Test 5: rerun_window augment injects missing chars ───────────────────────

class TestRerunWindowAugment(unittest.TestCase):
    def test_augment_injects_supervisor_hint(self):
        parent = _make_window("pwin_parent2", [0])
        state = _make_state(prompt_windows=[parent])

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock, return_value={}),
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            result = _run(rerun_window(state, "pwin_parent2", strategy="augment", missing_char_names=["Alice", "Bob"]))

        new_windows = result.get("prompt_windows", [])
        augmented = [w for w in new_windows if w["id"] != "pwin_parent2"]
        self.assertEqual(len(augmented), 1)
        self.assertIn("SUPERVISOR_HINT", augmented[0].get("text", ""))
        self.assertIn("Alice", augmented[0].get("text", ""))


# ── Test 6: max rerun cap respected ──────────────────────────────────────────

class TestRerunWindowMaxCap(unittest.TestCase):
    def test_max_rerun_cap_returns_skip_action(self):
        parent = _make_window("pwin_capped", [0])
        profile_config = {**PROFILE_CONFIGS["balanced"], "max_rerun_iterations": 1}
        state = _make_state(
            prompt_windows=[parent],
            profile_config=profile_config,
            window_metrics={"pwin_capped": {"rerun_count": 1}},  # already at max
        )

        with patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock, return_value={}):
            result = _run(rerun_window(state, "pwin_capped", strategy="augment"))

        decisions = result.get("supervisor_decisions", [])
        self.assertTrue(any(d.get("action") == "skip" for d in decisions))
        # No new windows should have been added
        new_windows = result.get("prompt_windows", [])
        self.assertEqual(len(new_windows), 0)


# ── Test 7: reduce_entities reports missing_groupkey_count ───────────────────

class TestReduceEntities(unittest.TestCase):
    def test_reports_missing_groupkey_count(self):
        registry = {
            "characters": {
                "char_001": {"canonical_name": "Alice", "importance": "core", "confidence": 0.9},
                "char_002": {"canonical_name": "Bob", "importance": "major", "confidence": 0.8, "groupKey": "Supporting Cast"},
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry)

        async def _mock_reconcile(s): return {"entity_registry": registry, "reducer_artifact": {}}
        async def _mock_low_conf(s): return {"entity_registry": registry}

        with (
            patch("sidecar.supervisor.tools.node_reconcile_entities", new_callable=lambda: lambda: _mock_reconcile),
            patch("sidecar.supervisor.tools.node_resolve_low_confidence", new_callable=lambda: lambda: _mock_low_conf),
        ):
            # Use actual node functions since the test registry doesn't need reconciliation
            async def _fake_reconcile(s):
                return {"entity_registry": s.get("entity_registry", {}), "reducer_artifact": {}}

            async def _fake_low_conf(s):
                return {"entity_registry": s.get("entity_registry", {})}

            with (
                patch("sidecar.supervisor.tools.node_reconcile_entities", _fake_reconcile),
                patch("sidecar.supervisor.tools.node_resolve_low_confidence", _fake_low_conf),
            ):
                result = _run(reduce_entities(state))

        log = " ".join(result.get("supervisor_log", []))
        # char_001 is missing groupKey (char_002 has it)
        self.assertIn("1 missing groupKey", log)


# ── Test 8: minor_repair sets groupKey for all chars ─────────────────────────

class TestMinorRepairGroupKey(unittest.TestCase):
    def test_sets_groupkey_for_all_missing(self):
        registry = {
            "characters": {
                "c1": {"canonical_name": "Alice", "importance": "core", "personality_traits": []},
                "c2": {"canonical_name": "Bob", "importance": "minor", "personality_traits": []},
                "c3": {"canonical_name": "Carol", "importance": "major", "groupKey": "Already Set", "personality_traits": []},
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry)
        result = _run(minor_repair(state))

        chars = result.get("entity_registry", {}).get("characters", {})
        self.assertEqual(chars["c1"].get("groupKey"), "Main Characters")
        self.assertEqual(chars["c2"].get("groupKey"), "Minor Characters")
        self.assertEqual(chars["c3"].get("groupKey"), "Already Set")  # unchanged


# ── Test 9: minor_repair migrates orgs to world_detailed ─────────────────────

class TestMinorRepairOrgMigration(unittest.TestCase):
    def test_migrates_org_chars_to_world_detailed(self):
        registry = {
            "characters": {
                "c_org": {
                    "canonical_name": "Merchant Guild",
                    "importance": "supporting",
                    "role_in_story": "A major organization in the story",
                    "summary": "The guild controls trade routes",
                    "personality_traits": [],
                },
                "c_person": {
                    "canonical_name": "Alice",
                    "importance": "core",
                    "role_in_story": "protagonist",
                    "personality_traits": [],
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry)
        result = _run(minor_repair(state))

        chars = result.get("entity_registry", {}).get("characters", {})
        world_detailed = result.get("entity_registry", {}).get("world_detailed", {})

        self.assertTrue(chars["c_org"].get("skip_create"), "org-char should be marked skip_create")
        self.assertIn("Merchant Guild", world_detailed)
        self.assertFalse(chars["c_person"].get("skip_create"))


# ── Test 10: minor_repair strips Latin traits for zh source ──────────────────

class TestMinorRepairLatinStrip(unittest.TestCase):
    def test_strips_latin_dominant_traits_for_zh_source(self):
        registry = {
            "characters": {
                "c_zh": {
                    "canonical_name": "韩立",
                    "importance": "core",
                    "personality_traits": ["勤奋", "determined warrior", "聪明"],
                    "role_in_story": "protagonist",
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry, source_language="zh")
        result = _run(minor_repair(state))

        traits = result.get("entity_registry", {}).get("characters", {}).get("c_zh", {}).get("personality_traits", [])
        trait_text = " ".join(traits)
        self.assertIn("勤奋", trait_text)
        self.assertIn("聪明", trait_text)
        self.assertNotIn("determined warrior", trait_text)

    def test_does_not_strip_for_en_source(self):
        registry = {
            "characters": {
                "c_en": {
                    "canonical_name": "John",
                    "importance": "core",
                    "personality_traits": ["determined warrior", "brave"],
                    "role_in_story": "protagonist",
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry, source_language="en")
        result = _run(minor_repair(state))

        traits = result.get("entity_registry", {}).get("characters", {}).get("c_en", {}).get("personality_traits", [])
        self.assertIn("determined warrior", traits)


# ── Test 11: qa_review gate_failures from symptom flags ──────────────────────

class TestQaReview(unittest.TestCase):
    def test_gate_failures_populated_from_symptom_flags(self):
        registry = {
            "characters": {
                "c1": {"canonical_name": "Alice", "importance": "core"},  # missing groupKey
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry)

        async def _mock_review(s):
            return {"import_review_report": {"status": "warning", "warnings": [], "errors": [], "proposal_counts": {}}}

        with patch("sidecar.supervisor.tools.node_review_import", _mock_review):
            result = _run(qa_review(state))

        gate_failures = result.get("gate_failures", [])
        gates = [gf["gate"] for gf in gate_failures]
        self.assertIn("groupKey_coverage", gates)

    def test_mixed_language_flag_triggers_gate(self):
        registry = {
            "characters": {
                "c1": {
                    "canonical_name": "韩立",
                    "importance": "core",
                    "groupKey": "Main Characters",
                    "personality_traits": ["determined fighter", "勤奋"],
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry, source_language="zh")

        async def _mock_review(s):
            return {"import_review_report": {"status": "pass", "warnings": [], "errors": [], "proposal_counts": {}}}

        with patch("sidecar.supervisor.tools.node_review_import", _mock_review):
            result = _run(qa_review(state))

        gate_failures = result.get("gate_failures", [])
        gates = [gf["gate"] for gf in gate_failures]
        self.assertIn("language_consistency", gates)


class TestToolOperatingSpecPlanner(unittest.TestCase):
    def test_deep_defaults_enable_orchestrator_and_supervisor(self):
        spec, target = plan_orchestrator_targets("deep", "zh", 20)

        self.assertTrue(spec["orchestrator_enabled"])
        self.assertTrue(spec["supervisor_enabled"])
        self.assertEqual(spec["timeline_topology_target"], "full_dag")
        self.assertEqual(spec["language_policy"], "normalize_to_source")
        self.assertGreaterEqual(target["expected_min_characters"], 30)

    def test_custom_overrides_are_applied(self):
        spec, target = plan_orchestrator_targets(
            "custom",
            "en",
            10,
            overrides={"rerun_budget": 1, "judge_pass_threshold": 0.9},
        )

        self.assertTrue(spec["orchestrator_enabled"])
        self.assertEqual(spec["rerun_budget"], 1)
        self.assertEqual(spec["judge_pass_threshold"], 0.9)
        self.assertEqual(target["expected_language"], "en")

    def test_custom_ui_profile_terms_are_normalized_into_tos(self):
        spec, target = plan_orchestrator_targets(
            "custom",
            "zh",
            10,
            overrides={
                "max_chapters_per_window": 4,
                "event_density": "scene_level",
                "world_strictness": "full_attributes",
                "timeline_topology_depth": "full_dag",
            },
        )

        self.assertEqual(spec["chapters_per_window_max"], 4)
        self.assertEqual(spec["event_density_target"], 1.75)
        self.assertEqual(spec["world_category_policy"], "full_attributes")
        self.assertEqual(spec["timeline_topology_target"], "full_dag")
        self.assertGreaterEqual(target["expected_min_events"], 18)


class TestJudgeImport(unittest.TestCase):
    def test_flags_character_timeline_world_and_language_gates(self):
        registry = {
            "characters": {
                "c_org": {
                    "canonical_name": "Merchant Guild",
                    "importance": "organization",
                    "role_in_story": "organization",
                    "groupKey": "Supporting Cast",
                    "personality_traits": ["determined merchant"],
                },
            },
            "events": {},
            "world": {},
            "world_detailed": {},
        }
        state = _make_state(
            prompt_profile="deep",
            source_language="zh",
            entity_registry=registry,
            chunks=[
                {"chunk_id": i, "content": f"Chapter {i}", "chapter_hint": f"Chapter {i+1}", "char_start": i*100, "char_end": (i+1)*100}
                for i in range(4)
            ],
            prompt_windows=[_make_window("pwin_a", [0, 1]), _make_window("pwin_b", [2, 3])],
            window_metrics={
                "pwin_a": {"window_id": "pwin_a", "chapter_count": 2, "char_count_extracted": 0, "event_count_extracted": 0},
                "pwin_b": {"window_id": "pwin_b", "chapter_count": 2, "char_count_extracted": 0, "event_count_extracted": 0},
            },
            tool_operating_spec=plan_orchestrator_targets("deep", "zh", 4)[0],
            converge_target=plan_orchestrator_targets("deep", "zh", 4)[1],
        )

        with patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/artifact.json"):
            result = _run(judge_import(state))

        artifact = result.get("judge_artifact", {})
        gates = set(artifact.get("failed_gates", []))
        self.assertIn("character_undercoverage", gates)
        self.assertIn("timeline_undercoverage", gates)
        self.assertIn("world_boundary", gates)
        self.assertIn("language_mismatch", gates)
        self.assertFalse(artifact.get("passed"))
        request_themes = {r["theme"] for r in artifact.get("thematic_rerun_requests", [])}
        self.assertTrue(gates.issubset(request_themes))


# ── Test 12: output_budget gate on estimated > 3500 ──────────────────────────

class TestOutputBudgetGate(unittest.TestCase):
    def test_estimate_scales_with_chapter_count(self):
        win_8ch = _make_window("pwin_8ch", list(range(8)))
        win_2ch = _make_window("pwin_2ch", [0, 1])

        est_8 = estimate_window_output_tokens(win_8ch, chapters_per_window=8)
        est_2 = estimate_window_output_tokens(win_2ch, chapters_per_window=8)

        self.assertGreater(est_8, est_2)

    def test_window_exceeds_budget_for_large_chapter_count(self):
        win_12ch = _make_window("pwin_12ch", list(range(12)))
        profile_config = PROFILE_CONFIGS["deep"]

        result = window_exceeds_output_budget(win_12ch, profile_config)
        self.assertTrue(result, "12-chapter window should exceed 3500-token output budget")

    def test_window_within_budget_for_small_chapter_count(self):
        win_2ch = _make_window("pwin_2ch", [0, 1])
        profile_config = PROFILE_CONFIGS["deep"]

        result = window_exceeds_output_budget(win_2ch, profile_config)
        self.assertFalse(result, "2-chapter window should be within output budget")

    def test_segment_manifest_splits_oversized_windows(self):
        # A window with many chunks should trigger pre-flight split
        large_chunks = [
            {"chunk_id": i, "content": f"Chapter {i}", "chapter_hint": f"Chapter {i+1}", "char_start": i*100, "char_end": (i+1)*100}
            for i in range(12)
        ]
        state = _make_state(chunks=large_chunks)

        large_win = _make_window("pwin_large", list(range(12)))

        with patch("sidecar.supervisor.tools._build_prompt_windows", return_value=[large_win]):
            result = _run(segment_manifest(state))

        windows = result.get("prompt_windows", [])
        # Large window should have been split into smaller ones
        self.assertGreater(len(windows), 1, "Pre-flight split should produce multiple windows")


# ── Tool registry ─────────────────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):
    def test_build_tool_registry_returns_all_ten_tools(self):
        registry = build_tool_registry()
        expected = {
            "segment_manifest", "extract_window", "cross_validate_window",
            "rerun_window", "reduce_entities", "architect_timeline",
            "qa_review", "judge_import", "minor_repair", "proposal_write",
        }
        self.assertEqual(set(registry.keys()), expected)
        for name, fn in registry.items():
            self.assertTrue(callable(fn), f"{name} must be callable")


# ── TOS world entity cap ──────────────────────────────────────────────────────

class TestTOSWorldCap(unittest.TestCase):
    def test_deep_tos_has_world_entities_per_chapter(self):
        from sidecar.models.state import plan_tool_operating_spec
        spec = plan_tool_operating_spec("deep", "zh", 50)
        self.assertEqual(spec["max_world_entities_per_chapter"], 5)

    def test_fast_tos_has_world_entities_per_chapter(self):
        from sidecar.models.state import plan_tool_operating_spec
        spec = plan_tool_operating_spec("fast", "en", 10)
        self.assertEqual(spec["max_world_entities_per_chapter"], 3)


class TestWorldDedupeKeyInPrompt(unittest.TestCase):
    def test_world_deep_prompt_contains_dedupeKey_field(self):
        from sidecar.prompts.w1_prompts import W1_EXTRACT_WORLD_DEEP
        self.assertIn("dedupeKey", W1_EXTRACT_WORLD_DEEP)


# ── proposal_write early artifact write ────────────────────────────────────────

class TestProposalWriteEarlyArtifacts(unittest.TestCase):
    """Diagnostics artifacts must be written BEFORE node_write_to_project runs.

    If node_write_to_project OOMs or raises, supervisor_decisions.json and
    window_metrics.json must already be on disk.
    """

    def test_diagnostics_written_before_oom_crash(self):
        import json, tempfile
        from pathlib import Path
        from sidecar.supervisor.tools import proposal_write

        with tempfile.TemporaryDirectory() as td:
            project_path = td
            import_run_id = "test_oom_run"
            artifact_dir = Path(project_path) / "system" / "imports" / import_run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)

            state = _make_state(
                project_path=project_path,
                import_run_id=import_run_id,
                supervisor_decisions=[{"decision": "test"}],
                window_metrics={"pwin_a": {"char_count_extracted": 5}},
                judge_artifact={"score": 0.9, "passed": True, "failed_gates": []},
                cross_validation={"duplicate_characters": [], "missing_major_characters": []},
                entity_registry={"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
                manuscript_chapters=[],
                timeline_branches=[],
                relationships=[],
                character_tags=[],
                world_settings={},
            )

            async def _boom(*a, **kw):
                raise MemoryError("simulated OOM")

            # Patch node_write_to_project to raise after artifacts should be written
            with (
                patch("sidecar.supervisor.tools.node_build_manuscript", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_synthesize_relationships", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_classify_character_tags", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_infer_world_settings", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_write_to_project", new=AsyncMock(side_effect=MemoryError("simulated OOM"))),
            ):
                try:
                    _run(proposal_write(state))
                except MemoryError:
                    pass  # expected — crash during proposal write

            # Diagnostics must be on disk despite the crash
            decisions_path = artifact_dir / "supervisor_decisions.json"
            metrics_path = artifact_dir / "window_metrics.json"
            judge_path = artifact_dir / "judge_artifact.json"
            cv_path = artifact_dir / "cross_validation.json"

            self.assertTrue(decisions_path.exists(), "supervisor_decisions.json must be written before OOM")
            self.assertTrue(metrics_path.exists(), "window_metrics.json must be written before OOM")
            self.assertTrue(judge_path.exists(), "judge_artifact.json must be written before OOM")
            self.assertTrue(cv_path.exists(), "cross_validation.json must be written before OOM")

            decisions = json.loads(decisions_path.read_text())
            self.assertEqual(decisions, [{"decision": "test"}])


# ── proposal_write returns compact state (no entity_registry) ─────────────────

class TestProposalWriteCompactReturn(unittest.TestCase):
    """proposal_write must not include entity_registry in its return dict."""

    def test_entity_registry_not_in_return_dict(self):
        import tempfile
        from sidecar.supervisor.tools import proposal_write

        with tempfile.TemporaryDirectory() as td:
            state = _make_state(
                project_path=td,
                import_run_id="test_compact",
                entity_registry={
                    "characters": {"char_x": {"canonical_name": "X", "confidence": 0.8, "importance": "minor"}},
                    "events": {},
                    "world": {},
                    "world_detailed": {},
                },
                manuscript_chapters=[],
                timeline_branches=[],
                relationships=[],
                character_tags=[],
                world_settings={},
            )

            with (
                patch("sidecar.supervisor.tools.node_build_manuscript", new=AsyncMock(return_value={"manuscript_chapters": []})),
                patch("sidecar.supervisor.tools.node_synthesize_relationships", new=AsyncMock(return_value={"relationships": []})),
                patch("sidecar.supervisor.tools.node_classify_character_tags", new=AsyncMock(return_value={"character_tags": []})),
                patch("sidecar.supervisor.tools.node_infer_world_settings", new=AsyncMock(return_value={"world_settings": {}})),
                patch("sidecar.supervisor.tools.node_write_to_project", new=AsyncMock(return_value={
                    "proposals": [{"id": "p1", "entity_type": "character", "status": "", "confidence": 0.75, "blocked": False}],
                    "errors": [],
                    "status": "done",
                    "progress": 1.0,
                })),
            ):
                result = _run(proposal_write(state))

            # entity_registry must be evicted from the return dict
            self.assertNotIn("entity_registry", result)
            # proposals list must be present (compact receipts)
            self.assertIn("proposals", result)


# ── extract_window world entity cap ──────────────────────────────────────────

class TestWorldEntityCapInExtractWindow(unittest.TestCase):
    """world_mentions must be capped to 20 per chapter before registry merge."""

    def test_world_mentions_capped_by_chapter_count(self):
        win = _make_window("pwin_worldcap", [0, 1])  # 2 chunk_ids → 2 chapters → cap = 40
        state = _make_state(prompt_windows=[win], tool_operating_spec={"max_world_entities_per_chapter": 20})

        # Build 60 world mentions (exceeds cap of 2 × 20 = 40)
        world_mentions = [
            {"name": f"World_{i}", "category": "location", "confidence": 0.5 + (i / 200)}
            for i in range(60)
        ]
        # Highest confidence items are indices 40-59 (confidence 0.7+)
        world_output = {"world_mentions": world_mentions}

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock) as mock_invoke,
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            mock_invoke.side_effect = [
                {"new_characters": [], "existing_character_updates": []},
                {"events": []},
                world_output,
                {"relationships": []},
                {"scenes": []},
            ]
            result = _run(extract_window(state, "pwin_worldcap"))

        world_registry = result.get("entity_registry", {}).get("world", {})
        # Cap is 2 chapters × 20 = 40; 60 mentions provided, so registry must have ≤ 40
        self.assertLessEqual(len(world_registry), 40, f"Got {len(world_registry)} world entries, expected ≤ 40")

    def test_world_mentions_below_cap_not_truncated(self):
        win = _make_window("pwin_worldsmall", [0])  # 1 chunk → 1 chapter → cap = 20
        state = _make_state(prompt_windows=[win], tool_operating_spec={"max_world_entities_per_chapter": 20})

        world_mentions = [
            {"name": f"Place_{i}", "category": "location", "confidence": 0.8}
            for i in range(10)  # 10 < cap of 20
        ]
        world_output = {"world_mentions": world_mentions}

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", new_callable=AsyncMock) as mock_invoke,
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            mock_invoke.side_effect = [
                {"new_characters": [], "existing_character_updates": []},
                {"events": []},
                world_output,
                {"relationships": []},
                {"scenes": []},
            ]
            result = _run(extract_window(state, "pwin_worldsmall"))

        world_registry = result.get("entity_registry", {}).get("world", {})
        self.assertEqual(len(world_registry), 10, "10 mentions should all be registered when below cap")


# ── Test: per-window world entity cap (TDD task 3) ───────────────────────────

class TestExtractWindowWorldCap(unittest.TestCase):
    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_world_cap_limits_per_window_registration(self, mock_invoke, mock_llm):
        """World entities exceeding max_world_entities_per_chapter * chunk_count are dropped."""
        mock_llm.return_value = MagicMock()
        # 2 chunks, max 5/chapter → cap = 10. Return 15 world mentions.
        world_mentions = [
            {"name": f"Place{i}", "category": "location", "dedupeKey": f"place{i}::location",
             "description": "a place", "confidence": 0.9 - i * 0.01}
            for i in range(15)
        ]
        mock_invoke.side_effect = [
            {"new_characters": []},
            {"events": []},
            {"world_mentions": world_mentions},
            {"relationships": []},
            {"scene_summaries": []},
        ]
        state = _make_state(
            tool_operating_spec={"max_world_entities_per_chapter": 5},
            prompt_windows=[_make_window("win1", [0, 1])],
        )
        result = asyncio.run(extract_window(state, "win1"))
        registered = len(result.get("entity_registry", {}).get("world", {}))
        self.assertLessEqual(registered, 10, f"Expected ≤10 world entities for 2-chunk window with cap 5/ch, got {registered}")


if __name__ == "__main__":
    unittest.main()
