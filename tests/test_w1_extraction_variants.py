"""B1 tests for W1 extraction prompt variant constants.

All tests are pure string assertions — no LLM calls, no I/O.
Groups:
  1. Existing constants regression guard
  2. New variant existence and template variables
  3. Policy content assertions
"""
import pytest

from sidecar.prompts.w1_prompts import (
    # Existing (must remain unchanged)
    W1_EXTRACT_CHARACTERS_DEEP,
    W1_EXTRACT_EVENTS_DEEP,
    W1_EXTRACT_WORLD_DEEP,
    W1_EXTRACT_RELATIONSHIPS_CHUNK,
    # Character variants
    W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL,
    W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    W1_EXTRACT_CHARACTERS_DEEP_FINE,
    # Event variants
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    W1_EXTRACT_EVENTS_DEEP_DENSE,
    # World variants
    W1_EXTRACT_WORLD_DEEP_SPARSE,
    W1_EXTRACT_WORLD_DEEP_STRUCTURAL,
    W1_EXTRACT_WORLD_DEEP_LORE,
    # Relationship variants
    W1_EXTRACT_RELATIONSHIPS_CORE,
    W1_EXTRACT_RELATIONSHIPS_RECURRING,
    W1_EXTRACT_RELATIONSHIPS_DENSE,
)

_CHAR_VARIANTS = [
    W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL,
    W1_EXTRACT_CHARACTERS_DEEP_BALANCED,
    W1_EXTRACT_CHARACTERS_DEEP_FINE,
]
_EVENT_VARIANTS = [
    W1_EXTRACT_EVENTS_DEEP_ARC,
    W1_EXTRACT_EVENTS_DEEP_CHAPTER,
    W1_EXTRACT_EVENTS_DEEP_DENSE,
]
_WORLD_VARIANTS = [
    W1_EXTRACT_WORLD_DEEP_SPARSE,
    W1_EXTRACT_WORLD_DEEP_STRUCTURAL,
    W1_EXTRACT_WORLD_DEEP_LORE,
]
_REL_VARIANTS = [
    W1_EXTRACT_RELATIONSHIPS_CORE,
    W1_EXTRACT_RELATIONSHIPS_RECURRING,
    W1_EXTRACT_RELATIONSHIPS_DENSE,
]
_ALL_12 = _CHAR_VARIANTS + _EVENT_VARIANTS + _WORLD_VARIANTS + _REL_VARIANTS

_REQUIRED_VARS = [
    "{source_language_label}",
    "{language_policy}",
    "{chunk_content}",
    "{entity_registry_summary}",
    "{chunk_id}",
    "{total_chunks}",
]


# ── Group 1: Existing constants are intact ─────────────────────────────────────

class TestExistingConstantsUnchanged:
    def test_existing_constants_still_exist(self):
        for c in [W1_EXTRACT_CHARACTERS_DEEP, W1_EXTRACT_EVENTS_DEEP,
                  W1_EXTRACT_WORLD_DEEP, W1_EXTRACT_RELATIONSHIPS_CHUNK]:
            assert isinstance(c, str) and len(c) > 100

    def test_existing_constants_are_not_variant_aliases(self):
        assert W1_EXTRACT_CHARACTERS_DEEP is not W1_EXTRACT_CHARACTERS_DEEP_BALANCED
        assert W1_EXTRACT_EVENTS_DEEP is not W1_EXTRACT_EVENTS_DEEP_CHAPTER
        assert W1_EXTRACT_WORLD_DEEP is not W1_EXTRACT_WORLD_DEEP_STRUCTURAL
        assert W1_EXTRACT_RELATIONSHIPS_CHUNK is not W1_EXTRACT_RELATIONSHIPS_RECURRING

    def test_existing_constants_contain_known_anchor_text(self):
        assert "W1 Import Character Compiler" in W1_EXTRACT_CHARACTERS_DEEP
        assert "Timeline Scout" in W1_EXTRACT_EVENTS_DEEP
        assert "deep world extraction" in W1_EXTRACT_WORLD_DEEP
        assert "cross-validate character identity" in W1_EXTRACT_RELATIONSHIPS_CHUNK


# ── Group 2: New variant constants exist and have template vars ────────────────

class TestVariantExistenceAndTemplateVars:
    def test_all_12_new_variant_constants_are_nonempty_strings(self):
        for c in _ALL_12:
            assert isinstance(c, str) and len(c) > 100, f"variant too short: {c[:40]!r}"

    @pytest.mark.parametrize("variant", _CHAR_VARIANTS)
    def test_character_variants_contain_required_template_vars(self, variant):
        for var in _REQUIRED_VARS:
            assert var in variant, f"missing {var!r} in character variant"

    @pytest.mark.parametrize("variant", _EVENT_VARIANTS)
    def test_event_variants_contain_required_template_vars(self, variant):
        for var in _REQUIRED_VARS:
            assert var in variant, f"missing {var!r} in event variant"

    @pytest.mark.parametrize("variant", _WORLD_VARIANTS)
    def test_world_variants_contain_required_template_vars(self, variant):
        for var in _REQUIRED_VARS:
            assert var in variant, f"missing {var!r} in world variant"

    @pytest.mark.parametrize("variant", _REL_VARIANTS)
    def test_relationship_variants_contain_required_template_vars(self, variant):
        for var in _REQUIRED_VARS:
            assert var in variant, f"missing {var!r} in relationship variant"


# ── Group 3: Policy content assertions ────────────────────────────────────────

class TestPolicyContent:
    def test_webnovel_char_policy_excludes_npcs(self):
        assert "EXCLUDE" in W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL
        assert "guards" in W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL.lower() or \
               "shopkeeper" in W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL.lower()

    def test_webnovel_char_policy_cap_is_5(self):
        assert "≤5" in W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL

    def test_fine_char_policy_includes_socially_meaningful(self):
        assert (
            "socially meaningful" in W1_EXTRACT_CHARACTERS_DEEP_FINE.lower()
            or "named-by-role" in W1_EXTRACT_CHARACTERS_DEEP_FINE.lower()
        )

    def test_fine_char_is_not_the_default(self):
        assert W1_EXTRACT_CHARACTERS_DEEP_FINE is not W1_EXTRACT_CHARACTERS_DEEP

    def test_arc_event_policy_max_6_per_window(self):
        assert "6" in W1_EXTRACT_EVENTS_DEEP_ARC

    def test_dense_event_policy_cap_40(self):
        assert "40" in W1_EXTRACT_EVENTS_DEEP_DENSE

    def test_sparse_world_policy_omits_attributes(self):
        assert "omit" in W1_EXTRACT_WORLD_DEEP_SPARSE.lower()
        assert "attributes" in W1_EXTRACT_WORLD_DEEP_SPARSE.lower()

    def test_lore_world_policy_allows_full_attributes(self):
        assert "full" in W1_EXTRACT_WORLD_DEEP_LORE.lower()

    def test_core_relationship_cap_3(self):
        assert "≤3" in W1_EXTRACT_RELATIONSHIPS_CORE
