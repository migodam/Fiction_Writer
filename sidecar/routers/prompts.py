"""Prompts router — exposes sidecar prompt text to the frontend.

GET /prompts/list → returns all W0–W7 prompt names and their base text,
grouped by workflow ID. The frontend uses this to populate the Settings >
Prompts tab so users can read the base prompt and optionally set a
user instruction slot.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def _safe_import_prompts(module_name: str, *var_names: str) -> list[dict]:
    """Import a prompt module and return a list of {name, text} dicts."""
    try:
        import importlib
        mod = importlib.import_module(f"sidecar.prompts.{module_name}")
        entries = []
        for name in var_names:
            text = getattr(mod, name, "")
            entries.append({"name": name, "text": str(text)})
        return entries
    except Exception as exc:
        return [{"name": "error", "text": str(exc)}]


@router.get("/list")
async def list_prompts() -> dict:
    """Return all agent-flow prompts grouped by workflow."""
    return {
        "W0": _safe_import_prompts(
            "w0_prompts",
            "W0_PARSE_GOAL",
            "W0_EVALUATE_RESULT",
        ),
        "W1": _safe_import_prompts(
            "w1_prompts",
            "W1_EXTRACT_CHARACTERS",
            "W1_EXTRACT_EVENTS",
            "W1_EXTRACT_WORLD",
            "W1_EXTRACT_CHARACTERS_DEEP",
            "W1_EXTRACT_EVENTS_DEEP",
            "W1_EXTRACT_WORLD_DEEP",
            "W1_EXTRACT_RELATIONSHIPS_CHUNK",
            "W1_EXTRACT_SCENE_SUMMARIES",
            "W1_SYNTHESIZE_RELATIONSHIPS",
            "W1_CLASSIFY_CHARACTER_TAGS",
            "W1_INFER_WORLD_SETTINGS",
        ),
        "W2": _safe_import_prompts(
            "w2_prompts",
            "W2_EXTRACT_FROM_CHAPTER",
        ),
        "W3": _safe_import_prompts(
            "w3_prompts",
            "W3_GENERATE_DIRECT",
            "W3_GENERATE_OPTIONS",
            "W3_EXPAND_SELECTED",
        ),
        "W4": _safe_import_prompts(
            "w4_prompts",
            "W4_TIMELINE_CHECK",
            "W4_CHARACTER_CHECK",
            "W4_WORLD_RULE_CHECK",
            "W4_ITEM_TRACKER",
        ),
        "W5": _safe_import_prompts(
            "w5_prompts",
            "W5_SCENARIO_ENGINE",
            "W5_CHARACTER_ENGINE",
            "W5_AUTHOR_ENGINE",
            "W5_READER_ENGINE",
            "W5_LOGIC_ENGINE",
        ),
        "W6": _safe_import_prompts(
            "w6_prompts",
            "W6_READ_AS_PERSONA",
            "W6_GENERATE_FEEDBACK",
        ),
        "W7": _safe_import_prompts(
            "w7_prompts",
            "W7_EXTRACT_STYLE",
            "W7_EXTRACT_VOCABULARY",
            "W7_EXTRACT_STRUCTURE",
            "W7_EXTRACT_KNOWLEDGE",
        ),
    }
