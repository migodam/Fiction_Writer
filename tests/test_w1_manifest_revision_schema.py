"""Tests for validate_manifest_revision() schema validator in planner.py."""
from __future__ import annotations

import pytest

from sidecar.supervisor.planner import validate_manifest_revision


def _valid_demote() -> dict:
    return {
        "revision_type": "demote",
        "window_id": "w3",
        "dedupeKey": "hanlì_market_supplies_ch3",
        "action": "demote_to_scene_beat",
        "reason": "Event is logistics-only; no state change.",
        "revised_by": "importance_dilution_signal",
    }


# ── 1. Valid demote ───────────────────────────────────────────────────────────

def test_valid_demote():
    ok, errors = validate_manifest_revision(_valid_demote())
    assert ok is True
    assert errors == []


# ── 2. Unknown revision_type ──────────────────────────────────────────────────

def test_unknown_revision_type():
    rev = _valid_demote()
    rev["revision_type"] = "delete"
    ok, errors = validate_manifest_revision(rev)
    assert ok is False
    assert any("revision_type" in e for e in errors)


# ── 3. Unknown action ─────────────────────────────────────────────────────────

def test_unknown_action():
    rev = _valid_demote()
    rev["action"] = "free_form_edit"
    ok, errors = validate_manifest_revision(rev)
    assert ok is False
    assert any("action" in e for e in errors)


# ── 4. Empty dedupeKey ────────────────────────────────────────────────────────

def test_empty_dedupeKey():
    rev = _valid_demote()
    rev["dedupeKey"] = ""
    ok, errors = validate_manifest_revision(rev)
    assert ok is False
    assert any("dedupeKey" in e for e in errors)


def test_missing_dedupeKey():
    rev = _valid_demote()
    del rev["dedupeKey"]
    ok, errors = validate_manifest_revision(rev)
    assert ok is False
    assert any("dedupeKey" in e for e in errors)


# ── 5. Unknown field rejected ─────────────────────────────────────────────────

def test_unknown_field_rejected():
    rev = _valid_demote()
    rev["raw_text"] = "韩立前往集市购买药材，买了一堆草药"
    ok, errors = validate_manifest_revision(rev)
    assert ok is False
    assert any("unknown" in e.lower() for e in errors)


# ── 6. All four revision_types valid ─────────────────────────────────────────

@pytest.mark.parametrize("revision_type", ["promote", "demote", "merge", "reclassify"])
def test_all_four_types_valid(revision_type):
    rev = _valid_demote()
    rev["revision_type"] = revision_type
    # action must also be valid — use a matching one that is in the allowed set
    rev["action"] = "demote_to_scene_beat"
    ok, errors = validate_manifest_revision(rev)
    assert ok is True, f"Expected valid for revision_type={revision_type!r}, got errors: {errors}"


# ── 7. All four actions valid ─────────────────────────────────────────────────

@pytest.mark.parametrize("action", [
    "demote_to_scene_beat",
    "promote_to_canonical",
    "merge_with_predecessor",
    "reclassify_to_background",
])
def test_all_four_actions_valid(action):
    rev = _valid_demote()
    rev["action"] = action
    ok, errors = validate_manifest_revision(rev)
    assert ok is True, f"Expected valid for action={action!r}, got errors: {errors}"
