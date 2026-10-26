from app.security.policies import ALLOWED_TOOL_NAMES
from app.tools.builtin.text_tools import EXTENDED_ACTIONS
from app.tools.registry import get_tool, list_tools


def test_every_extended_action_is_registered_and_allowlisted():
    names = {item["name"] for item in list_tools()}
    assert EXTENDED_ACTIONS <= names
    assert EXTENDED_ACTIONS <= ALLOWED_TOOL_NAMES
    assert all(get_tool(name) is not None for name in EXTENDED_ACTIONS)


def test_extended_tools_execute_with_fixed_registry_action():
    result = get_tool("count_characters")({"action": "hash_text", "input": "one two"})
    assert result["characters_including_spaces"] == 7
    assert result["words"] == 2
    assert "digest" not in result


def test_invalid_extended_tool_input_is_reported_as_validation_error():
    import pytest

    with pytest.raises(ValueError, match="valid base64"):
        get_tool("base64_decode")({"input": "not base64!"})


def test_calculator_remains_registered():
    assert get_tool("calculator") is not None
