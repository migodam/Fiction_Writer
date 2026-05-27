"""W1 V2 orchestrator planner matrix — zero-cost dry-run validation.

Groups:
  1. TestOrchestratorPlannerMatrix — 5 source shapes, full planner chain assertions
  2. TestPromptVariantDispatch — prompt constant identity + manifest name checks
  3. TestArtifactIntegrity — file write, schema keys, no-secret scan
  4. TestConvergeTargetConsistency — acceptable floor, fast-vs-fine target divergence
"""
import json
import re

import pytest

from sidecar.models.state import (
    analyze_source_profile,
    plan_converge_target,
    plan_import_pipeline,
    plan_tool_operating_spec,
    select_granularity_profile,
    validate_import_plan,
)
from sidecar.prompts.w1_prompts import (
    W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    W1_EXTRACT_CHARACTERS_DEEP_FINE,
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    W1_EXTRACT_EVENTS_DEEP_DENSE,
    W1_EXTRACT_RELATIONSHIPS_CORE,
    W1_EXTRACT_RELATIONSHIPS_DENSE,
    W1_EXTRACT_RELATIONSHIPS_RECURRING,
    W1_EXTRACT_WORLD_DEEP_LORE,
    W1_EXTRACT_WORLD_DEEP_SPARSE,
    W1_EXTRACT_WORLD_DEEP_STRUCTURAL,
)
from sidecar.supervisor.tools import (
    _select_extraction_prompts,
    _selected_extraction_prompt_manifest,
)
from sidecar.workflows.w1_import import _write_import_artifact

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chunks(n, chars_each=1000):
    return [
        {"chunk_id": i, "content": "x" * chars_each, "chapter_hint": f"Ch{i+1}", "entity_mentions": []}
        for i in range(n)
    ]


def _build_state(n, lang, profile):
    chunks = _make_chunks(n)
    source_profile = analyze_source_profile(chunks, lang, profile)
    spec = plan_tool_operating_spec(profile, lang, n, use_supervisor=True)
    granularity = select_granularity_profile(n, lang, profile)
    target = plan_converge_target(spec, lang, n, granularity_profile=granularity)
    import_plan = plan_import_pipeline(granularity, spec, source_language=lang, prompt_profile=profile, chapter_count=n)
    is_valid, errors = validate_import_plan(import_plan)
    return {
        "chunks": chunks,
        "source_language": lang,
        "prompt_profile": profile,
        "source_profile": source_profile,
        "tool_operating_spec": spec,
        "import_granularity_profile": granularity,
        "converge_target": target,
        "import_plan": import_plan,
        "import_plan_validation": {"ok": is_valid, "errors": errors},
    }


