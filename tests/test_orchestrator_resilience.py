import pytest
from src.ai.orchestrator import safe_parse_json, validate_planner_output

def test_safe_parse_json_with_markdown():
    raw = """Here is the result:
```json
{"key": "value"}
```
Hope this helps!"""
    obj, err = safe_parse_json(raw)
    assert obj == {"key": "value"}
    assert err is None

def test_safe_parse_json_invalid():
    raw = "not a json at all"
    obj, err = safe_parse_json(raw)
    assert obj is None
    assert "No JSON structure found" in err

def test_validate_planner_output_empty():
    # Test normalization of empty dict
    ok, missing, normalized = validate_planner_output({})
    assert ok is False # No steps
    assert len(missing) == 5
    assert "user_output" in normalized
    assert normalized["user_output"]["content_markdown"] == ""

def test_validate_planner_output_partial():
    obj = {
        "user_output": {"content_markdown": "hello"},
        "modification_plan": {"steps": [{"action": "test"}]}
    }
    ok, missing, normalized = validate_planner_output(obj)
    assert ok is True
    assert "classification" in missing
    assert normalized["user_output"]["content_markdown"] == "hello"
    assert "memory_change_proposals" in normalized
