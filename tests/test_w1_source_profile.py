"""Tests for analyze_source_profile deterministic source profiler.

Groups:
  1. Source type classification (required 4 scenarios + 2 boundary)
  2. Profile field correctness
  3. Robustness: empty input, content fallback, missing entity_mentions
  4. ImportSupervisorState type surface
"""
import pytest

from sidecar.models.state import SourceProfile, analyze_source_profile


def _make_chunks(n, chars_each=1000, entity_count=5, text_key="content"):
    return [
        {
            "chunk_id": i,
            text_key: "x" * chars_each,
            "chapter_hint": f"Chapter {i + 1}",
            "entity_mentions": [f"e{j}" for j in range(entity_count)],
        }
        for i in range(n)
    ]


# ── Group 1: Source type classification ───────────────────────────────────────

class TestSourceTypeClassification:
    def test_10ch_zh_fine_short_story(self):
        p = analyze_source_profile(_make_chunks(10), "zh", "deep")
        assert p["recommended_granularity_profile"] == "fine_short_story"
        assert p["estimated_source_type"] == "fine_short_story"

    def test_50ch_zh_coarse_webnovel(self):
        p = analyze_source_profile(_make_chunks(50), "zh", "deep")
        assert p["recommended_granularity_profile"] == "coarse_webnovel"
        assert p["estimated_source_type"] == "coarse_webnovel"

    def test_40ch_en_balanced_novel(self):
        p = analyze_source_profile(_make_chunks(40), "en", "deep")
        assert p["recommended_granularity_profile"] == "balanced_novel"
        assert p["estimated_source_type"] == "balanced_novel"

    def test_20ch_en_balanced_novel(self):
        p = analyze_source_profile(_make_chunks(20), "en", "deep")
        assert p["recommended_granularity_profile"] == "balanced_novel"
        assert p["estimated_source_type"] == "balanced_novel"

    def test_15ch_boundary_fine(self):
        p = analyze_source_profile(_make_chunks(15), "en", "deep")
        assert p["recommended_granularity_profile"] == "fine_short_story"

    def test_31ch_zh_coarse(self):
        p = analyze_source_profile(_make_chunks(31), "zh", "deep")
        assert p["recommended_granularity_profile"] == "coarse_webnovel"


# ── Group 2: Profile field correctness ────────────────────────────────────────

class TestProfileFields:
    def test_chapter_count_matches_input(self):
        p = analyze_source_profile(_make_chunks(25), "en", "balanced")
        assert p["chapter_count"] == 25

    def test_total_chars_correct(self):
        p = analyze_source_profile(_make_chunks(10, chars_each=500), "en", "balanced")
        assert p["total_chars"] == 5000

    def test_avg_chars_per_chapter_correct(self):
        p = analyze_source_profile(_make_chunks(10, chars_each=500), "en", "balanced")
        assert p["avg_chars_per_chapter"] == 500.0

    @pytest.mark.parametrize("n,lang", [(10, "zh"), (50, "zh"), (40, "en"), (20, "en")])
    def test_confidence_in_valid_range(self, n, lang):
        p = analyze_source_profile(_make_chunks(n), lang, "deep")
        assert 0.0 <= p["confidence"] <= 1.0

    def test_evidence_is_nonempty_list(self):
        p = analyze_source_profile(_make_chunks(20), "en", "deep")
        assert isinstance(p["evidence"], list)
        assert len(p["evidence"]) > 0

    def test_dialogue_density_hint_valid(self):
        p = analyze_source_profile(_make_chunks(10), "en", "balanced")
        assert p["dialogue_density_hint"] in ("low", "medium", "high")

    def test_named_entity_density_hint_valid(self):
        p = analyze_source_profile(_make_chunks(10), "en", "balanced")
        assert p["named_entity_density_hint"] in ("sparse", "moderate", "dense")

    def test_source_language_preserved(self):
        p = analyze_source_profile(_make_chunks(10), "zh", "deep")
        assert p["source_language"] == "zh"


# ── Group 3: Robustness ────────────────────────────────────────────────────────

class TestRobustness:
    def test_empty_chunks_returns_valid_profile(self):
        p = analyze_source_profile([], "en")
        assert p["chapter_count"] == 0
        assert p["recommended_granularity_profile"] == "fine_short_story"
        assert isinstance(p["evidence"], list) and len(p["evidence"]) > 0
        assert "no chunks" in p["evidence"][0].lower()

    def test_content_fallback_manuscript_content(self):
        chunks = _make_chunks(5, chars_each=800, text_key="manuscript_content")
        p = analyze_source_profile(chunks, "en")
        assert p["total_chars"] == 5 * 800

    def test_content_fallback_raw_content(self):
        chunks = _make_chunks(5, chars_each=600, text_key="raw_content")
        p = analyze_source_profile(chunks, "en")
        assert p["total_chars"] == 5 * 600

    def test_missing_entity_mentions_no_error(self):
        chunks = [{"chunk_id": i, "content": "x" * 500} for i in range(10)]
        p = analyze_source_profile(chunks, "en")
        assert p["named_entity_density_hint"] == "sparse"

    def test_partial_missing_entity_mentions(self):
        chunks = (
            [{"chunk_id": i, "content": "x" * 500, "entity_mentions": ["a", "b"]} for i in range(5)]
            + [{"chunk_id": i + 5, "content": "x" * 500} for i in range(5)]
        )
        p = analyze_source_profile(chunks, "en")
        assert p["named_entity_density_hint"] in ("sparse", "moderate", "dense")


# ── Group 4: ImportSupervisorState type surface ────────────────────────────────

class TestImportSupervisorStateTypeSurface:
    def test_source_profile_key_accepted_by_state(self):
        profile = analyze_source_profile(_make_chunks(10), "en")
        state: dict = {"source_profile": profile}
        assert "recommended_granularity_profile" in state["source_profile"]
        assert "chapter_count" in state["source_profile"]
