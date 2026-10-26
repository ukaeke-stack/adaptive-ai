"""Deterministic, bounded local tools for Norah's agent runtime.

These tools process user-supplied data only. They do not access accounts, the network,
or the device, and they never execute user-provided code.
"""
from __future__ import annotations

import base64
import csv
import difflib
import hashlib
import io
from html.parser import HTMLParser
import json
import math
import re
import unicodedata
import textwrap
from collections import Counter
from urllib.parse import parse_qs, urlparse

EXTENDED_ACTIONS = {
    "count_characters", "estimate_reading_time", "word_frequency",
    "deduplicate_lines", "sort_lines", "convert_case", "slugify",
    "extract_urls", "extract_headings", "validate_json", "format_json",
    "summarize_csv", "csv_to_markdown", "replace_text", "hash_text",
    "extract_numbers", "extract_hashtags", "extract_mentions",
    "reverse_lines", "trim_lines", "normalize_whitespace", "count_lines",
    "extract_sentences", "redact_sensitive_data", "strip_html", "compare_texts",
    "split_text", "base64_encode", "base64_decode", "parse_url",
    "extract_markdown_links", "generate_checklist", "wrap_text", "convert_units",
}

MAX_TEXT = 120_000
MAX_ROWS = 5_000
MAX_ITEMS = 500
STOP_WORDS = {
    "the", "and", "for", "that", "with", "this", "from", "you", "your",
    "are", "was", "were", "have", "has", "had", "but", "not", "all",
    "can", "will", "would", "could", "should", "into", "about", "their",
    "they", "them", "then", "than", "there", "here", "its", "our", "out",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(step: dict) -> str:
    value = step.get("input", "")
    if not isinstance(value, str):
        raise ValueError("Input must be text.")
    if len(value) > MAX_TEXT:
        raise ValueError(f"Text is too large; maximum is {MAX_TEXT} characters.")
    return value


def execute_extended(step: dict) -> dict | None:
    """Execute an allowlisted extended action; return None for unknown actions."""
    action = step.get("action")
    if action not in EXTENDED_ACTIONS:
        return None

    value = "" if action == "convert_units" else _text(step)
    if action != "convert_units" and not value.strip():
        return {"status": "needs_input", "message": "Add text in the task context before running this step."}
    if action == "count_characters":
        return {"status": "succeeded", "characters_including_spaces": len(value),
                "characters_excluding_whitespace": sum(not c.isspace() for c in value),
                "lines": len(value.splitlines()), "words": len(re.findall(r"\S+", value))}
    if action == "estimate_reading_time":
        words = len(re.findall(r"\S+", value))
        return {"status": "succeeded", "word_count": words,
                "estimated_minutes_at_200_wpm": round(words / 200, 2),
                "note": "Estimate only; actual reading speed varies."}
    if action == "word_frequency":
        words = re.findall(r"[\w’'-]+", value.casefold())
        counts = Counter(w.strip("’'-") for w in words if len(w.strip("’'-")) > 1)
        counts = Counter({k: v for k, v in counts.items() if k and k not in STOP_WORDS})
        return {"status": "succeeded", "top_words": [{"word": w, "count": n} for w, n in counts.most_common(50)]}
    if action == "count_lines":
        lines = value.splitlines()
        return {"status": "succeeded", "line_count": len(lines),
                "non_empty_lines": sum(bool(line.strip()) for line in lines),
                "blank_lines": sum(not line.strip() for line in lines)}
    if action == "extract_sentences":
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", value.strip()) if item.strip()]
        return {"status": "succeeded", "sentences": sentences[:MAX_ITEMS], "sentence_count": len(sentences)}
    if action == "redact_sensitive_data":
        redacted = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", value, flags=re.I)
        redacted = re.sub(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)", "[REDACTED_PHONE]", redacted)
        redacted = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_NUMBER]", redacted)
        return {"status": "succeeded", "text": redacted, "note": "Pattern-based redaction can miss or over-redact data; review before sharing."}
    if action == "strip_html":
        parser = _HTMLTextExtractor()
        parser.feed(value)
        parser.close()
        return {"status": "succeeded", "text": re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:MAX_TEXT]}
    if action == "compare_texts":
        other = step.get("second_input", "")
        if not isinstance(other, str) or not other.strip():
            return {"status": "needs_input", "message": "Provide second_input to compare both texts."}
        if len(other) > MAX_TEXT:
            return {"status": "failed", "message": f"Second text exceeds {MAX_TEXT} characters."}
        left, right = value.splitlines(), other.splitlines()
        return {"status": "succeeded", "similarity_percent": round(difflib.SequenceMatcher(None, value, other).ratio() * 100, 2),
                "only_in_first": [line for line in left if line not in right][:MAX_ITEMS],
                "only_in_second": [line for line in right if line not in left][:MAX_ITEMS]}
    if action == "split_text":
        try:
            chunk_size = int(step.get("chunk_size", 2000))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "chunk_size must be an integer from 100 to 12000."}
        if not 100 <= chunk_size <= 12000:
            return {"status": "failed", "message": "chunk_size must be an integer from 100 to 12000."}
        chunks = [value[i:i + chunk_size] for i in range(0, len(value), chunk_size)]
        return {"status": "succeeded", "chunks": chunks[:100], "chunk_count": len(chunks), "truncated": len(chunks) > 100}
    if action == "base64_encode":
        return {"status": "succeeded", "encoding": "base64", "text": base64.b64encode(value.encode("utf-8")).decode("ascii")}
    if action == "base64_decode":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            return {"status": "failed", "message": "Input must be valid base64 containing UTF-8 text."}
        return {"status": "succeeded", "text": decoded[:MAX_TEXT], "truncated": len(decoded) > MAX_TEXT}
    if action == "parse_url":
        try:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("URL must use http:// or https:// and include a host.")
            port = parsed.port
        except ValueError as exc:
            return {"status": "failed", "message": str(exc)}
        return {"status": "succeeded", "scheme": parsed.scheme, "host": parsed.hostname, "port": port,
                "path": parsed.path, "query": parse_qs(parsed.query), "fragment": parsed.fragment}
    if action == "extract_markdown_links":
        links = [{"text": label.strip(), "url": url.strip()} for label, url in
                 re.findall(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", value)]
        return {"status": "succeeded", "links": links[:MAX_ITEMS]}
    if action == "generate_checklist":
        items = [line.strip(" -*\t") for line in value.splitlines() if line.strip()]
        return {"status": "succeeded", "markdown": "\n".join(f"- [ ] {item}" for item in items[:MAX_ITEMS]),
                "item_count": len(items), "truncated": len(items) > MAX_ITEMS}
    if action == "wrap_text":
        try:
            width = int(step.get("width", 80))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "width must be an integer from 20 to 200."}
        if not 20 <= width <= 200:
            return {"status": "failed", "message": "width must be an integer from 20 to 200."}
        return {"status": "succeeded", "text": textwrap.fill(value, width=width)}
    if action == "convert_units":
        source, target = step.get("from_unit"), step.get("to_unit")
        factors = {
            ("km", "mi"): 0.621371, ("mi", "km"): 1.609344,
            ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
            ("cm", "in"): 0.393701, ("in", "cm"): 2.54,
            ("kg", "lb"): 2.204623, ("lb", "kg"): 0.45359237,
            ("g", "oz"): 0.035274, ("oz", "g"): 28.349523125,
            ("l", "gal_us"): 0.264172, ("gal_us", "l"): 3.785411784,
        }
        try:
            number = float(step.get("number"))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "Provide a numeric number plus from_unit and to_unit."}
        if not math.isfinite(number):
            return {"status": "failed", "message": "Number must be finite."}
        if source == "c" and target == "f":
            result = number * 9 / 5 + 32
        elif source == "f" and target == "c":
            result = (number - 32) * 5 / 9
        elif (source, target) in factors:
            result = number * factors[(source, target)]
        elif source == target and source in {"km", "mi", "m", "ft", "cm", "in", "kg", "lb", "g", "oz", "l", "gal_us", "c", "f"}:
            result = number
        else:
            return {"status": "failed", "message": "Unsupported unit pair. Use km/mi, m/ft, cm/in, kg/lb, g/oz, l/gal_us, or c/f."}
        return {"status": "succeeded", "input": number, "from_unit": source, "to_unit": target, "result": round(result, 8)}
    if action == "normalize_whitespace":
        normalized = re.sub(r"\s+", " ", value).strip()
        return {"status": "succeeded", "text": normalized}
    if action in {"deduplicate_lines", "sort_lines", "reverse_lines", "trim_lines"}:
        lines = value.splitlines()
        if action == "deduplicate_lines":
            lines = list(dict.fromkeys(line for line in lines))
        elif action == "sort_lines":
            lines = sorted(lines, key=str.casefold)
        elif action == "reverse_lines":
            lines = list(reversed(lines))
        else:
            lines = [line.strip() for line in lines]
        return {"status": "succeeded", "lines": lines[:MAX_ITEMS], "line_count": len(lines),
                "truncated": len(lines) > MAX_ITEMS}
    if action == "convert_case":
        mode = step.get("mode", "lower")
        if mode == "upper":
            result = value.upper()
        elif mode == "title":
            result = value.title()
        elif mode == "sentence":
            result = value[:1].upper() + value[1:].lower()
        elif mode == "lower":
            result = value.lower()
        else:
            return {"status": "failed", "message": "mode must be lower, upper, title, or sentence."}
        return {"status": "succeeded", "text": result}
    if action == "slugify":
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
        return {"status": "succeeded", "slug": re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:240]}
    if action == "extract_urls":
        candidates = re.findall(r"https?://[^\s<>\"']+", value, re.I)
        urls = []
        for candidate in candidates:
            candidate = candidate.rstrip(r".,;:!?)\]")
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.hostname and candidate not in urls:
                urls.append(candidate)
        return {"status": "succeeded", "urls": urls[:MAX_ITEMS]}
    if action == "extract_headings":
        headings = []
        for line in value.splitlines():
            match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if match:
                headings.append({"level": len(match.group(1)), "text": match.group(2)})
        return {"status": "succeeded", "headings": headings[:MAX_ITEMS]}
    if action in {"validate_json", "format_json"}:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            return {"status": "failed", "valid": False, "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"}
        if action == "validate_json":
            return {"status": "succeeded", "valid": True, "root_type": type(parsed).__name__}
        return {"status": "succeeded", "valid": True, "json": json.dumps(parsed, ensure_ascii=False, indent=2)[:MAX_TEXT]}
    if action in {"summarize_csv", "csv_to_markdown"}:
        try:
            reader = csv.DictReader(io.StringIO(value))
            headers = reader.fieldnames or []
            if not headers:
                return {"status": "failed", "message": "CSV must include a header row."}
            rows = []
            for index, row in enumerate(reader):
                if index >= MAX_ROWS:
                    break
                rows.append(row)
        except csv.Error as exc:
            return {"status": "failed", "message": f"CSV parsing failed: {exc}"}
        if action == "summarize_csv":
            return {"status": "succeeded", "columns": headers, "row_count": len(rows),
                    "sample_rows": rows[:5], "truncated": len(rows) >= MAX_ROWS}
        def cell(item):
            return str(item or "").replace("|", "\\|").replace("\n", " ")
        table = "| " + " | ".join(cell(h) for h in headers) + " |\n"
        table += "| " + " | ".join("---" for _ in headers) + " |\n"
        table += "".join("| " + " | ".join(cell(row.get(h)) for h in headers) + " |\n" for row in rows[:200])
        return {"status": "succeeded", "markdown_table": table[:MAX_TEXT], "rows_included": min(len(rows), 200)}
    if action == "replace_text":
        find = step.get("find", "")
        replacement = step.get("replacement", "")
        if not isinstance(find, str) or not find:
            return {"status": "failed", "message": "Provide a non-empty literal find value."}
        if not isinstance(replacement, str) or len(replacement) > 4000:
            return {"status": "failed", "message": "Replacement must be text up to 4000 characters."}
        return {"status": "succeeded", "text": value.replace(find, replacement)[:MAX_TEXT],
                "replacements": value.count(find)}
    if action == "hash_text":
        algorithm = step.get("algorithm", "sha256")
        if algorithm not in {"sha256", "sha512", "sha1", "md5"}:
            return {"status": "failed", "message": "Supported digest algorithms: sha256, sha512, sha1, md5."}
        digest = hashlib.new(algorithm, value.encode("utf-8")).hexdigest()
        return {"status": "succeeded", "algorithm": algorithm, "digest": digest}
    if action == "extract_numbers":
        numbers = re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?![\w])", value)
        return {"status": "succeeded", "numbers": list(dict.fromkeys(numbers))[:MAX_ITEMS]}
    if action == "extract_hashtags":
        return {"status": "succeeded", "hashtags": list(dict.fromkeys(re.findall(r"(?<!\w)#[\w]+", value)))[:MAX_ITEMS]}
    if action == "extract_mentions":
        return {"status": "succeeded", "mentions": list(dict.fromkeys(re.findall(r"(?<!\w)@[A-Za-z0-9_.]{1,64}", value)))[:MAX_ITEMS]}
    return None


