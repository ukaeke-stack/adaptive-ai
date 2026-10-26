"""Regression tests for the central deterministic tool registry.

These tests verify registration and dispatch boundaries. They do not claim that
all 500 catalogue requirements or every third-party/device integration is done.
"""
from app.tools.builtin.text_tools import EXTENDED_ACTIONS
from app.tools.registry import get_tool, list_tools


def test_every_extended_action_has_a_callable_registry_handler():
    registered = {item["name"] for item in list_tools()}
    assert EXTENDED_ACTIONS <= registered
    for name in EXTENDED_ACTIONS:
        handler = get_tool(name)
        assert callable(handler), f"{name} has no executable registry handler"


def test_registry_handler_pins_action_name_instead_of_trusting_arguments():
    handler = get_tool("count_characters")
    result = handler({"input": "one two", "action": "unsupported_goal"})
    assert result["status"] == "succeeded"
    assert result["words"] == 2
    assert "blocked" not in result


def test_unknown_and_unallowlisted_tools_are_not_executable():
    assert get_tool("not_a_real_tool") is None
    assert get_tool("__import__") is None


def test_registry_metadata_only_lists_callable_handlers():
    items = list_tools()
    assert items
    assert len({item["name"] for item in items}) == len(items)
    for item in items:
        assert item["status"] == "implemented"
        assert callable(get_tool(item["name"]))
