"""Tests for W1 granularity profile selection and converge target overrides.

Covers:
- select_granularity_profile() decision table
- plan_converge_target() backward compat and profile override
"""
import pytest

from sidecar.models.state import (
    ImportGranularityProfile,
    plan_converge_target,
    plan_import_pipeline,
    plan_tool_operating_spec,
    select_granularity_profile,
)


# ---------------------------------------------------------------------------
# select_granularity_profile
# ---------------------------------------------------------------------------


class TestSelectGranularityProfile:
    def test_long_zh_deep_selects_coarse(self):
        p = select_granularity_profile(50, "zh", "deep")
        assert p["profile_name"] == "coarse_webnovel"

    def test_long_zh_fast_selects_coarse(self):
        p = select_granularity_profile(50, "zh", "fast")
        assert p["profile_name"] == "coarse_webnovel"

    def test_long_ko_deep_selects_coarse(self):
        p = select_granularity_profile(40, "ko", "deep")
        assert p["profile_name"] == "coarse_webnovel"

    def test_long_ja_balanced_selects_coarse(self):
        p = select_granularity_profile(35, "ja", "balanced")
        assert p["profile_name"] == "coarse_webnovel"

    def test_long_en_deep_selects_balanced(self):
        p = select_granularity_profile(40, "en", "deep")
        assert p["profile_name"] == "balanced_novel"

    def test_medium_en_deep_selects_balanced(self):
        p = select_granularity_profile(20, "en", "deep")
        assert p["profile_name"] == "balanced_novel"

    def test_short_en_deep_selects_fine(self):
        p = select_granularity_profile(12, "en", "deep")
        assert p["profile_name"] == "fine_short_story"

    def test_short_zh_deep_selects_fine(self):
        # Short CJK still goes to fine_short_story (length wins over language)
        p = select_granularity_profile(10, "zh", "deep")
        assert p["profile_name"] == "fine_short_story"

    def test_custom_long_zh_does_not_select_fine(self):
        p = select_granularity_profile(50, "zh", "custom")
        assert p["profile_name"] != "fine_short_story"

    def test_custom_long_en_does_not_select_fine(self):
        p = select_granularity_profile(50, "en", "custom")
        assert p["profile_name"] != "fine_short_story"

    def test_custom_short_selects_fine_via_length(self):
        p = select_granularity_profile(10, "en", "custom")
        assert p["profile_name"] == "fine_short_story"

    def test_new_granularity_fields_present_coarse(self):
        p = select_granularity_profile(50, "zh", "deep")
        assert "character_granularity" in p
        assert "event_density" in p
        assert "world_density" in p
        assert "relationship_depth" in p

    def test_new_granularity_fields_present_fine(self):
        p = select_granularity_profile(12, "en", "deep")
        assert "character_granularity" in p
        assert "event_density" in p
        assert "world_density" in p
        assert "relationship_depth" in p

    def test_coarse_webnovel_floor_fraction(self):
        p = select_granularity_profile(50, "zh", "deep")
        assert p["acceptable_floor_fraction"] == 0.80

    def test_fine_story_floor_fraction(self):
        p = select_granularity_profile(12, "en", "deep")
        assert p["acceptable_floor_fraction"] == 0.90

    def test_fast_min_chars_is_low(self):
        p = select_granularity_profile(50, "en", "fast")
        assert p["min_characters_per_chapter"] <= 0.5

    def test_long_en_deep_floor_is_80pct(self):
        p = select_granularity_profile(50, "en", "deep")
        assert p["acceptable_floor_fraction"] == 0.80


# ---------------------------------------------------------------------------
# plan_converge_target — backward compat and profile override
# ---------------------------------------------------------------------------