# Additional bounded productivity actions.
# These actions operate only on explicitly supplied content and never access external accounts.
EXTENDED_ACTIONS.update({
    "extract_emails", "extract_phone_numbers", "extract_ipv4_addresses",
    "extract_file_paths", "extract_code_blocks", "extract_markdown_tables",
    "extract_html_links", "extract_html_images", "markdown_to_plain_text",
    "json_to_yaml_preview", "count_words_by_line", "paragraph_count",
    "find_duplicate_words", "find_long_words", "alphabetize_words",
    "remove_empty_lines", "number_lines", "indent_text", "dedent_text",
    "truncate_text", "mask_text", "extract_quoted_text", "extract_bracketed_text",
    "extract_dates_iso", "extract_currency_amounts", "extract_emojis",
    "validate_email_list", "validate_ipv4", "validate_uuid",
    "generate_table_of_contents", "markdown_to_html_safe", "html_escape",
    "url_encode_text", "url_decode_text", "unicode_normalize",
    "json_to_csv", "csv_column_stats", "csv_filter_rows",
    "csv_sort_rows", "csv_deduplicate_rows", "csv_select_columns",
    "diff_summary", "text_statistics", "extract_initials",
    "make_acronym", "expand_tabs", "remove_control_characters",
    "normalize_newlines", "count_occurrences", "extract_lines_matching",
    "exclude_lines_matching", "prefix_lines", "suffix_lines",
    "join_lines", "split_words", "reverse_words", "shuffle_preview",
})