# (n, lang, profile, exp_granularity_name, exp_source_type, exp_char_variant, exp_event_variant, exp_min_chars)
MATRIX = [
    (10, "zh", "deep",     "fine_short_story", "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_FINE,     W1_EXTRACT_EVENTS_DEEP_DENSE,   15),
    (50, "zh", "deep",     "coarse_webnovel",  "coarse_webnovel",  W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 50),
    (40, "en", "deep",     "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 40),
    (20, "en", "balanced", "balanced_novel",   "balanced_novel",   W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_CHAPTER, 24),
    (10, "en", "fast",     "coarse_webnovel",  "fine_short_story", W1_EXTRACT_CHARACTERS_DEEP_BALANCED,  W1_EXTRACT_EVENTS_DEEP_ARC,      5),
]

_SECRET_PATTERN = re.compile(r"sk-|DEEPSEEK_API_KEY|Bearer |api\.deepseek", re.IGNORECASE)


# ── Group 1: Orchestrator planner matrix ──────────────────────────────────────

class TestOrchestratorPlannerMatrix:
    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_granularity_profile_name(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        assert state["import_granularity_profile"]["profile_name"] == exp_gran

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_source_profile_recommended_type(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        assert state["source_profile"]["recommended_granularity_profile"] == exp_src

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_converge_target_expected_min_characters(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        assert state["converge_target"]["expected_min_characters"] == exp_min_chars

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_import_plan_validation_ok(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        assert state["import_plan_validation"]["ok"] is True
        assert state["import_plan_validation"]["errors"] == []

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_window_strategy_supervised_chapter_batching(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        assert state["import_plan"]["window_strategy"]["strategy"] == "supervised_chapter_batching"

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,_char,_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_all_import_plan_tools_enabled(self, n, lang, profile, exp_gran, exp_src, _char, _event, exp_min_chars):
        state = _build_state(n, lang, profile)
        tools = state["import_plan"]["tools"]
        assert len(tools) > 0
        assert all(t.get("enabled") is True for t in tools)

    def test_fast_profile_divergence_source_vs_execution(self):
        # source_profile is descriptive (10ch ≤ 15 → fine) while import_granularity_profile
        # reflects the fast execution override (fast → coarse regardless of chapter count)
        state = _build_state(10, "en", "fast")
        assert state["source_profile"]["recommended_granularity_profile"] == "fine_short_story"
        assert state["import_granularity_profile"]["profile_name"] == "coarse_webnovel"


# ── Group 2: Prompt variant dispatch ──────────────────────────────────────────

class TestPromptVariantDispatch:
    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,exp_char,exp_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_char_prompt_variant_identity(self, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars):
        state = _build_state(n, lang, profile)
        prompts = _select_extraction_prompts(state)
        assert prompts["character"] is exp_char

    @pytest.mark.parametrize(
        "n,lang,profile,exp_gran,exp_src,exp_char,exp_event,exp_min_chars",
        MATRIX,
        ids=[f"{r[0]}ch_{r[1]}_{r[2]}" for r in MATRIX],
    )
    def test_event_prompt_variant_identity(self, n, lang, profile, exp_gran, exp_src, exp_char, exp_event, exp_min_chars):
        state = _build_state(n, lang, profile)
        prompts = _select_extraction_prompts(state)
        assert prompts["event"] is exp_event

    def test_fine_case_manifest_constant_names(self):
        state = _build_state(10, "zh", "deep")
        manifest = _selected_extraction_prompt_manifest(state)
        assert manifest["character"]["prompt_constant"] == "W1_EXTRACT_CHARACTERS_DEEP_FINE"
        assert manifest["event"]["prompt_constant"] == "W1_EXTRACT_EVENTS_DEEP_DENSE"
        assert manifest["world"]["prompt_constant"] == "W1_EXTRACT_WORLD_DEEP_LORE"
        assert manifest["relationship"]["prompt_constant"] == "W1_EXTRACT_RELATIONSHIPS_DENSE"

    def test_coarse_case_manifest_constant_names(self):
        state = _build_state(50, "zh", "deep")
        manifest = _selected_extraction_prompt_manifest(state)
        assert manifest["character"]["prompt_constant"] == "W1_EXTRACT_CHARACTERS_DEEP_BALANCED"
        assert manifest["event"]["prompt_constant"] == "W1_EXTRACT_EVENTS_DEEP_CHAPTER"
        assert manifest["world"]["prompt_constant"] == "W1_EXTRACT_WORLD_DEEP_SPARSE"
        assert manifest["relationship"]["prompt_constant"] == "W1_EXTRACT_RELATIONSHIPS_CORE"

    def test_fast_case_arc_level_event(self):
        state = _build_state(10, "en", "fast")
        manifest = _selected_extraction_prompt_manifest(state)
        assert manifest["event"]["prompt_constant"] == "W1_EXTRACT_EVENTS_DEEP_ARC"


# ── Group 3: Artifact integrity ────────────────────────────────────────────────

class TestArtifactIntegrity:
    def test_write_source_profile_creates_file(self, tmp_path):
        state = _build_state(20, "en", "deep")
        path = _write_import_artifact(str(tmp_path), "run_test", "source_profile.json", state["source_profile"])
        written = json.loads((tmp_path / "system" / "imports" / "run_test" / "source_profile.json").read_text())
        assert "chapter_count" in written
        assert "recommended_granularity_profile" in written

    def test_write_import_plan_validation_creates_file(self, tmp_path):
        state = _build_state(20, "en", "deep")
        _write_import_artifact(str(tmp_path), "run_test", "import_plan_validation.json", state["import_plan_validation"])
        written = json.loads((tmp_path / "system" / "imports" / "run_test" / "import_plan_validation.json").read_text())
        assert "ok" in written
        assert isinstance(written["ok"], bool)
        assert "errors" in written

    def test_artifact_json_no_api_key(self):
        state = _build_state(20, "en", "deep")
        artifacts = [
            state["source_profile"],
            state["import_plan"],
            state["converge_target"],
            state["import_granularity_profile"],
            state["import_plan_validation"],
        ]
        for artifact in artifacts:
            serialized = json.dumps(artifact, ensure_ascii=False)
            assert not _SECRET_PATTERN.search(serialized), f"Secret pattern found in artifact: {serialized[:200]}"

    def test_source_profile_has_required_keys(self):
        state = _build_state(20, "en", "deep")
        sp = state["source_profile"]
        for key in ("chapter_count", "source_language", "avg_chars_per_chapter", "total_chars",
                    "estimated_source_type", "dialogue_density_hint", "named_entity_density_hint",
                    "recommended_granularity_profile", "confidence", "evidence"):
            assert key in sp, f"Missing key: {key}"

    def test_import_plan_has_required_keys(self):
        state = _build_state(20, "en", "deep")
        plan = state["import_plan"]
        for key in ("plan_version", "planner_kind", "source_type", "tools",
                    "window_strategy", "prompt_policy", "cost_policy", "safety"):
            assert key in plan, f"Missing key: {key}"

    def test_import_plan_validation_schema(self):
        state = _build_state(20, "en", "deep")
        v = state["import_plan_validation"]
        assert isinstance(v["ok"], bool)
        assert isinstance(v["errors"], list)

    def test_import_plan_safety_gates_set(self):
        state = _build_state(20, "en", "deep")
        safety = state["import_plan"]["safety"]
        assert safety["proposal_gate_required"] is True
        assert safety["schema_validated_plan"] is True
        assert safety["llm_planner_can_propose_only"] is True

    def test_import_plan_cost_policy_402_stop(self):
        state = _build_state(20, "en", "deep")
        assert state["import_plan"]["cost_policy"]["stop_on_api_402"] is True

    def test_import_plan_prompt_policy_no_dynamic_edits(self):
        state = _build_state(20, "en", "deep")
        assert state["import_plan"]["prompt_policy"]["dynamic_prompt_edits_allowed"] is False


# ── Group 4: Converge target consistency ──────────────────────────────────────

class TestConvergeTargetConsistency:
    def test_acceptable_floor_set_for_coarse_case(self):
        state = _build_state(50, "zh", "deep")
        target = state["converge_target"]
        assert "acceptable_min_characters" in target
        assert target["acceptable_min_characters"] <= target["expected_min_characters"]

    def test_acceptable_floor_set_for_balanced_case(self):
        state = _build_state(20, "en", "balanced")
        target = state["converge_target"]
        assert "acceptable_min_characters" in target
        assert target["acceptable_min_characters"] <= target["expected_min_characters"]

    def test_fine_min_chars_exceeds_fast_same_chapter_count(self):
        # Same 10 chapters, but fine_short_story (deep zh) should have higher targets than
        # coarse_fast (fast en) — proves fast override reduces expected coverage
        fine_state = _build_state(10, "zh", "deep")
        fast_state = _build_state(10, "en", "fast")
        assert fine_state["converge_target"]["expected_min_characters"] > fast_state["converge_target"]["expected_min_characters"]

    def test_all_cases_expected_min_chars_positive(self):
        for n, lang, profile, *_ in MATRIX:
            state = _build_state(n, lang, profile)
            assert state["converge_target"]["expected_min_characters"] >= 1
            assert state["converge_target"]["expected_min_events"] >= 1