class TestPlanConvergeTargetWithGranularity:
    def _deep_tos(self, chapter_count: int = 50):
        return plan_tool_operating_spec("deep", chapter_count=chapter_count)

    def test_profile_none_unchanged(self):
        tos = self._deep_tos(50)
        old = plan_converge_target(tos, "en", 50)
        new = plan_converge_target(tos, "en", 50, granularity_profile=None)
        assert old == new

    def test_profile_none_no_acceptable_fields(self):
        tos = self._deep_tos(50)
        result = plan_converge_target(tos, "en", 50)
        assert "acceptable_min_characters" not in result
        assert "acceptable_min_events" not in result

    def test_65_chars_acceptable_with_coarse(self):
        tos = self._deep_tos(50)
        profile = select_granularity_profile(50, "zh", "deep")
        target = plan_converge_target(tos, "zh", 50, granularity_profile=profile)
        assert 65 >= target["expected_min_characters"]
        assert 65 >= target["acceptable_min_characters"]

    def test_68_chars_acceptable_with_coarse(self):
        tos = self._deep_tos(50)
        profile = select_granularity_profile(50, "zh", "deep")
        target = plan_converge_target(tos, "zh", 50, granularity_profile=profile)
        assert 68 >= target["expected_min_characters"]

    def test_coarse_expected_chars_is_50(self):
        tos = self._deep_tos(50)
        profile = select_granularity_profile(50, "zh", "deep")
        target = plan_converge_target(tos, "zh", 50, granularity_profile=profile)
        assert target["expected_min_characters"] == 50

    def test_coarse_floor_is_40(self):
        tos = self._deep_tos(50)
        profile = select_granularity_profile(50, "zh", "deep")
        target = plan_converge_target(tos, "zh", 50, granularity_profile=profile)
        assert target["acceptable_min_characters"] == 40

    def test_fine_story_keeps_high_target(self):
        tos = self._deep_tos(12)
        profile = select_granularity_profile(12, "en", "deep")
        target = plan_converge_target(tos, "en", 12, granularity_profile=profile)
        assert target["expected_min_characters"] == 18  # 1.5 × 12

    def test_fine_story_acceptable_floor(self):
        tos = self._deep_tos(12)
        profile = select_granularity_profile(12, "en", "deep")
        target = plan_converge_target(tos, "en", 12, granularity_profile=profile)
        # floor = 0.90 × 18 = 16
        assert target["acceptable_min_characters"] == 16

    def test_protagonist_list_empty_by_default(self):
        tos = self._deep_tos(50)
        profile = select_granularity_profile(50, "zh", "deep")
        target = plan_converge_target(tos, "zh", 50, granularity_profile=profile)
        assert target.get("protagonist_list", []) == []

    def test_other_fields_unaffected_by_profile(self):
        tos = self._deep_tos(50)
        no_profile = plan_converge_target(tos, "en", 50)
        profile = select_granularity_profile(50, "zh", "deep")
        with_profile = plan_converge_target(tos, "en", 50, granularity_profile=profile)
        # Non-character/event fields should be unchanged
        assert with_profile["expected_max_canonical_events"] == no_profile["expected_max_canonical_events"]
        assert with_profile["expected_min_world_entities"] == no_profile["expected_min_world_entities"]
        assert with_profile["expected_timeline_topology"] == no_profile["expected_timeline_topology"]

    def test_balanced_profile_medium_source(self):
        tos = self._deep_tos(20)
        profile = select_granularity_profile(20, "en", "deep")
        target = plan_converge_target(tos, "en", 20, granularity_profile=profile)
        # balanced_novel: 1.2 × 20 = 24
        assert target["expected_min_characters"] == 24
        # floor: 0.85 × 24 = 20
        assert target["acceptable_min_characters"] == 20


# ---------------------------------------------------------------------------
# plan_import_pipeline — schema-first deterministic planner foundation
# ---------------------------------------------------------------------------


class TestPlanImportPipeline:
    def test_coarse_webnovel_plan_records_window_and_prompt_policy(self):
        tos = plan_tool_operating_spec("deep", "zh", 50)
        profile = select_granularity_profile(50, "zh", "deep")
        plan = plan_import_pipeline(profile, tos, source_language="zh", prompt_profile="deep", chapter_count=50)

        assert plan["planner_kind"] == "deterministic_rules"
        assert plan["source_type"] == "coarse_webnovel"
        assert plan["window_strategy"]["strategy"] == "supervised_chapter_batching"
        assert plan["prompt_policy"]["variant_dispatch"] is True
        assert plan["prompt_policy"]["dynamic_prompt_edits_allowed"] is False
        assert plan["cost_policy"]["stop_on_api_402"] is True
        assert [step["order"] for step in plan["tools"]] == sorted(step["order"] for step in plan["tools"])
        assert "proposal_write" in {step["tool"] for step in plan["tools"]}

    def test_fine_story_plan_contains_dense_tool_granularity(self):
        tos = plan_tool_operating_spec("deep", "zh", 10)
        profile = select_granularity_profile(10, "zh", "deep")
        plan = plan_import_pipeline(profile, tos, source_language="zh", prompt_profile="deep", chapter_count=10)
        tools = {step["tool"]: step for step in plan["tools"]}

        assert plan["source_type"] == "fine_short_story"
        assert tools["extract_character"]["prompt_granularity"] == "all"
        assert tools["extract_event"]["prompt_granularity"] == "scene_level"
        assert tools["extract_world"]["prompt_granularity"] == "full_lore"
        assert tools["extract_relationship"]["prompt_granularity"] == "dense"

    def test_import_plan_is_schema_safe_for_future_llm_planners(self):
        tos = plan_tool_operating_spec("balanced", "en", 20)
        profile = select_granularity_profile(20, "en", "balanced")
        plan = plan_import_pipeline(profile, tos, source_language="en", prompt_profile="balanced", chapter_count=20)

        assert plan["safety"]["schema_validated_plan"] is True
        assert plan["safety"]["llm_planner_can_propose_only"] is True
        assert all("tool" in step and "enabled" in step and "order" in step for step in plan["tools"])
