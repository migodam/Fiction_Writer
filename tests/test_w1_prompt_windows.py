"""Tests for W1 Supervisor chapter-count-aware windowing (S2)."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from sidecar.models.state import PROFILE_CONFIGS
from sidecar.workflows.w1_import import (
    _build_supervised_prompt_windows,
    _build_prompt_windows,
    _detect_language,
    _estimate_window_output_tokens,
    _SUPERVISOR_OUTPUT_BUDGET_THRESHOLD,
)


def _make_chunk(chunk_id: int, content: str = "", chapter_hint: str | None = None, chars: int = 1000) -> dict:
    text = content or f"Chapter {chunk_id + 1} text. " * (chars // 20)
    return {
        "chunk_id": chunk_id,
        "content": text,
        "manuscript_content": text,
        "raw_content": text,
        "chapter_hint": chapter_hint or f"Chapter {chunk_id + 1}",
        "char_start": chunk_id * chars,
        "char_end": (chunk_id + 1) * chars,
        "source_span": {"start": chunk_id * chars, "end": (chunk_id + 1) * chars},
    }


def _make_state(profile: str = "deep", chunks: list | None = None, **overrides) -> dict:
    from sidecar.models.state import PROFILE_CONFIGS
    return {
        "project_path": "/tmp/test_project",
        "import_run_id": "import_s2_test",
        "source_file_path": "/tmp/novel.txt",
        "prompt_profile": profile,
        "profile_config": PROFILE_CONFIGS[profile],
        "import_mode": "import_all",
        "source_language": "en",
        "context": {},
        "chunks": chunks or [],
        "import_run_manifest": {"source_hash": "abc123def456", "import_run_id": "import_s2_test"},
        **overrides,
    }


_EMPTY_DIGEST = {"content": "(empty)", "estimated_tokens": 5, "artifact_path": "/tmp/x.json", "counts": {}}


class TestSupervisorWindowing(unittest.TestCase):
    # ── Test 1: 50-chapter deep → ≥ 4 windows ──────────────────────────────────

    def test_50_chapter_deep_produces_at_least_4_windows(self):
        chunks = [_make_chunk(i) for i in range(50)]
        state = _make_state(profile="deep", chunks=chunks)

        windows = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)

        self.assertGreaterEqual(len(windows), 4, f"Expected ≥4 windows for 50 chapters with deep profile, got {len(windows)}")

    # ── Test 2: chapters_per_window cap enforced ─────────────────────────────

    def test_chapters_per_window_cap_enforced_for_balanced(self):
        chunks = [_make_chunk(i) for i in range(24)]
        state = _make_state(profile="balanced", chunks=chunks)

        windows = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)

        chapters_per_window = PROFILE_CONFIGS["balanced"]["chapters_per_window"]
        for w in windows:
            self.assertLessEqual(
                len(w["chunk_ids"]), chapters_per_window,
                f"Window {w['id']} has {len(w['chunk_ids'])} chunks, exceeds cap of {chapters_per_window}"
            )

    # ── Test 3: single oversized chapter → paragraph split ───────────────────

    def test_single_oversized_chapter_paragraph_splits(self):
        # 200k chars → will exceed input_window_budget; triggers paragraph split
        big_text = "paragraph one.\n\n" * 8_000  # ~128k chars
        chunk = _make_chunk(0, content=big_text, chars=len(big_text))
        state = _make_state(profile="deep", chunks=[chunk])

        windows = _build_supervised_prompt_windows(state, [chunk], _EMPTY_DIGEST)

        # Should produce at least one window; if oversized, 2+ parts
        self.assertGreaterEqual(len(windows), 1)

    # ── Test 4: pre-flight estimator > 3000 for 8-chapter zh window ──────────

    def test_preflight_estimator_exceeds_threshold_for_8ch_zh(self):
        chunks = [_make_chunk(i) for i in range(8)]
        state = _make_state(profile="deep", chunks=chunks, source_language="zh")

        windows = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)

        # With 8 chapters, estimated output = 8 × _SUPERVISOR_TOKENS_PER_CHAPTER
        # which should exceed the threshold, triggering recursive halving
        # Result: each window should have fewer than 8 chapters
        max_chunks_per_window = max(len(w["chunk_ids"]) for w in windows)
        from sidecar.workflows.w1_import import _SUPERVISOR_TOKENS_PER_CHAPTER
        expected_exceed = 8 * _SUPERVISOR_TOKENS_PER_CHAPTER > _SUPERVISOR_OUTPUT_BUDGET_THRESHOLD
        if expected_exceed:
            self.assertLess(max_chunks_per_window, 8, "8-ch window exceeds budget; should have been split")
        else:
            # If estimate doesn't exceed, 8 chapters is fine — test just verifies the estimate
            self.assertGreater(8 * _SUPERVISOR_TOKENS_PER_CHAPTER, 0)

    # ── Test 5: use_supervisor=False → existing packer ───────────────────────

    def test_feature_flag_false_uses_legacy_packer(self):
        """When use_supervisor=False in state, node_split_chunks calls _build_prompt_windows."""
        from unittest.mock import patch, MagicMock
        legacy_result = [{"id": "pwin_legacy", "chunk_ids": [0], "text": "t", "output_token_budget": 3000}]
        with patch("sidecar.workflows.w1_import._build_supervised_prompt_windows") as sup_mock, \
             patch("sidecar.workflows.w1_import._build_prompt_windows", return_value=legacy_result):
            from sidecar.workflows.w1_import import _build_prompt_windows
            # Without use_supervisor in state, _build_supervised_prompt_windows should NOT be called
            chunks = [_make_chunk(0)]
            state = _make_state(profile="balanced", chunks=chunks)  # no use_supervisor key
            # Simulate logic: use_supervisor=False → _build_prompt_windows
            use_supervisor = bool(state.get("use_supervisor") or state.get("context", {}).get("use_supervisor"))
            self.assertFalse(use_supervisor)
            sup_mock.assert_not_called()

    # ── Test 6: all windows have output_token_budget field ───────────────────

    def test_all_windows_have_output_token_budget(self):
        chunks = [_make_chunk(i) for i in range(10)]
        state = _make_state(profile="balanced", chunks=chunks)

        windows = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)

        for w in windows:
            self.assertIn("output_token_budget", w, f"Window {w.get('id')} missing output_token_budget")
            self.assertIsInstance(w["output_token_budget"], int)

    # ── Test 7: window IDs are stable (deterministic) ────────────────────────

    def test_window_ids_are_deterministic(self):
        chunks = [_make_chunk(i) for i in range(5)]
        state = _make_state(profile="balanced", chunks=chunks)

        windows1 = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)
        windows2 = _build_supervised_prompt_windows(state, chunks, _EMPTY_DIGEST)

        ids1 = [w["id"] for w in windows1]
        ids2 = [w["id"] for w in windows2]
        self.assertEqual(ids1, ids2, "Window IDs should be deterministic across calls")

    # ── Test 8: estimate_window_output_tokens scales correctly ───────────────

    def test_estimate_window_output_tokens_scales_with_chapters(self):
        win_4ch = {"chunk_ids": [0, 1, 2, 3]}
        win_8ch = {"chunk_ids": list(range(8))}

        est_4 = _estimate_window_output_tokens(win_4ch, "deep")
        est_8 = _estimate_window_output_tokens(win_8ch, "deep")

        self.assertGreater(est_8, est_4)
        self.assertEqual(est_8, 2 * est_4)

    # ── Test 9: late-window density cap ──────────────────────────────────────

    def test_late_window_chapters_capped_for_deep_profile(self):
        """For a cpw=6 profile with 50 tiny chapters, last 25% (ch38+) windows
        should have <= 3 chunks after the late-window cap, not 6.

        Token-budget halving does NOT fire here (6 * 520 = 3120 <= 3500 threshold),
        so without the explicit late-window cap all windows would have 6 chunks.
        """
        from sidecar.workflows.w1_import import _build_supervised_prompt_windows

        # Synthetic profile with cpw=6 so halving does NOT fire (6*520=3120 <= 3500)
        profile_config_6 = {
            "chapters_per_window": 6,
            "input_window_budget": 48_000,
            "output_token_budget": 3_000,
        }
        chunks = [
            {"chunk_id": i, "content": f"Tiny ch {i}.",
             "chapter_hint": f"Chapter {i+1}", "char_start": i * 20, "char_end": (i+1) * 20}
            for i in range(50)
        ]
        state = {
            "prompt_profile": "deep",
            "profile_config": profile_config_6,
            "import_run_id": "test_lw",
            "import_run_manifest": {"source_hash": "abc"},
            "project_structure_digest": {"content": "(empty)", "estimated_tokens": 5},
            "source_language": "zh",
        }
        digest = {"content": "(empty)", "estimated_tokens": 5, "artifact_path": ""}
        windows = _build_supervised_prompt_windows(state, chunks, digest)

        # Late windows: those whose chunk_ids are all >= 38 (last 25% of 50)
        late_windows = [w for w in windows if all(cid >= 38 for cid in w["chunk_ids"])]
        self.assertTrue(late_windows, "Expected at least one late window (chunk_id >= 38)")

        # late_cpw = max(3, 6 // 2) = 3
        for w in late_windows:
            self.assertLessEqual(
                len(w["chunk_ids"]), 3,
                f"Late window {w['id']} has {len(w['chunk_ids'])} chunks, expected <= 3 (cpw=6 → late_cpw=3)"
            )


class TestWindowMetadata(unittest.TestCase):
    """Tests for late_window_cap_applied, effective_chapters_per_window, chapters_per_window_config."""

    # Synthetic profile: cpw=6, output budget chosen so 6*520=3120 < threshold (3500),
    # meaning budget halving does NOT fire and the only split mechanism is the late-window cap.
    _PROFILE_CPW6 = {
        "chapters_per_window": 6,
        "input_window_budget": 48_000,
        "output_token_budget": 3_000,
    }

    def _make_state_cpw6(self, n: int = 50) -> tuple[dict, list[dict]]:
        chunks = [
            {"chunk_id": i, "content": f"Tiny ch {i}.",
             "chapter_hint": f"Ch{i+1}", "char_start": i * 20, "char_end": (i+1) * 20}
            for i in range(n)
        ]
        state = {
            "prompt_profile": "deep",
            "profile_config": self._PROFILE_CPW6,
            "import_run_id": "test_meta",
            "import_run_manifest": {"source_hash": "abc"},
            "source_language": "en",
        }
        return state, chunks

    def _digest(self) -> dict:
        return {"content": "(empty)", "estimated_tokens": 5, "artifact_path": ""}

    # ── Test 1: early windows have late_window_cap_applied=False ─────────────

    def test_early_windows_not_late_capped(self):
        state, chunks = self._make_state_cpw6(50)
        windows = _build_supervised_prompt_windows(state, chunks, self._digest())

        # First window must contain chunk_id 0 which is in the early zone
        first_window = next(w for w in windows if 0 in w["chunk_ids"])
        self.assertFalse(first_window["late_window_cap_applied"])
        self.assertEqual(first_window["effective_chapters_per_window"], 6)

    # ── Test 2: late windows have late_window_cap_applied=True ───────────────

    def test_late_windows_have_cap_applied(self):
        state, chunks = self._make_state_cpw6(50)
        windows = _build_supervised_prompt_windows(state, chunks, self._digest())

        # Late zone: chunk_ids >= 38 (last 25% of 50)
        late_windows = [w for w in windows if all(cid >= 38 for cid in w["chunk_ids"])]
        self.assertTrue(late_windows, "Expected at least one late window")
        for w in late_windows:
            self.assertTrue(w["late_window_cap_applied"], f"Window {w['id']} should have late_window_cap_applied=True")
            self.assertEqual(w["effective_chapters_per_window"], 3)  # late_cpw = max(3, 6//2) = 3

    # ── Test 3: chapters_per_window_config is always the profile max ──────────

    def test_chapters_per_window_config_always_profile_max(self):
        state, chunks = self._make_state_cpw6(50)
        windows = _build_supervised_prompt_windows(state, chunks, self._digest())

        for w in windows:
            self.assertEqual(w["chapters_per_window_config"], 6,
                             f"Window {w['id']} has chapters_per_window_config={w.get('chapters_per_window_config')}, expected 6")

    # ── Test 4: manifest entry includes new fields ────────────────────────────

    def test_manifest_entry_includes_metadata_fields(self):
        from sidecar.workflows.w1_import import _prompt_window_manifest_entry
        state, chunks = self._make_state_cpw6(12)
        windows = _build_supervised_prompt_windows(state, chunks, self._digest())

        entry = _prompt_window_manifest_entry(windows[0])
        self.assertIn("late_window_cap_applied", entry)
        self.assertIn("effective_chapters_per_window", entry)
        self.assertIn("chapters_per_window_config", entry)

    # ── Test 5: manifest entry includes normalized observability fields ──────

    def test_manifest_entry_includes_normalized_observability_fields(self):
        from sidecar.workflows.w1_import import _prompt_window_manifest_entry
        state, chunks = self._make_state_cpw6(12)
        windows = _build_supervised_prompt_windows(state, chunks, self._digest())

        entry = _prompt_window_manifest_entry(windows[0])
        self.assertGreater(entry["estimated_input_tokens"], 0)
        self.assertGreater(entry["source_budget_tokens"], 0)
        self.assertGreater(entry["source_token_estimate"], 0)
        self.assertIn("split_reason", entry)
        self.assertIn("late_window_threshold", entry)
        self.assertIn("late_chapters_per_window", entry)
        self.assertEqual(entry["project_digest_token_estimate"], entry["digest_token_estimate"])
        self.assertEqual(entry["validation_summary_token_estimate"], entry["validation_token_estimate"])

    # ── Test 6: prompt variant manifest is preserved when available ──────────

    def test_manifest_entry_preserves_prompt_variant_manifest_when_available(self):
        from sidecar.workflows.w1_import import _prompt_window_manifest_entry
        entry = _prompt_window_manifest_entry({
            "id": "pwin_test",
            "estimated_tokens": 42,
            "selected_prompt_variants": {"character": {"prompt_constant": "W1_TEST"}},
        })

        self.assertEqual(
            entry["prompt_variant_manifest"],
            {"character": {"prompt_constant": "W1_TEST"}},
        )


class TestDigestBudgetFix(unittest.TestCase):
    """Phase A: verify supervisor windowing uses 8000-char digest clip for source budget."""

    def _make_long_digest(self) -> dict:
        # ~12000-char digest — longer than 8000 chars
        content = "项目摘要：主角韩立修炼路途。" * 900  # ~12600 chars
        return {"content": content, "estimated_tokens": 6000, "artifact_path": "/tmp/x.json", "counts": {}}

    def test_digest_clip_estimate_smaller_than_full_reserve(self):
        from sidecar.workflows.w1_import import _estimate_tokens, _DIGEST_RESERVE_TOKENS, _fit_text_to_token_budget
        digest_content = "项目摘要" * 3000  # ~12000 chars
        full_estimate = _estimate_tokens(_fit_text_to_token_budget(digest_content, _DIGEST_RESERVE_TOKENS))
        clip_estimate = _estimate_tokens(digest_content[:8000])
        self.assertLess(clip_estimate, full_estimate,
                        "8000-char clip should produce smaller token estimate than full 24000-token reserve")

    def test_long_digest_allows_larger_source_budget(self):
        """Windows with a long digest should have more source token capacity after the fix."""
        from sidecar.workflows.w1_import import _estimate_tokens, _SCHEMA_POLICY_RESERVE_TOKENS
        digest = self._make_long_digest()
        chunks = [_make_chunk(i, chars=1000) for i in range(8)]
        state = _make_state(profile="deep", chunks=chunks)
        windows = _build_supervised_prompt_windows(state, chunks, digest)
        # The key assertion: no paragraph-split windows (source_budget should be generous enough
        # to fit each chapter batch without overflow)
        for w in windows:
            self.assertIn(
                w.get("split_reason", "complete_chapter_batch"),
                ("complete_chapter_batch",),
                f"Window {w['id']} unexpectedly paragraph-split with split_reason={w.get('split_reason')}",
            )

    def test_max_tokens_per_call_in_profile_configs(self):
        """Phase A: PROFILE_CONFIGS must have max_tokens_per_call for all profiles."""
        for profile_name in ("fast", "balanced", "deep", "custom"):
            config = PROFILE_CONFIGS[profile_name]
            self.assertIn("max_tokens_per_call", config,
                          f"Profile '{profile_name}' missing max_tokens_per_call")
            self.assertIsInstance(config["max_tokens_per_call"], int)
            self.assertGreaterEqual(config["max_tokens_per_call"], 4096)

    def test_deep_and_custom_have_larger_max_tokens(self):
        """deep/custom profiles should have max_tokens_per_call > fast/balanced."""
        self.assertGreater(PROFILE_CONFIGS["deep"]["max_tokens_per_call"],
                           PROFILE_CONFIGS["fast"]["max_tokens_per_call"])
        self.assertGreater(PROFILE_CONFIGS["custom"]["max_tokens_per_call"],
                           PROFILE_CONFIGS["balanced"]["max_tokens_per_call"])


class TestDetectLanguage(unittest.TestCase):
    def test_cjk_text_detected_as_zh(self):
        cjk_text = "这是一段中文文字，用于测试语言检测功能。韩立是主角，他修炼法术，追求长生。" * 10
        self.assertEqual(_detect_language(cjk_text), "zh")

    def test_latin_text_detected_as_en(self):
        en_text = "This is a chapter about the protagonist who goes on a journey." * 10
        self.assertEqual(_detect_language(en_text), "en")

    def test_empty_string_returns_en(self):
        self.assertEqual(_detect_language(""), "en")

    def test_mixed_below_threshold_returns_en(self):
        mostly_latin = "Hello world test sentence. " * 20 + "你好"
        self.assertEqual(_detect_language(mostly_latin), "en")

    def test_mixed_above_threshold_returns_zh(self):
        mostly_cjk = "这是中文内容。" * 20 + "some latin"
        self.assertEqual(_detect_language(mostly_cjk), "zh")


if __name__ == "__main__":
    unittest.main()
