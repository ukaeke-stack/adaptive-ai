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

def test_parse_url_separates_query_parameters_and_fragment():
    result = execute_extended({
        "action": "parse_url",
        "input": "https://example.com:8443/path?a=1&a=2&b=hello#section",
    })
    assert result["status"] == "succeeded"
    assert result["scheme"] == "https"
    assert result["host"] == "example.com"
    assert result["port"] == 8443
    assert result["path"] == "/path"
    assert result["query"] == {"a": ["1", "2"], "b": ["hello"]}
    assert result["fragment"] == "section"


def test_convert_units_rejects_infinite_values():
    result = execute_extended({
        "action": "convert_units",
        "input": "",
        "number": "inf",
        "from_unit": "km",
        "to_unit": "mi",
    })
    assert result["status"] == "failed"
    assert "finite" in result["message"].lower()


def test_validate_json_distinguishes_valid_json_root_types():
    result = execute_extended({"action": "validate_json", "input": '[1, true, null]'})
    assert result["status"] == "succeeded"
    assert result["valid"] is True
    assert result["root_type"] == "list"


def test_markdown_link_extraction_preserves_label_and_url():
    result = execute_extended({
        "action": "extract_markdown_links",
        "input": "See [Family Roots](https://example.com/family?q=1) and [Docs](http://example.org/docs).",
    })
    assert result["status"] == "succeeded"
    assert result["links"] == [
        {"text": "Family Roots", "url": "https://example.com/family?q=1"},
        {"text": "Docs", "url": "http://example.org/docs"},
    ]


def test_hash_text_sha256_is_deterministic():
    result = execute_extended({"action": "hash_text", "input": "abc"})
    assert result["status"] == "succeeded"
    assert result["algorithm"] == "sha256"
    assert result["digest"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

