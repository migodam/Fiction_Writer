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

        with patch("sidecar.supervisor.tools._build_supervised_prompt_windows", return_value=[built_win]):
            result = _run(segment_manifest(state))

        windows = result.get("prompt_windows", [])
        self.assertGreater(len(windows), 0)

    def test_uses_supervised_multi_chapter_window_builder(self):
        state = _make_state(chunks=[
            {"chunk_id": i, "content": f"Chapter {i + 1}", "chapter_hint": f"Chapter {i + 1}"}
            for i in range(6)
        ])
        built_win = _make_window("pwin_packed", [0, 1, 2, 3, 4, 5])

        with (
            patch("sidecar.supervisor.tools._build_supervised_prompt_windows", return_value=[built_win]) as mock_supervised,
            patch("sidecar.supervisor.tools._build_prompt_windows") as mock_legacy,
        ):
            result = _run(segment_manifest(state))

        mock_supervised.assert_called_once()
        mock_legacy.assert_not_called()
        self.assertEqual(result.get("prompt_windows", [])[0]["chunk_ids"], [0, 1, 2, 3, 4, 5])


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


# ── Test 13: extract_window passes source_language_label to all prompts ───────

class TestExtractWindowLanguageInjection(unittest.TestCase):
    def test_extract_window_passes_source_language_label_to_prompts(self):
        win = _make_window("pwin_zh", [0])
        state = _make_state(
            prompt_windows=[win],
            source_language="zh",
        )
        captured_kwargs: list[dict] = []

        async def _mock_invoke(_llm, _template, **kwargs):
            captured_kwargs.append(dict(kwargs))
            return {}

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", side_effect=_mock_invoke),
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            _run(extract_window(state, "pwin_zh"))

        self.assertEqual(len(captured_kwargs), 5, "Expected 5 prompt calls")
        for call_kwargs in captured_kwargs:
            self.assertEqual(
                call_kwargs.get("source_language_label"), "Chinese (Simplified)",
                f"source_language_label missing or wrong in call: {call_kwargs}",
            )
            self.assertIn("language_policy", call_kwargs, f"language_policy missing in call: {call_kwargs}")

    def test_extract_window_uses_english_label_for_en_source(self):
        win = _make_window("pwin_en", [0])
        state = _make_state(prompt_windows=[win], source_language="en")
        captured_kwargs: list[dict] = []

        async def _mock_invoke(_llm, _template, **kwargs):
            captured_kwargs.append(dict(kwargs))
            return {}

        with (
            patch("sidecar.supervisor.tools._get_llm", return_value=MagicMock()),
            patch("sidecar.supervisor.tools._invoke_json_prompt", side_effect=_mock_invoke),
            patch("sidecar.supervisor.tools._write_import_artifact", return_value="/tmp/mock.json"),
        ):
            _run(extract_window(state, "pwin_en"))

        for call_kwargs in captured_kwargs:
            self.assertEqual(call_kwargs.get("source_language_label"), "English")


# ── Test 14: minor_repair strips short Latin traits (4–6 chars) ──────────────

