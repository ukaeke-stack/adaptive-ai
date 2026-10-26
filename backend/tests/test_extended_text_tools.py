import pytest

from app.api.agent_runtime import _execute_step, _plan


def run(action, text, **kwargs):
    return _execute_step({"action": action, "input": text, **kwargs})


def test_extended_text_tools_are_plannable():
    assert _plan("Count characters in this text", {"text": "abc"})[0]["action"] == "count_characters"
    assert _plan("Extract URLs from this text", {"text": "https://example.com"})[0]["action"] == "extract_urls"
    assert _plan("Format JSON", {"text": "{\"a\":1}"})[0]["action"] == "format_json"


def test_count_characters_and_reading_time():
    result = run("count_characters", "one two\n")
    assert result["status"] == "succeeded"
    assert result["characters_including_spaces"] == 8
    assert result["characters_excluding_whitespace"] == 6
    assert run("estimate_reading_time", "one two")["word_count"] == 2


def test_line_transformations_preserve_order_or_sort():
    assert run("deduplicate_lines", "b\na\nb")["lines"] == ["b", "a"]
    assert run("sort_lines", "z\nA")["lines"] == ["A", "z"]
    assert run("reverse_lines", "a\nb")["lines"] == ["b", "a"]
    assert run("normalize_whitespace", "  too   much\n whitespace  ")["text"] == "too much whitespace"


def test_case_conversion_slug_and_frequency():
    assert run("convert_case", "hello there", mode="upper")["text"] == "HELLO THERE"
    assert run("slugify", "Hello, World!")["slug"] == "hello-world"
    assert run("word_frequency", "apple apple banana")["top_words"][0] == {"word": "apple", "count": 2}


def test_json_validation_and_formatting():
    assert run("validate_json", '{"a": 1}')["valid"] is True
    assert run("validate_json", "{bad")["valid"] is False
    assert '"a": 1' in run("format_json", '{"a":1}')["json"]


def test_csv_summary_and_markdown():
    result = run("summarize_csv", "name,age\nAda,36\nGrace,85")
    assert result["row_count"] == 2
    table = run("csv_to_markdown", "name,age\nAda,36")["markdown_table"]
    assert "| name | age |" in table
    assert "| Ada | 36 |" in table


def test_extraction_replace_hash_and_safe_urls():
    assert run("extract_urls", "go https://example.com/test).")["urls"] == ["https://example.com/test"]
    assert run("extract_headings", "# Heading\nbody")["headings"] == [{"level": 1, "text": "Heading"}]
    assert run("replace_text", "a cat", find="cat", replacement="dog")["text"] == "a dog"
    assert len(run("hash_text", "hello")["digest"]) == 64
    assert run("extract_hashtags", "#Norah and #AI")["hashtags"] == ["#Norah", "#AI"]
    assert run("extract_mentions", "hi @norah @user.name")["mentions"] == ["@norah", "@user.name"]
    assert run("extract_numbers", "values 12 and 3.5")["numbers"] == ["12", "3.5"]


def test_extended_tools_reject_empty_and_oversized_text():
    assert run("count_characters", "  ")["status"] == "needs_input"
    with pytest.raises(ValueError):
        from app.tools.builtin.text_tools import execute_extended
        execute_extended({"action": "count_characters", "input": "x" * 120001})


def test_unknown_extended_action_does_not_claim_success():
    from app.tools.builtin.text_tools import execute_extended
    assert execute_extended({"action": "send_email", "input": "Hello"}) is None
