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

def test_milliseconds_duration_uses_milliseconds_argument():
    from app.tools.builtin.text_tools import execute_extended

    result = execute_extended({
        "action": "convert_milliseconds_to_duration",
        "input": "",
        "milliseconds": 1500,
    })
    assert result["status"] == "succeeded"
    assert result["seconds"] == 1
    assert result["formatted"] == "0d 0h 0m 1s"


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
        "milliseconds": 1500,
        "old": 10,
        "new": 12,
        "value": 2,
    }
    failures = []
    for name in sorted(EXTENDED_ACTIONS):
        try:
            action_input = common_arguments["input"]
            if name.startswith("csv_") or name == "csv_to_tsv":
                action_input = "name,age\\nAlice,30\\nBob,40\\n,\\n"
            elif name == "tsv_to_csv":
                action_input = "name\\tage\\nAlice\\t30\\nBob\\t40\\n"
            elif name.startswith("json_") or name in {"json_minify", "json_sort_keys", "json_to_xml_preview"}:
                action_input = '{"name":"Alice","age":30,"items":[1,2]}'
                if any(token in name for token in ("array", "jsonl", "to_csv", "to_markdown_table")):
                    action_input = '[{"name":"Alice","age":30},{"name":"Bob","age":40}]'
            elif name == "markdown_table_to_csv" or name == "extract_markdown_tables":
                action_input = "| name | age |\\n| --- | --- |\\n| Alice | 30 |"
            elif name in {"convert_percentage_decimal", "convert_decimal_percentage", "convert_fraction_decimal", "decimal_to_fraction", "fraction_to_decimal", "format_bytes", "format_number_commas", "parse_number_locale", "convert_milliseconds_to_duration", "convert_milliseconds_to_seconds", "convert_minutes_to_seconds", "convert_seconds_to_minutes", "calculate_square_root", "calculate_power", "calculate_logarithm", "calculate_permutation", "calculate_combination", "calculate_compound_rate", "calculate_sales_tax", "calculate_average_speed", "calculate_distance", "calculate_time"}:
                action_input = "1/2" if name == "fraction_to_decimal" else ("0.5" if name in {"convert_decimal_percentage", "decimal_to_fraction", "format_bytes", "format_number_commas", "parse_number_locale"} else ("50%" if name in {"convert_percentage_decimal", "convert_fraction_decimal"} else "1500"))
            elif name == "extract_env_variable_names":
                action_input = "export TEST_KEY=hello\\nOTHER_VALUE=world"
            elif name == "extract_functions":
                action_input = "def example():\\n    return 1\\nfunction sample() {}"
            elif name == "extract_bracketed_text":
                action_input = "value [inside] and (outside)"
            elif name == "extract_quoted_text":
                action_input = 'value "quoted" and \'single\''
            elif name == "extract_emojis":
                action_input = "hello 😀 🌍"
            elif name == "extract_ip_addresses":
                action_input = "IPs 192.168.1.1 and 2001:db8::1"
            elif name == "extract_list_items":
                action_input = "- one\\n2. two"
            elif name == "extract_markdown_tables":
                action_input = "| name | age |\\n| --- | --- |\\n| Alice | 30 |"
            elif name == "find_email_domains":
                action_input = "person@example.com other@sample.org"
            elif name == "extract_urls_domains":
                action_input = "https://example.com/path and https://sample.org"
            result = execute_extended({**common_arguments, "input": action_input, "action": name})
            if not isinstance(result, dict) or not isinstance(result.get("status"), str):
                failures.append(f"{name}: no structured result")
        except Exception as exc:  # report every action rather than stopping at the first
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "\\n".join(failures)
