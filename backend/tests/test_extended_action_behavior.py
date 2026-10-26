"""Focused behavior tests for representative registered actions.

These tests supplement the all-action dispatch smoke test with exact output
assertions and malformed-input checks. They do not imply device integrations
or the unrecovered 500-item catalogue have been verified.
"""
import pytest

from app.tools.builtin.text_tools import execute_extended
from app.tools.registry import get_tool


def test_base64_round_trip_preserves_unicode():
    encoded = execute_extended({"action": "base64_encode", "input": "Lagos — Abuja 🌍"})
    assert encoded == {
        "status": "succeeded",
        "encoding": "base64",
        "text": "TGFnb3Mg4oCUIEFidWphIPCfjI0=",
    }

    decoded = execute_extended({"action": "base64_decode", "input": encoded["text"]})
    assert decoded["status"] == "succeeded"
    assert decoded["text"] == "Lagos — Abuja 🌍"


def test_base64_decode_rejects_invalid_data():
    result = execute_extended({"action": "base64_decode", "input": "not valid base64!"})
    assert result["status"] == "failed"
    assert isinstance(result.get("message"), str) and result["message"]


def test_count_characters_reports_whitespace_and_words_separately():
    result = execute_extended({"action": "count_characters", "input": "one two\nthree"})
    assert result["status"] == "succeeded"
    assert result["characters_including_spaces"] == 13
    assert result["characters_excluding_whitespace"] == 11
    assert result["lines"] == 2
    assert result["words"] == 3


def test_csv_unique_column_handles_duplicate_values_and_quoted_commas():
    result = execute_extended({
        "action": "csv_column_unique",
        "input": 'name,city\nAda,"Lagos, Mainland"\nTola,Abuja\nSam,"Lagos, Mainland"',
        "column": "city",
    })
    assert result["status"] == "succeeded"
    assert result["values"] == ["Lagos, Mainland", "Abuja"]


def test_registry_adapter_does_not_allow_action_override():
    handler = get_tool("count_characters")
    assert handler is not None
    result = handler({"input": "hello world", "action": "base64_decode"})
    assert result["status"] == "succeeded"
    assert result["words"] == 2
    assert "text" not in result


def test_registry_adapter_surfaces_invalid_action_input_as_failure():
    handler = get_tool("base64_decode")
    assert handler is not None
    with pytest.raises(ValueError, match="Invalid base64|base64"):
        handler({"input": "%%%not-base64%%%"})
