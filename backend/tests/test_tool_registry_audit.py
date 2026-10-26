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

def test_every_declared_extended_action_reaches_a_result_without_uncaught_errors():
    from app.tools.builtin.text_tools import execute_extended

    common_arguments = {
        "input": "Sample text 42, https://example.com and test@example.com",
        "second_input": "Other sample text 43",
        "number": 2,
        "amount": 100,
        "rate": 5,
        "years": 2,
        "months": 12,
        "from_unit": "km",
        "to_unit": "mi",
        "mode": "lower",
        "algorithm": "sha256",
        "pattern": "sample",
        "width": 80,
        "chunk_size": 100,
        "limit": 10,
        "tabsize": 4,
        "prefix": "> ",
        "suffix": " !",
        "separator": ", ",
        "column": "name",
        "new_name": "renamed",
        "columns": ["name"],
        "key": "name",
        "equals": "sample",
        "path": "name",
        "seconds": 90,
        "old": 10,
        "new": 12,
        "value": 2,
    }
    failures = []
    for name in sorted(EXTENDED_ACTIONS):
        try:
            result = execute_extended({**common_arguments, "action": name})
            if not isinstance(result, dict) or not isinstance(result.get("status"), str):
                failures.append(f"{name}: no structured result")
        except Exception as exc:  # report every action rather than stopping at the first
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "\\n".join(failures)