class TestMinorRepairShortLatinStrip(unittest.TestCase):
    def test_strips_short_latin_traits_for_zh(self):
        registry = {
            "characters": {
                "c_zh": {
                    "canonical_name": "韩立",
                    "importance": "core",
                    "personality_traits": ["brave", "勤奋", "calm", "kind"],
                    "role_in_story": "protagonist",
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry, source_language="zh")
        result = _run(minor_repair(state))

        traits = result["entity_registry"]["characters"]["c_zh"]["personality_traits"]
        self.assertIn("勤奋", traits)
        self.assertNotIn("brave", traits)
        self.assertNotIn("calm", traits)
        self.assertNotIn("kind", traits)

    def test_language_gate_passes_after_minor_repair_cleans_all_traits(self):
        registry = {
            "characters": {
                "c_zh": {
                    "canonical_name": "韩立",
                    "importance": "core",
                    "groupKey": "Main Characters",
                    "personality_traits": ["brave", "calm", "determined"],
                    "role_in_story": "protagonist",
                },
            },
            "events": {}, "world": {}, "world_detailed": {},
        }
        state = _make_state(entity_registry=registry, source_language="zh")
        repaired = _run(minor_repair(state))
        repaired_state = {**state, **repaired}
        flags = _symptom_flags(repaired_state)

        self.assertFalse(
            flags["mixed_language_trait_sets"],
            "language gate should pass after minor_repair strips all Latin traits",
        )


# ── Tool registry ─────────────────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):
    def test_build_tool_registry_returns_all_ten_tools(self):
        registry = build_tool_registry()
        expected = {
            "segment_manifest", "extract_window", "cross_validate_window",
            "rerun_window", "reduce_entities", "reduce_world_entities",
            "architect_timeline", "qa_review", "judge_import", "minor_repair",
            "proposal_write",
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
                import_granularity_profile={
                    "profile_name": "fine_short_story",
                    "character_granularity": "all",
                    "event_density": "scene_level",
                    "world_density": "full_lore",
                    "relationship_depth": "dense",
                },
                import_plan={
                    "plan_version": "w1-import-plan-v1",
                    "planner_kind": "deterministic_rules",
                    "source_type": "fine_short_story",
                },
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
            gran_path = artifact_dir / "import_granularity_profile.json"
            plan_path = artifact_dir / "import_plan.json"
            prompts_path = artifact_dir / "extraction_prompt_variants.json"

            self.assertTrue(decisions_path.exists(), "supervisor_decisions.json must be written before OOM")
            self.assertTrue(metrics_path.exists(), "window_metrics.json must be written before OOM")
            self.assertTrue(judge_path.exists(), "judge_artifact.json must be written before OOM")
            self.assertTrue(cv_path.exists(), "cross_validation.json must be written before OOM")
            self.assertTrue(gran_path.exists(), "import_granularity_profile.json must be written before OOM")
            self.assertTrue(plan_path.exists(), "import_plan.json must be written before OOM")
            self.assertTrue(prompts_path.exists(), "extraction_prompt_variants.json must be written before OOM")

            decisions = json.loads(decisions_path.read_text())
            self.assertEqual(decisions, [{"decision": "test"}])
            prompt_manifest = json.loads(prompts_path.read_text())
            self.assertEqual(
                prompt_manifest["character"]["prompt_constant"],
                "W1_EXTRACT_CHARACTERS_DEEP_FINE",
            )


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

class TestReduceWorldEntities(unittest.TestCase):
    def test_reduces_duplicate_names_to_single_canonical(self):
        """Two differently-spelled entries for the same entity collapse to one."""
        from sidecar.supervisor.tools import reduce_world_entities
        state = _make_state(entity_registry={
            "characters": {}, "events": {},
            "world": {"七玄门": "organization", "七玄門": "organization"},
            "world_detailed": {
                "七玄门": {"name": "七玄门", "category": "organization", "description": "A sect",
                          "dedupeKey": "七玄门::organization", "attributes": [], "confidence": 0.9,
                          "container_hint": "organizations"},
                "七玄門": {"name": "七玄門", "category": "organization", "description": "Same sect",
                          "dedupeKey": "七玄门::organization", "attributes": [], "confidence": 0.8,
                          "container_hint": "organizations"},
            },
        })
        result = reduce_world_entities(state)
        world = result["entity_registry"]["world"]
        self.assertEqual(len(world), 1, f"Expected 1 world entry after dedup, got {len(world)}: {list(world)}")

    def test_canonical_entry_is_highest_confidence(self):
        from sidecar.supervisor.tools import reduce_world_entities
        state = _make_state(entity_registry={
            "characters": {}, "events": {},
            "world": {"七玄门": "organization", "七玄門": "organization"},
            "world_detailed": {
                "七玄门": {"name": "七玄门", "category": "organization", "description": "High conf",
                          "dedupeKey": "七玄门::organization", "attributes": [], "confidence": 0.95,
                          "container_hint": "organizations"},
                "七玄門": {"name": "七玄門", "category": "organization", "description": "Low conf",
                          "dedupeKey": "七玄门::organization", "attributes": [], "confidence": 0.6,
                          "container_hint": "organizations"},
            },
        })
        result = reduce_world_entities(state)
        world = result["entity_registry"]["world"]
        canonical_name = list(world.keys())[0]
        self.assertEqual(canonical_name, "七玄门", f"Expected high-confidence entry as canonical, got {canonical_name!r}")

    def test_keeps_organization_category_for_sect_name(self):
        from sidecar.supervisor.tools import reduce_world_entities
        state = _make_state(entity_registry={
            "characters": {}, "events": {},
            "world": {"七玄门": "organization"},
            "world_detailed": {
                "七玄门": {"name": "七玄门", "category": "organization", "description": "A sect",
                          "dedupeKey": "七玄门::organization", "attributes": [], "confidence": 0.9,
                          "container_hint": "organizations"},
            },
        })
        result = reduce_world_entities(state)
        world = result["entity_registry"]["world"]
        self.assertEqual(world.get("七玄门"), "organization", f"Expected category 'organization', got {world.get('七玄门')!r}")

    def test_merges_attributes_from_duplicates(self):
        from sidecar.supervisor.tools import reduce_world_entities
        state = _make_state(entity_registry={
            "characters": {}, "events": {},
            "world": {"SectA": "organization", "Sect A": "organization"},
            "world_detailed": {
                "SectA": {"name": "SectA", "category": "organization", "description": "Main",
                          "dedupeKey": "secta::organization",
                          "attributes": [{"key": "founded", "value": "dynasty"}],
                          "confidence": 0.9, "container_hint": "organizations"},
                "Sect A": {"name": "Sect A", "category": "organization", "description": "Alt",
                           "dedupeKey": "secta::organization",
                           "attributes": [{"key": "leader", "value": "Elder Mo"}],
                           "confidence": 0.7, "container_hint": "organizations"},
            },
        })
        result = reduce_world_entities(state)
        canonical = list(result["entity_registry"]["world_detailed"].values())[0]
        attr_keys = {a["key"] for a in canonical.get("attributes", [])}
        self.assertIn("founded", attr_keys)
        self.assertIn("leader", attr_keys, "Attributes from lower-confidence dup should be merged in")

    def test_computed_fallback_deduplicates_spacing_variants(self):
        """Entries with no model-provided dedupeKey are deduplicated by computed normalized key."""
        from sidecar.supervisor.tools import reduce_world_entities
        # Neither entry has a dedupeKey — fallback normalizes "Zhao Yun" and "Zhao-Yun" to same key
        state = _make_state(entity_registry={
            "characters": {}, "events": {},
            "world": {"Zhao Yun": "location", "Zhao-Yun": "location"},
            "world_detailed": {
                "Zhao Yun": {"name": "Zhao Yun", "category": "location", "description": "A place",
                             "attributes": [], "confidence": 0.85, "container_hint": "locations"},
                "Zhao-Yun": {"name": "Zhao-Yun", "category": "location", "description": "Same place",
                             "attributes": [], "confidence": 0.75, "container_hint": "locations"},
            },
        })
        result = reduce_world_entities(state)
        world = result["entity_registry"]["world"]
        self.assertEqual(len(world), 1, f"Expected 1 entry after computed-key fallback dedup, got {len(world)}: {list(world)}")
        canonical_name = list(world.keys())[0]
        self.assertEqual(canonical_name, "Zhao Yun", "Canonical should be highest-confidence entry")


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


class TestExtractWindowFailureGate(unittest.TestCase):
    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_character_extraction_failure_fails_gate(self, mock_invoke, mock_llm):
        """A single character extraction failure + 0 chars should fail the window gate."""
        import asyncio
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = [
            RuntimeError("LLM timeout"),   # character fails
            {"events": []},
            {"world_mentions": []},
            {"relationships": []},
            {"scene_summaries": []},
        ]
        state = _make_state(prompt_windows=[_make_window("win_fail", [0])])
        result = asyncio.run(extract_window(state, "win_fail"))
        metrics = result.get("window_metrics", {}).get("win_fail", {})
        self.assertFalse(
            metrics.get("gate_passed", True),
            "Gate should fail when character extraction errors and 0 chars extracted"
        )
        self.assertEqual(metrics.get("char_count_extracted", 0), 0)

    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_non_character_failure_still_passes_gate(self, mock_invoke, mock_llm):
        """A single non-character failure (world) with chars extracted should pass gate."""
        import asyncio
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = [
            {"new_characters": [{"canonical_name": "Hero", "confidence": 0.9, "importance": "core",
                                 "groupKey": "main_characters", "aliases": []}]},
            {"events": []},
            RuntimeError("world extraction failed"),  # world fails
            {"relationships": []},
            {"scene_summaries": []},
        ]
        state = _make_state(prompt_windows=[_make_window("win_ok", [0])])
        result = asyncio.run(extract_window(state, "win_ok"))
        metrics = result.get("window_metrics", {}).get("win_ok", {})
        self.assertTrue(
            metrics.get("gate_passed", False),
            "Gate should pass when only 1 non-character failure occurs and chars were extracted"
        )


# ── P1: proposal_write passes only needed keys to node_write_to_project ──────

class TestProposalWriteSlimWriteInput(unittest.TestCase):
    """node_write_to_project must NOT receive unneeded large blobs."""

    def test_unneeded_keys_evicted_before_write(self):
        """timeline_architecture and prompt_windows must not reach node_write_to_project."""
        import tempfile, json
        from pathlib import Path
        from sidecar.supervisor.tools import proposal_write

        captured_state: dict = {}

        async def _capture_write(state):
            captured_state.update(state)
            return {"proposals": [], "import_review_report": {}, "errors": [], "status": "done", "progress": 1.0}

        with tempfile.TemporaryDirectory() as td:
            artifact_dir = Path(td) / "system" / "imports" / "test_slim"
            artifact_dir.mkdir(parents=True, exist_ok=True)

            state = _make_state(
                project_path=td,
                import_run_id="test_slim",
                timeline_architecture={"events": [{"id": "e1"}], "branches": []},
                prompt_windows=[{"id": "pw1", "text": "long text " * 500}],
                entity_registry={"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
                supervisor_decisions=[{"decision": "test"}],
                window_metrics={"pw1": {"char_count_extracted": 3}},
            )

            with (
                patch("sidecar.supervisor.tools.node_build_manuscript", new=AsyncMock(return_value={"manuscript_chapters": []})),
                patch("sidecar.supervisor.tools.node_synthesize_relationships", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_classify_character_tags", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_infer_world_settings", new=AsyncMock(return_value={})),
                patch("sidecar.supervisor.tools.node_write_to_project", new=AsyncMock(side_effect=_capture_write)),
            ):
                _run(proposal_write(state))

        self.assertNotIn("timeline_architecture", captured_state,
                         "timeline_architecture must be evicted before node_write_to_project")
        self.assertNotIn("prompt_windows", captured_state,
                         "prompt_windows must be evicted before node_write_to_project")
        self.assertNotIn("supervisor_decisions", captured_state,
                         "supervisor_decisions must be evicted before node_write_to_project")
        self.assertNotIn("window_metrics", captured_state,
                         "window_metrics must be evicted before node_write_to_project")
        # Keys that ARE needed must still be present
        self.assertIn("entity_registry", captured_state)
        self.assertIn("project_path", captured_state)


# ── Cost guard: 402 budget exhaustion detection ───────────────────────────────

class TestBudgetExhausted402Detection(unittest.TestCase):
    def test_is_budget_exhausted_error_detects_402_in_message(self):
        from sidecar.supervisor.tools import _is_budget_exhausted_error
        exc = RuntimeError("APIStatusError: Error code: 402 - Insufficient Balance")
        self.assertTrue(_is_budget_exhausted_error(exc))

    def test_is_budget_exhausted_error_detects_insufficient_balance(self):
        from sidecar.supervisor.tools import _is_budget_exhausted_error
        exc = Exception("Insufficient Balance — please top up your account")
        self.assertTrue(_is_budget_exhausted_error(exc))

    def test_is_budget_exhausted_error_false_for_normal_errors(self):
        from sidecar.supervisor.tools import _is_budget_exhausted_error
        self.assertFalse(_is_budget_exhausted_error(RuntimeError("LLM timeout")))
        self.assertFalse(_is_budget_exhausted_error(ValueError("bad JSON")))
        self.assertFalse(_is_budget_exhausted_error(Exception("rate_limit_exceeded")))


class TestExtractWindowBudgetExhausted(unittest.TestCase):
    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_all_402_failures_set_budget_exhausted(self, mock_invoke, mock_llm):
        """All 5 prompts returning 402 errors must set budget_exhausted=True in result."""
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = RuntimeError(
            "APIStatusError: Error code: 402 - {'error': {'message': 'Insufficient Balance'}}"
        )
        state = _make_state(prompt_windows=[_make_window("win_402", [0])])
        result = asyncio.run(extract_window(state, "win_402"))
        self.assertTrue(result.get("budget_exhausted"), "budget_exhausted must be True when all prompts return 402")

    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_partial_402_failure_sets_budget_exhausted(self, mock_invoke, mock_llm):
        """Even one 402 error among 5 prompts must set budget_exhausted."""
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = [
            RuntimeError("Error code: 402 - Insufficient Balance"),  # character fails with 402
            {"events": []},
            {"world_mentions": []},
            {"relationships": []},
            {"scene_summaries": []},
        ]
        state = _make_state(prompt_windows=[_make_window("win_partial_402", [0])])
        result = asyncio.run(extract_window(state, "win_partial_402"))
        self.assertTrue(result.get("budget_exhausted"))

    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_non_402_failure_does_not_set_budget_exhausted(self, mock_invoke, mock_llm):
        """A normal LLM timeout must not set budget_exhausted."""
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = [
            RuntimeError("LLM connection timeout"),
            {"events": []},
            {"world_mentions": []},
            {"relationships": []},
            {"scene_summaries": []},
        ]
        state = _make_state(prompt_windows=[_make_window("win_timeout", [0])])
        result = asyncio.run(extract_window(state, "win_timeout"))
        self.assertFalse(result.get("budget_exhausted", False))

    @patch("sidecar.supervisor.tools._get_llm")
    @patch("sidecar.supervisor.tools._invoke_json_prompt")
    def test_budget_exhausted_adds_error_message(self, mock_invoke, mock_llm):
        """budget_exhausted=True must also add a clear error string to result['errors']."""
        mock_llm.return_value = MagicMock()
        mock_invoke.side_effect = RuntimeError("402 Insufficient Balance")
        state = _make_state(prompt_windows=[_make_window("win_err", [0])])
        result = asyncio.run(extract_window(state, "win_err"))
        errors = result.get("errors", [])
        self.assertTrue(any("budget_exhausted" in e or "402" in e for e in errors),
                        f"Expected budget_exhausted error message, got: {errors}")


# ── Cost guard: judge_import result_status ────────────────────────────────────

class TestJudgeImportResultStatus(unittest.TestCase):
    def _make_state_with_chars(self, profile: str, char_count: int) -> dict:
        chars = {f"char_{i}": {"canonical_name": f"C{i}", "importance": "supporting", "confidence": 0.8}
                 for i in range(char_count)}
        return _make_state(
            prompt_profile=profile,
            entity_registry={"characters": chars, "events": {}, "world": {}, "world_detailed": {}},
            chunks=[{"chunk_id": i, "content": f"ch{i}"} for i in range(10)],
            converge_target={"expected_min_characters": 20, "expected_min_events": 1},
        )

    def test_passed_status_when_all_gates_pass(self):
        chars = {f"char_{i}": {"canonical_name": f"C{i}", "importance": "supporting", "confidence": 0.8}
                 for i in range(30)}
        state = _make_state(
            prompt_profile="balanced",
            entity_registry={"characters": chars, "events": {}, "world": {}, "world_detailed": {}},
            chunks=[{"chunk_id": i, "content": f"ch{i}"} for i in range(10)],
            converge_target={"expected_min_characters": 10, "expected_min_events": 1},
            timeline_architecture={"canonical_events": [{"title": "e"}] * 15},
        )
        result = asyncio.run(judge_import(state))
        artifact = result.get("judge_artifact", {})
        self.assertEqual(artifact.get("result_status"), "passed")

    def test_acceptable_with_warnings_for_balanced_char_undercoverage_only(self):
        """Balanced profile + only character_undercoverage gate → acceptable_with_warnings."""
        state = self._make_state_with_chars("balanced", 5)  # far below target of 20
        state["converge_target"] = {"expected_min_characters": 20, "expected_min_events": 1}
        state["timeline_architecture"] = {"canonical_events": [{"title": "e"}] * 15}
        result = asyncio.run(judge_import(state))
        artifact = result.get("judge_artifact", {})
        self.assertIn("character_undercoverage", artifact.get("failed_gates", []))
        self.assertEqual(artifact.get("result_status"), "acceptable_with_warnings",
                         f"Balanced profile with only char_undercoverage should be acceptable_with_warnings, got {artifact.get('result_status')}")

    def test_failed_status_for_deep_profile_char_undercoverage(self):
        """Deep profile: character_undercoverage is a hard fail (result_status=needs_review)."""
        state = self._make_state_with_chars("deep", 5)
        state["converge_target"] = {"expected_min_characters": 20, "expected_min_events": 1}
        state["timeline_architecture"] = {"canonical_events": [{"title": "e"}] * 15}
        result = asyncio.run(judge_import(state))
        artifact = result.get("judge_artifact", {})
        self.assertNotEqual(artifact.get("result_status"), "acceptable_with_warnings",
                            "Deep profile should not use acceptable_with_warnings for char_undercoverage")

    def test_budget_exhausted_status_propagates(self):
        """When state has budget_exhausted=True, judge result_status must be budget_exhausted."""
        state = self._make_state_with_chars("balanced", 5)
        state["budget_exhausted"] = True
        result = asyncio.run(judge_import(state))
        artifact = result.get("judge_artifact", {})
        self.assertEqual(artifact.get("result_status"), "budget_exhausted")


# ── Cost guard: TOS thematic_rerun_wave_cap ───────────────────────────────────

class TestTOSThematicRerunWaveCap(unittest.TestCase):
    def test_deep_profile_has_wave_cap_1(self):
        from sidecar.models.state import plan_tool_operating_spec
        spec = plan_tool_operating_spec("deep", "zh", 50)
        self.assertEqual(spec["thematic_rerun_wave_cap"], 1)

    def test_fast_profile_has_wave_cap_0(self):
        from sidecar.models.state import plan_tool_operating_spec
        spec = plan_tool_operating_spec("fast", "en", 10)
        self.assertEqual(spec["thematic_rerun_wave_cap"], 0)

    def test_balanced_profile_has_wave_cap_1(self):
        from sidecar.models.state import plan_tool_operating_spec
        spec = plan_tool_operating_spec("balanced", "en", 20)
        self.assertEqual(spec["thematic_rerun_wave_cap"], 1)


if __name__ == "__main__":
    unittest.main()
