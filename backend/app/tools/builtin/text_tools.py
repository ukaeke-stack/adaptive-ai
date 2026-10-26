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

    ARGUMENT_ONLY_ACTIONS = {
        "convert_units", "generate_uuid", "generate_timestamp", "calculate_percentage",
        "calculate_discount", "calculate_tax", "calculate_simple_interest",
        "calculate_compound_interest", "calculate_loan_payment", "calculate_square_root",
        "calculate_power", "calculate_logarithm", "calculate_permutation",
        "calculate_combination", "calculate_compound_rate", "calculate_sales_tax",
        "calculate_average_speed", "calculate_distance", "calculate_time",
        "calculate_weighted_average", "calculate_geometric_mean", "calculate_harmonic_mean",
        "calculate_z_scores", "calculate_percentile", "calculate_factorial",
        "calculate_fibonacci", "prime_factors", "calculate_gcd", "calculate_lcm",
        "is_prime", "factorize_integer", "convert_number_base", "days_in_month",
        "is_leap_year", "add_days", "add_months", "date_difference",
        "business_days_between", "add_business_days", "format_datetime",
        "convert_timezone", "age_from_date", "generate_password", "format_duration",
        "convert_milliseconds_to_duration", "format_currency_preview",
    }
    value = "" if action in ARGUMENT_ONLY_ACTIONS else _text(step)
    if action not in ARGUMENT_ONLY_ACTIONS and not value.strip():
        return {"status": "needs_input", "message": "Add text in the task context before running this step."}
    # Keep the original, reviewed core implementations here. All additional catalog
    # actions are dispatched to the separate bounded executor so they cannot be
    # accidentally shadowed by legacy experimental branches below.
    CORE_ACTIONS = {
        "count_characters", "estimate_reading_time", "word_frequency", "deduplicate_lines",
        "sort_lines", "convert_case", "slugify", "extract_urls", "extract_headings",
        "validate_json", "summarize_csv", "replace_text", "hash_text", "extract_numbers",
        "extract_hashtags", "extract_mentions", "reverse_lines", "normalize_whitespace",
        "count_lines", "extract_sentences", "redact_sensitive_data", "strip_html",
        "compare_texts", "split_text", "base64_encode", "base64_decode", "parse_url",
        "extract_markdown_links", "generate_checklist", "wrap_text", "convert_units",
    }
    if action not in CORE_ACTIONS:
        from app.tools.builtin.extra_actions import execute_extra
        return execute_extra(action, step, value)
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

    # Additional deterministic productivity helpers. All input and output are bounded.
    if action == "extract_emails":
        return {"status": "succeeded", "emails": list(dict.fromkeys(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", value, re.I)))[:MAX_ITEMS]}
    if action == "extract_phone_numbers":
        matches = re.findall(r"(?<!\\w)\\+?\\d[\\d ().-]{6,}\\d(?!\\w)", value)
        phones = list(dict.fromkeys(" ".join(x.split()) for x in matches if 7 <= sum(c.isdigit() for c in x) <= 15))
        return {"status": "succeeded", "phone_numbers": phones[:MAX_ITEMS]}
    if action == "extract_ipv4_addresses":
        candidates = re.findall(r"(?<![\\w.])(?:\\d{1,3}\\.){3}\\d{1,3}(?![\\w.])", value)
        valid = []
        for candidate in candidates:
            parts = candidate.split(".")
            if all(0 <= int(part) <= 255 for part in parts):
                valid.append(candidate)
        return {"status": "succeeded", "addresses": list(dict.fromkeys(valid))[:MAX_ITEMS]}
    if action == "extract_file_paths":
        paths = re.findall(r"(?<!\\w)(?:/[\\w. -]+)+/?|[A-Za-z]:\\\\(?:[^\\\\<>:\"|?*]+\\\\?)+", value)
        return {"status": "succeeded", "paths": list(dict.fromkeys(paths))[:MAX_ITEMS]}
    if action == "extract_code_blocks":
        blocks = re.findall(r"```[^\\n]*\\n(.*?)```", value, re.S)
        return {"status": "succeeded", "code_blocks": blocks[:100], "count": len(blocks)}
    if action == "extract_markdown_tables":
        tables, current = [], []
        for line in value.splitlines():
            if line.strip().startswith("|") and line.strip().endswith("|"):
                current.append(line)
            elif current:
                tables.append("\\n".join(current)); current = []
        if current: tables.append("\\n".join(current))
        return {"status": "succeeded", "tables": tables[:50], "count": len(tables)}
    if action == "extract_html_links":
        links = re.findall(r"(?is)<a\\b[^>]*href\\s*=\\s*[\"']?([^\"'\\s>]+)[^\"']*[\"']?[^>]*>(.*?)</a\\s*>", value)
        return {"status": "succeeded", "links": [{"url": u[:2000], "text": re.sub(r"<[^>]*>", "", t).strip()[:500]} for u,t in links[:MAX_ITEMS]]}
    if action == "extract_html_images":
        images = re.findall(r"(?is)<img\\b[^>]*?src\\s*=\\s*[\"']([^\"']+)[\"'][^>]*>", value)
        return {"status": "succeeded", "images": list(dict.fromkeys(images))[:MAX_ITEMS]}
    if action == "markdown_to_plain_text":
        plain = re.sub(r"!?(\\[([^\\]]*)\\])\\([^)]*\\)", lambda m: m.group(2), value)
        plain = re.sub(r"(?m)^\\s{0,3}#{1,6}\\s*", "", plain)
        plain = re.sub(r"(?m)^\\s*[-*+]\\s+", "", plain)
        plain = re.sub(r"[*_~`]", "", plain)
        return {"status": "succeeded", "text": plain[:MAX_TEXT]}
    if action == "json_to_yaml_preview":
        try: obj = json.loads(value)
        except json.JSONDecodeError as exc: return {"status": "failed", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        def yaml_lines(obj, indent=0):
            pad = " " * indent
            if isinstance(obj, dict):
                out = []
                for key, val in list(obj.items())[:MAX_ITEMS]:
                    if isinstance(val, (dict, list)): out.append(f"{pad}{key}:"); out.extend(yaml_lines(val, indent+2))
                    else: out.append(f"{pad}{key}: {json.dumps(val, ensure_ascii=False)}")
                return out
            if isinstance(obj, list):
                out = []
                for val in obj[:MAX_ITEMS]:
                    if isinstance(val, (dict, list)): out.append(f"{pad}-"); out.extend(yaml_lines(val, indent+2))
                    else: out.append(f"{pad}- {json.dumps(val, ensure_ascii=False)}")
                return out
            return [pad + json.dumps(obj, ensure_ascii=False)]
        return {"status": "succeeded", "yaml_preview": "\\n".join(yaml_lines(obj))[:MAX_TEXT], "note": "Preview uses JSON scalar quoting; review before using as production YAML."}
    if action == "count_words_by_line":
        rows = [{"line": i, "words": len(re.findall(r"\\S+", line))} for i,line in enumerate(value.splitlines(), 1)]
        return {"status": "succeeded", "lines": rows[:MAX_ITEMS], "line_count": len(rows)}
    if action == "paragraph_count":
        paragraphs = [p for p in re.split(r"\\n\\s*\\n", value.strip()) if p.strip()]
        return {"status": "succeeded", "paragraph_count": len(paragraphs)}
    if action == "find_duplicate_words":
        words = re.findall(r"[\\w’'-]+", value.casefold())
        counts = Counter(words)
        return {"status": "succeeded", "duplicates": [{"word": w, "count": n} for w,n in counts.items() if n > 1][:MAX_ITEMS]}
    if action == "find_long_words":
        minimum = step.get("minimum_length", 10)
        try: minimum = int(minimum)
        except (TypeError, ValueError): minimum = 10
        if not 2 <= minimum <= 100: return {"status": "failed", "message": "minimum_length must be from 2 to 100."}
        words = re.findall(r"[^\\W\\d_]+", value, re.UNICODE)
        return {"status": "succeeded", "minimum_length": minimum, "words": list(dict.fromkeys(w for w in words if len(w) >= minimum))[:MAX_ITEMS]}
    if action == "alphabetize_words":
        words = re.findall(r"\\S+", value)
        return {"status": "succeeded", "words": sorted(words, key=str.casefold)[:MAX_ITEMS], "count": len(words)}
    if action == "remove_empty_lines":
        lines = [line for line in value.splitlines() if line.strip()]
        return {"status": "succeeded", "text": "\\n".join(lines)[:MAX_TEXT], "removed": len(value.splitlines())-len(lines)}
    if action == "number_lines":
        lines = value.splitlines()
        return {"status": "succeeded", "text": "\\n".join(f"{i}. {line}" for i,line in enumerate(lines,1))[:MAX_TEXT], "line_count": len(lines)}
    if action == "indent_text":
        prefix = step.get("prefix", "    ")
        if not isinstance(prefix, str) or len(prefix) > 40: return {"status": "failed", "message": "prefix must be text up to 40 characters."}
        return {"status": "succeeded", "text": "\\n".join(prefix+line for line in value.splitlines())[:MAX_TEXT]}
    if action == "dedent_text":
        return {"status": "succeeded", "text": textwrap.dedent(value)[:MAX_TEXT]}
    if action == "truncate_text":
        try: limit = int(step.get("limit", 500))
        except (TypeError, ValueError): limit = 500
        if not 1 <= limit <= MAX_TEXT: return {"status": "failed", "message": "limit must be between 1 and 120000."}
        return {"status": "succeeded", "text": value[:limit], "truncated": len(value)>limit, "original_length": len(value)}
    if action == "mask_text":
        try: visible = int(step.get("visible_characters", 4))
        except (TypeError, ValueError): visible = 4
        if not 0 <= visible <= 20: return {"status": "failed", "message": "visible_characters must be between 0 and 20."}
        return {"status": "succeeded", "text": "*"*max(0,len(value)-visible)+value[-visible:] if visible else "*"*len(value)}
    if action == "extract_quoted_text":
        matches = re.findall(r'["“”](.+?)["“”]|[\'‘’](.+?)[\'‘’]', value)
        return {"status": "succeeded", "quoted_text": [(a or b) for a,b in matches][:MAX_ITEMS]}
    if action == "extract_bracketed_text":
        return {"status": "succeeded", "bracketed_text": re.findall(r"\\(([^()]*)\\)|\\[([^\\[\\]]*)\\]|\\{([^{}]*)\\}", value)[:MAX_ITEMS]}
    if action == "extract_dates_iso":
        dates = re.findall(r"\\b\\d{4}-\\d{2}-\\d{2}(?:[T ]\\d{2}:\\d{2}(?::\\d{2})?(?:Z|[+-]\\d{2}:?\\d{2})?)?\\b", value)
        return {"status": "succeeded", "dates": list(dict.fromkeys(dates))[:MAX_ITEMS]}
    if action == "extract_currency_amounts":
        amounts = re.findall(r"(?<!\\w)(?:[$€£₦]|USD|EUR|GBP|NGN)\\s?\\d[\\d,]*(?:\\.\\d{1,2})?", value, re.I)
        return {"status": "succeeded", "amounts": list(dict.fromkeys(amounts))[:MAX_ITEMS], "note": "Pattern extraction only; currency context may be ambiguous."}
    if action == "extract_emojis":
        chars = [c for c in value if ord(c) >= 0x1F000]
        return {"status": "succeeded", "symbols": list(dict.fromkeys(chars))[:MAX_ITEMS]}
    if action == "validate_email_list":
        candidates = [x.strip() for x in value.replace(",", "\\n").splitlines() if x.strip()]
        valid = [x for x in candidates if re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", x, re.I)]
        return {"status": "succeeded", "valid": valid[:MAX_ITEMS], "invalid": [x for x in candidates if x not in valid][:MAX_ITEMS], "valid_count": len(valid), "invalid_count": len(candidates)-len(valid)}
    if action == "validate_ipv4":
        candidate = value.strip()
        parts = candidate.split(".")
        valid = len(parts)==4 and all(p.isdigit() and (p=="0" or not p.startswith("0")) and 0<=int(p)<=255 for p in parts)
        return {"status": "succeeded", "valid": valid, "address": candidate}
    if action == "validate_uuid":
        import uuid
        try: normalized = str(uuid.UUID(value.strip())); valid = True
        except (ValueError, AttributeError, TypeError): normalized = None; valid = False
        return {"status": "succeeded", "valid": valid, "normalized": normalized}
    if action == "generate_table_of_contents":
        headings = [{"level": len(m.group(1)), "title": m.group(2).strip()} for line in value.splitlines() if (m := re.match(r"^\\s{0,3}(#{1,6})\\s+(.+?)\\s*#*\\s*$", line))]
        return {"status": "succeeded", "markdown_toc": "\\n".join("  "*(h["level"]-1)+f"- [{h['title']}](#{re.sub(r'[^a-z0-9 -]', '', h['title'].casefold()).strip().replace(' ', '-')})" for h in headings[:MAX_ITEMS]), "heading_count": len(headings)}
    if action == "markdown_to_html_safe":
        escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped = re.sub(r"(?m)^### (.+)$", r"<h3>\\1</h3>", escaped)
        escaped = re.sub(r"(?m)^## (.+)$", r"<h2>\\1</h2>", escaped)
        escaped = re.sub(r"(?m)^# (.+)$", r"<h1>\\1</h1>", escaped)
        escaped = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", escaped)
        return {"status": "succeeded", "html": escaped.replace("\\n", "<br>")[:MAX_TEXT], "note": "Safe subset conversion; raw HTML is escaped."}
    if action == "html_escape":
        return {"status": "succeeded", "text": value.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#x27;")}
    if action == "url_encode_text":
        from urllib.parse import quote
        return {"status": "succeeded", "text": quote(value, safe="")[:MAX_TEXT]}
    if action == "url_decode_text":
        from urllib.parse import unquote
        return {"status": "succeeded", "text": unquote(value)[:MAX_TEXT]}
    if action == "unicode_normalize":
        form = step.get("form", "NFC")
        if form not in {"NFC", "NFD", "NFKC", "NFKD"}: return {"status": "failed", "message": "form must be NFC, NFD, NFKC, or NFKD."}
        return {"status": "succeeded", "text": unicodedata.normalize(form, value)}
    if action in {"json_to_csv", "csv_column_stats", "csv_filter_rows", "csv_sort_rows", "csv_deduplicate_rows", "csv_select_columns"}:
        try:
            rows_obj = json.loads(value)
            if not isinstance(rows_obj, list) or any(not isinstance(row, dict) for row in rows_obj): raise ValueError()
            fields = list(dict.fromkeys(k for row in rows_obj[:MAX_ROWS] for k in row.keys()))
            rows = rows_obj[:MAX_ROWS]
        except (json.JSONDecodeError, ValueError, TypeError):
            return {"status": "failed", "message": "Input must be a JSON array of objects."}
        if action == "csv_column_stats":
            return {"status": "succeeded", "columns": [{"name": k, "non_empty": sum(row.get(k) not in (None,"") for row in rows), "distinct": len({str(row.get(k)) for row in rows})} for k in fields[:100]], "row_count": len(rows)}
        if action == "csv_filter_rows":
            col, contains = step.get("column"), step.get("contains", "")
            if col not in fields or not isinstance(contains, str): return {"status": "failed", "message": "Provide a valid column and text contains filter."}
            rows = [r for r in rows if contains.casefold() in str(r.get(col, "")).casefold()]
        elif action == "csv_sort_rows":
            col = step.get("column")
            if col not in fields: return {"status": "failed", "message": "Provide a valid sort column."}
            rows = sorted(rows, key=lambda r: str(r.get(col, "")).casefold(), reverse=bool(step.get("descending", False)))
        elif action == "csv_deduplicate_rows":
            seen, unique = set(), []
            for row in rows:
                key = json.dumps(row, sort_keys=True, ensure_ascii=False)
                if key not in seen: seen.add(key); unique.append(row)
            rows = unique
        elif action == "csv_select_columns":
            selected = step.get("columns")
            if not isinstance(selected, list) or not selected or any(c not in fields for c in selected): return {"status": "failed", "message": "columns must be a non-empty list of existing column names."}
            fields = selected
            rows = [{k: row.get(k) for k in fields} for row in rows]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return {"status": "succeeded", "csv": buffer.getvalue()[:MAX_TEXT], "row_count": len(rows), "columns": fields}
    if action == "diff_summary":
        other = step.get("second_input", "")
        if not isinstance(other, str): return {"status": "failed", "message": "second_input must be text."}
        diff = list(difflib.unified_diff(value.splitlines(), other.splitlines(), fromfile="first", tofile="second", lineterm=""))
        return {"status": "succeeded", "diff": "\\n".join(diff[:MAX_ITEMS])[:MAX_TEXT], "added_lines": sum(x.startswith("+") and not x.startswith("+++") for x in diff), "removed_lines": sum(x.startswith("-") and not x.startswith("---") for x in diff)}
    if action == "text_statistics":
        words = re.findall(r"\\S+", value)
        sentences = [x for x in re.split(r"(?<=[.!?])\\s+", value.strip()) if x]
        return {"status": "succeeded", "characters": len(value), "words": len(words), "lines": len(value.splitlines()), "paragraphs": len([p for p in re.split(r"\\n\\s*\\n", value.strip()) if p.strip()]), "sentences": len(sentences), "unique_words": len(set(w.casefold() for w in words))}
    if action == "extract_initials":
        words = re.findall(r"[^\\W\\d_]+", value, re.UNICODE)
        return {"status": "succeeded", "initials": "".join(w[0].upper() for w in words)}
    if action == "make_acronym":
        words = re.findall(r"[^\\W\\d_]+", value, re.UNICODE)
        return {"status": "succeeded", "acronym": "".join(w[0].upper() for w in words), "word_count": len(words)}
    if action == "expand_tabs":
        try: width = int(step.get("tab_size", 4))
        except (TypeError, ValueError): width = 4
        if not 1 <= width <= 16: return {"status": "failed", "message": "tab_size must be from 1 to 16."}
        return {"status": "succeeded", "text": value.expandtabs(width)[:MAX_TEXT]}
    if action == "remove_control_characters":
        cleaned = "".join(c for c in value if c in "\\n\\r\\t" or unicodedata.category(c)[0] != "C")
        return {"status": "succeeded", "text": cleaned[:MAX_TEXT], "removed": len(value)-len(cleaned)}
    if action == "normalize_newlines":
        return {"status": "succeeded", "text": re.sub(r"\\r\\n?|\\n", "\\n", value)[:MAX_TEXT]}
    if action == "count_occurrences":
        needle = step.get("needle", "")
        if not isinstance(needle, str) or not needle: return {"status": "failed", "message": "Provide a non-empty needle."}
        return {"status": "succeeded", "count": value.count(needle), "case_insensitive_count": value.casefold().count(needle.casefold())}
    if action in {"extract_lines_matching", "exclude_lines_matching"}:
        pattern = step.get("pattern", "")
        if not isinstance(pattern, str) or len(pattern) > 200: return {"status": "failed", "message": "Provide a regex pattern up to 200 characters."}
        try: rx = re.compile(pattern, re.I if step.get("ignore_case") else 0)
        except re.error as exc: return {"status": "failed", "message": f"Invalid regular expression: {exc}"}
        lines = [line for line in value.splitlines() if bool(rx.search(line)) == (action == "extract_lines_matching")]
        return {"status": "succeeded", "lines": lines[:MAX_ITEMS], "count": len(lines), "truncated": len(lines)>MAX_ITEMS}
    if action in {"prefix_lines", "suffix_lines"}:
        affix = step.get("affix", "")
        if not isinstance(affix, str) or len(affix) > 200: return {"status": "failed", "message": "affix must be text up to 200 characters."}
        lines = value.splitlines()
        return {"status": "succeeded", "text": "\\n".join((affix+line if action=="prefix_lines" else line+affix) for line in lines)[:MAX_TEXT]}
    if action == "join_lines":
        separator = step.get("separator", ", ")
        if not isinstance(separator, str) or len(separator)>100: return {"status": "failed", "message": "separator must be text up to 100 characters."}
        return {"status": "succeeded", "text": separator.join(value.splitlines())[:MAX_TEXT]}
    if action == "split_words":
        words = re.findall(r"\\S+", value)
        return {"status": "succeeded", "words": words[:MAX_ITEMS], "count": len(words), "truncated": len(words)>MAX_ITEMS}
    if action == "reverse_words":
        words = re.findall(r"\\S+", value)
        return {"status": "succeeded", "text": " ".join(reversed(words))[:MAX_TEXT], "word_count": len(words)}
    if action == "shuffle_preview":
        # Deterministic preview: rotate by half; avoids randomness in an auditable tool.
        words = value.splitlines()
        if len(words) > 1:
            shift = len(words)//2
            words = words[shift:] + words[:shift]
        return {"status": "succeeded", "lines": words[:MAX_ITEMS], "note": "Deterministic rotated preview, not a random shuffle."}

    if action == "extract_domains":
        hosts = re.findall(r"https?://([^/\\s?#]+)", value, re.I)
        domains = [host.rsplit("@", 1)[-1].split(":")[0].lower() for host in hosts]
        return {"status": "succeeded", "domains": list(dict.fromkeys(domains))[:MAX_ITEMS]}
    if action == "extract_file_extensions":
        extensions = re.findall(r"(?i)(?<![\\w.])\\w+\\.([a-z0-9]{1,12})\\b", value)
        return {"status": "succeeded", "extensions": list(dict.fromkeys(x.lower() for x in extensions))[:MAX_ITEMS]}
    if action in {"json_keys", "json_value_types"}:
        try:
            obj = json.loads(value)
        except json.JSONDecodeError as exc:
            return {"status": "failed", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if action == "json_keys":
            if not isinstance(obj, dict):
                return {"status": "failed", "message": "JSON root must be an object."}
            return {"status": "succeeded", "keys": list(obj.keys())[:MAX_ITEMS], "count": len(obj)}
        members = {str(k): type(v).__name__ for k, v in list(obj.items())[:MAX_ITEMS]} if isinstance(obj, dict) else None
        return {"status": "succeeded", "root_type": type(obj).__name__, "members": members}
    if action == "lines_to_json_array":
        lines = value.splitlines()
        return {"status": "succeeded", "json": json.dumps(lines, ensure_ascii=False)[:MAX_TEXT], "count": len(lines)}
    if action == "extract_todo_comments":
        matches = re.findall(r"(?im)^.*\\b(?:TODO|FIXME|XXX)\\b.*$", value)
        return {"status": "succeeded", "comments": matches[:MAX_ITEMS], "count": len(matches)}
    if action == "extract_functions":
        matches = re.findall(r"(?m)^\\s*(?:async\\s+)?def\\s+(\\w+)\\s*\\(", value)
        return {"status": "succeeded", "functions": matches[:MAX_ITEMS], "count": len(matches)}
    if action == "extract_imports":
        matches = re.findall(r"(?m)^\\s*(?:import\\s+.+|from\\s+.+\\s+import\\s+.+)", value)
        return {"status": "succeeded", "imports": matches[:MAX_ITEMS], "count": len(matches)}
    if action == "extract_log_levels":
        levels = re.findall(r"(?i)\\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\\b", value)
        return {"status": "succeeded", "levels": list(dict.fromkeys(x.upper() for x in levels)), "counts": dict(Counter(x.upper() for x in levels))}
    if action in {"numeric_summary", "sum_numbers", "average_numbers", "median_numbers", "min_max_numbers"}:
        nums = [float(x) for x in re.findall(r"[-+]?(?:\\d+\\.?\\d*|\\.\\d+)", value)]
        if not nums or any(not math.isfinite(n) for n in nums):
            return {"status": "failed", "message": "Provide finite numbers in the text."}
        import statistics
        if action == "sum_numbers": return {"status": "succeeded", "sum": sum(nums), "count": len(nums)}
        if action == "average_numbers": return {"status": "succeeded", "average": sum(nums)/len(nums), "count": len(nums)}
        if action == "median_numbers": return {"status": "succeeded", "median": statistics.median(nums), "count": len(nums)}
        if action == "min_max_numbers": return {"status": "succeeded", "minimum": min(nums), "maximum": max(nums), "count": len(nums)}
        return {"status": "succeeded", "count": len(nums), "sum": sum(nums), "average": sum(nums)/len(nums), "median": statistics.median(nums), "minimum": min(nums), "maximum": max(nums)}
    if action == "percent_change":
        try:
            old, new = float(step.get("old_value")), float(step.get("new_value"))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "Provide numeric old_value and new_value."}
        if not math.isfinite(old) or not math.isfinite(new) or old == 0:
            return {"status": "failed", "message": "Values must be finite and old_value cannot be zero."}
        return {"status": "succeeded", "percent_change": round((new-old)/abs(old)*100, 6)}
    if action in {"parse_key_value_lines", "key_value_to_json"}:
        pairs = {}
        for line in value.splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                if key.strip(): pairs[key.strip()] = val.strip()
        if action == "key_value_to_json":
            return {"status": "succeeded", "json": json.dumps(pairs, ensure_ascii=False, indent=2)[:MAX_TEXT]}
        return {"status": "succeeded", "values": dict(list(pairs.items())[:MAX_ITEMS]), "count": len(pairs)}
    if action == "json_to_key_value":
        try:
            obj = json.loads(value)
        except json.JSONDecodeError as exc:
            return {"status": "failed", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if not isinstance(obj, dict):
            return {"status": "failed", "message": "JSON root must be an object."}
        lines = [str(k) + "=" + (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)) for k, v in list(obj.items())[:MAX_ITEMS]]
        return {"status": "succeeded", "text": "\\n".join(lines)[:MAX_TEXT]}
    if action == "redact_urls":
        return {"status": "succeeded", "text": re.sub(r"https?://[^\\s<>]+", "[REDACTED_URL]", value, flags=re.I)}
    if action == "redact_ip_addresses":
        return {"status": "succeeded", "text": re.sub(r"(?<![\\w.])(?:\\d{1,3}\\.){3}\\d{1,3}(?![\\w.])", "[REDACTED_IP]", value)}
    if action == "extract_xml_tags":
        tags = re.findall(r"<([A-Za-z_][\\w:.-]*)\\b[^>]*>", value)
        return {"status": "succeeded", "tags": list(dict.fromkeys(tags))[:MAX_ITEMS]}
    if action == "strip_xml_tags":
        return {"status": "succeeded", "text": re.sub(r"<[^>]*>", " ", value)[:MAX_TEXT], "note": "Simple tag stripping; not a full XML parser."}
    if action == "extract_sql_tables":
        tables = re.findall(r"(?i)\\b(?:from|join|into|update|table)\\s+([A-Za-z_][\\w.]*)", value)
        return {"status": "succeeded", "tables": list(dict.fromkeys(tables))[:MAX_ITEMS]}

    if action in {"json_query", "extract_json_paths", "json_filter_array", "json_sort_array", "json_unique_array", "json_to_markdown_table"}:
        try:
            obj = json.loads(value)
        except json.JSONDecodeError as exc:
            return {"status": "failed", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if action == "json_query":
            path = step.get("path", "")
            current = obj
            try:
                for part in path.strip(".").split(".") if path else []:
                    if isinstance(current, list): current = current[int(part)]
                    elif isinstance(current, dict): current = current[part]
                    else: raise KeyError(part)
            except (KeyError, IndexError, ValueError, TypeError):
                return {"status": "failed", "message": "The requested JSON path does not exist."}
            return {"status": "succeeded", "value": current}
        if action == "extract_json_paths":
            paths = []
            def walk_json(node, prefix="$"):
                if len(paths) >= MAX_ITEMS: return
                if isinstance(node, dict):
                    for key, child in node.items(): walk_json(child, prefix+"."+str(key))
                elif isinstance(node, list):
                    for i, child in enumerate(node): walk_json(child, prefix+"["+str(i)+"]")
                else: paths.append({"path": prefix, "type": type(node).__name__})
            walk_json(obj)
            return {"status": "succeeded", "paths": paths}
        if action in {"json_filter_array", "json_sort_array", "json_unique_array"}:
            if not isinstance(obj, list): return {"status": "failed", "message": "JSON root must be an array."}
            if action == "json_filter_array":
                key, contains = step.get("key"), str(step.get("contains", ""))
                filtered = [item for item in obj if isinstance(item, dict) and key in item and contains.casefold() in str(item[key]).casefold()]
                return {"status": "succeeded", "items": filtered[:MAX_ITEMS], "count": len(filtered)}
            if action == "json_sort_array":
                key = step.get("key")
                ordered = sorted(obj, key=lambda item: str(item.get(key, "") if isinstance(item, dict) else item).casefold(), reverse=bool(step.get("descending", False)))
                return {"status": "succeeded", "items": ordered[:MAX_ITEMS], "count": len(ordered)}
            seen, unique = set(), []
            for item in obj:
                signature = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if signature not in seen: seen.add(signature); unique.append(item)
            return {"status": "succeeded", "items": unique[:MAX_ITEMS], "count": len(unique)}
        if not isinstance(obj, list) or not obj or any(not isinstance(item, dict) for item in obj):
            return {"status": "failed", "message": "JSON root must be a non-empty array of objects."}
        columns = list(dict.fromkeys(k for item in obj[:MAX_ROWS] for k in item))
        def cell(value):
            return str(value if value is not None else "").replace("|", "\\|").replace("\\n", " ")
        table = "| " + " | ".join(columns) + " |\\n| " + " | ".join("---" for _ in columns) + " |\\n"
        table += "".join("| " + " | ".join(cell(row.get(k)) for k in columns) + " |\\n" for row in obj[:200])
        return {"status": "succeeded", "markdown_table": table[:MAX_TEXT], "rows_included": min(len(obj), 200)}
    if action == "markdown_table_to_csv":
        rows = []
        for line in value.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [cell.strip() for cell in stripped[1:-1].split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
        if not rows: return {"status": "failed", "message": "No Markdown table rows found."}
        width = max(len(row) for row in rows)
        rows = [row + [""]*(width-len(row)) for row in rows]
        output = io.StringIO(); csv.writer(output).writerows(rows[:MAX_ROWS])
        return {"status": "succeeded", "csv": output.getvalue()[:MAX_TEXT], "row_count": len(rows)}
    if action == "extract_csv_emails":
        try: rows = list(csv.DictReader(io.StringIO(value)))[:MAX_ROWS]
        except csv.Error as exc: return {"status": "failed", "message": str(exc)}
        found = []
        for row in rows:
            for cell in row.values():
                if cell:
                    found.extend(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", cell, re.I))
        return {"status": "succeeded", "emails": list(dict.fromkeys(found))[:MAX_ITEMS], "count": len(set(found))}
    if action in {"csv_column_rename", "csv_column_remove"}:
        try: rows = list(csv.DictReader(io.StringIO(value)))[:MAX_ROWS]
        except csv.Error as exc: return {"status": "failed", "message": str(exc)}
        if not rows: return {"status": "failed", "message": "CSV must include headers and rows."}
        old_name = step.get("column")
        fields = list(rows[0].keys())
        if old_name not in fields: return {"status": "failed", "message": "Column does not exist."}
        if action == "csv_column_remove":
            fields = [name for name in fields if name != old_name]
            rows = [{k:v for k,v in row.items() if k != old_name} for row in rows]
        else:
            new_name = step.get("new_name")
            if not isinstance(new_name, str) or not new_name.strip() or new_name in fields: return {"status": "failed", "message": "new_name must be non-empty and unique."}
            fields = [new_name if name == old_name else name for name in fields]
            rows = [{(new_name if k == old_name else k):v for k,v in row.items()} for row in rows]
        output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        return {"status": "succeeded", "csv": output.getvalue()[:MAX_TEXT], "columns": fields, "row_count": len(rows)}
    if action == "csv_rows_to_json":
        try: rows = list(csv.DictReader(io.StringIO(value)))[:MAX_ROWS]
        except csv.Error as exc: return {"status": "failed", "message": str(exc)}
        if not rows: return {"status": "failed", "message": "CSV must include a header row."}
        return {"status": "succeeded", "json": json.dumps(rows, ensure_ascii=False)[:MAX_TEXT], "row_count": len(rows)}
    if action == "json_to_xml_preview":
        try: obj = json.loads(value)
        except json.JSONDecodeError as exc: return {"status": "failed", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        def xml_safe(s):
            return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")
        def to_xml(tag, node, depth=0):
            if depth > 20: return ""
            tag = re.sub(r"[^A-Za-z0-9_.-]", "_", str(tag)) or "item"
            if isinstance(node, dict): inner = "".join(to_xml(k,v,depth+1) for k,v in list(node.items())[:MAX_ITEMS])
            elif isinstance(node, list): inner = "".join(to_xml("item",v,depth+1) for v in node[:MAX_ITEMS])
            else: inner = xml_safe(json.dumps(node, ensure_ascii=False) if node is None or isinstance(node,bool) else node)
            return "<"+tag+">"+inner+"</"+tag+">"
        return {"status": "succeeded", "xml_preview": to_xml("root", obj)[:MAX_TEXT], "note": "Preview only; validate XML before production use."}
    if action == "extract_xml_attributes":
        pairs = []
        for tag in re.findall(r"<[^>]+>", value):
            name = re.match(r"<([A-Za-z_][\\w:.-]*)", tag)
            attrs = re.findall(r"""([A-Za-z_:][\\w:.-]*)\\s*=\\s*["']([^"']*)["']""", tag)
            for key, val in attrs: pairs.append({"tag": name.group(1) if name else "", "attribute": key, "value": val})
        return {"status": "succeeded", "attributes": pairs[:MAX_ITEMS], "count": len(pairs)}
    if action == "extract_html_forms":
        forms = re.findall(r"(?is)<form\\b[^>]*>.*?</form\\s*>", value)
        return {"status": "succeeded", "forms": forms[:50], "count": len(forms), "note": "Extracted markup only; forms are not submitted."}
    if action == "extract_html_scripts":
        scripts = re.findall(r"(?is)<script\\b[^>]*>(.*?)</script\\s*>", value)
        sources = re.findall(r"""(?is)<script\\b[^>]*\\bsrc\\s*=\\s*["']([^"']+)["']""", value)
        return {"status": "succeeded", "inline_scripts": scripts[:20], "sources": sources[:MAX_ITEMS], "count": len(scripts)+len(sources)}
    if action == "extract_css_urls":
        urls = re.findall(r"""(?i)url\\(\\s*["']?([^)"']+)""", value)
        return {"status": "succeeded", "urls": list(dict.fromkeys(x.strip() for x in urls))[:MAX_ITEMS]}
    if action == "extract_sql_statements":
        statements = [part.strip() for part in value.split(";") if part.strip()]
        return {"status": "succeeded", "statements": statements[:MAX_ITEMS], "count": len(statements), "note": "SQL text is split only; no statement is executed."}
    if action == "extract_markdown_images":
        images = [{"alt": alt, "url": url} for alt, url in re.findall(r"!\\[([^\\]]*)\\]\\(([^)]+)\\)", value)]
        return {"status": "succeeded", "images": images[:MAX_ITEMS], "count": len(images)}
    if action == "markdown_heading_slugs":
        headings = []
        for line in value.splitlines():
            match = re.match(r"^\\s{0,3}(#{1,6})\\s+(.+?)\\s*#*\\s*$", line)
            if match:
                title = match.group(2).strip()
                slug = re.sub(r"[^a-z0-9 -]", "", title.casefold()).strip().replace(" ", "-")
                headings.append({"title": title, "level": len(match.group(1)), "slug": slug})
        return {"status": "succeeded", "headings": headings[:MAX_ITEMS], "count": len(headings)}
    if action == "text_to_html_paragraphs":
        paragraphs = [p.strip() for p in re.split(r"\\n\\s*\\n", value.strip()) if p.strip()]
        escaped = [p.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#x27;") for p in paragraphs]
        return {"status": "succeeded", "html": "".join("<p>"+p.replace("\\n","<br>")+"</p>" for p in escaped)[:MAX_TEXT], "paragraph_count": len(paragraphs)}
    if action == "count_sentiment_terms":
        positive = {"good","great","excellent","happy","love","helpful","success","positive","best","wonderful","thanks"}
        negative = {"bad","poor","hate","sad","fail","failure","negative","worst","angry","broken","terrible"}
        words = set(re.findall(r"[a-z]+", value.casefold()))
        pos, neg = sorted(words & positive), sorted(words & negative)
        return {"status": "succeeded", "positive_terms": pos, "negative_terms": neg, "positive_count": sum(value.casefold().count(w) for w in pos), "negative_count": sum(value.casefold().count(w) for w in neg), "note": "Lexicon-based signal only, not a reliable sentiment model."}
    if action == "readability_estimate":
        words = re.findall(r"\\S+", value)
        sentences = max(1, len([s for s in re.split(r"(?<=[.!?])\\s+", value.strip()) if s]))
        syllables = 0
        for word in re.findall(r"[A-Za-z]+", value):
            chunks = re.findall(r"[aeiouy]+", word.lower())
            syllables += max(1, len(chunks) - (1 if word.lower().endswith("e") and len(chunks)>1 else 0))
        wcount = max(1, len(words))
        score = 206.835 - 1.015*(wcount/sentences) - 84.6*(syllables/wcount)
        return {"status": "succeeded", "word_count": len(words), "sentence_count": sentences, "estimated_syllables": syllables, "flesch_reading_ease_estimate": round(score,2), "note": "English-oriented heuristic; not suitable as a formal accessibility or education assessment."}
    if action == "extract_acronyms":
        acronyms = re.findall(r"\\b[A-Z]{2,}(?:[0-9]+)?\\b", value)
        return {"status": "succeeded", "acronyms": list(dict.fromkeys(acronyms))[:MAX_ITEMS]}
    if action == "normalize_phone_candidates":
        candidates = re.findall(r"(?<!\\w)\\+?\\d[\\d ().-]{6,}\\d(?!\\w)", value)
        normalized = list(dict.fromkeys(re.sub(r"[^+0-9]", "", item) for item in candidates))
        normalized = [item for item in normalized if 7 <= sum(ch.isdigit() for ch in item) <= 15]
        return {"status": "succeeded", "phone_candidates": normalized[:MAX_ITEMS], "note": "Normalization only; not carrier or ownership verification."}
    if action == "extract_hex_colors":
        colors = re.findall(r"(?i)(?<![\\w])#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})(?![\\w])", value)
        return {"status": "succeeded", "colors": list(dict.fromkeys(x.upper() for x in colors))[:MAX_ITEMS]}

    if action in {"calculate_percentage", "calculate_discount", "calculate_tax"}:
        try:
            amount = float(step.get("amount", step.get("value")))
            rate = float(step.get("rate_percent", step.get("rate")))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "Provide numeric amount/value and rate_percent."}
        if not math.isfinite(amount) or not math.isfinite(rate) or rate < 0 or rate > 10000:
            return {"status": "failed", "message": "Values must be finite and rate must be between 0 and 10000."}
        change = amount * rate / 100
        if action == "calculate_percentage": result = change
        elif action == "calculate_discount": result = amount - change
        else: result = amount + change
        return {"status": "succeeded", "base_amount": amount, "rate_percent": rate, "rate_amount": round(change, 8), "result": round(result, 8)}
    if action in {"calculate_simple_interest", "calculate_compound_interest"}:
        try:
            principal = float(step.get("principal")); rate = float(step.get("annual_rate_percent")); years = float(step.get("years"))
            periods = int(step.get("periods_per_year", 1))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "Provide principal, annual_rate_percent, years and optional periods_per_year."}
        if not all(math.isfinite(x) for x in (principal, rate, years)) or principal < 0 or rate < 0 or years < 0 or not 1 <= periods <= 365:
            return {"status": "failed", "message": "Inputs must be finite and non-negative; periods_per_year must be 1–365."}
        interest = principal*rate/100*years if action=="calculate_simple_interest" else principal*((1+rate/100/periods)**(periods*years)-1)
        return {"status": "succeeded", "principal": principal, "interest": round(interest, 8), "total": round(principal+interest, 8), "method": "simple" if action=="calculate_simple_interest" else "compound", "note": "Mathematical estimate only; excludes fees, tax and changing rates."}
    if action == "calculate_loan_payment":
        try:
            principal = float(step.get("principal")); annual_rate = float(step.get("annual_rate_percent")); months = int(step.get("months"))
        except (TypeError, ValueError):
            return {"status": "failed", "message": "Provide principal, annual_rate_percent and months."}
        if not math.isfinite(principal) or not math.isfinite(annual_rate) or principal <= 0 or annual_rate < 0 or not 1 <= months <= 600:
            return {"status": "failed", "message": "Principal must be positive, rate non-negative and months between 1 and 600."}
        monthly = annual_rate/1200
        payment = principal/months if monthly == 0 else principal*monthly/(1-(1+monthly)**(-months))
        return {"status": "succeeded", "monthly_payment": round(payment, 2), "total_paid": round(payment*months, 2), "total_interest": round(payment*months-principal, 2), "note": "Estimate only; excludes fees and variable-rate changes."}
    if action == "parse_iso_datetime":
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z","+00:00"))
        except ValueError:
            return {"status": "failed", "message": "Input must be a valid ISO-8601 date/time."}
        return {"status": "succeeded", "iso": parsed.isoformat(), "has_timezone": parsed.tzinfo is not None, "date": parsed.date().isoformat(), "time": parsed.time().isoformat()}
    if action == "date_difference":
        try:
            start = datetime.fromisoformat(str(step.get("start","")).replace("Z","+00:00"))
            end = datetime.fromisoformat(str(step.get("end","")).replace("Z","+00:00"))
        except ValueError:
            return {"status": "failed", "message": "Provide ISO-8601 start and end values."}
        if (start.tzinfo is None) != (end.tzinfo is None):
            return {"status": "failed", "message": "Both dates must either include timezone offsets or omit them."}
        delta = end-start
        return {"status": "succeeded", "seconds": delta.total_seconds(), "days": delta.total_seconds()/86400, "whole_days": delta.days}
    if action == "add_days":
        try:
            start = datetime.fromisoformat(str(step.get("date","")).replace("Z","+00:00")); days = int(step.get("days"))
        except (ValueError, TypeError):
            return {"status": "failed", "message": "Provide an ISO-8601 date and integer days."}
        if abs(days) > 36500: return {"status": "failed", "message": "days must be between -36500 and 36500."}
        return {"status": "succeeded", "result": (start+timedelta(days=days)).isoformat()}
    if action == "generate_uuid":
        from uuid import uuid4
        return {"status": "succeeded", "uuid": str(uuid4())}
    if action == "generate_timestamp":
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return {"status": "succeeded", "iso": now.isoformat(), "unix_seconds": int(now.timestamp()), "unix_milliseconds": int(now.timestamp()*1000)}
    if action in {"json_minify", "json_sort_keys"}:
        try: obj=json.loads(value)
        except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        result=json.dumps(obj,ensure_ascii=False,separators=(",",":") if action=="json_minify" else (",",": "),sort_keys=action=="json_sort_keys")
        return {"status":"succeeded","json":result[:MAX_TEXT],"truncated":len(result)>MAX_TEXT}
    if action in {"csv_to_json", "csv_count_rows", "csv_headers", "csv_column_unique", "csv_remove_blank_rows", "csv_reverse_rows", "csv_sample_rows", "csv_validate_shape", "tsv_to_csv", "csv_to_tsv"}:
        delimiter="\\t" if action=="tsv_to_csv" else ","
        try:
            rows=list(csv.reader(io.StringIO(value),delimiter=delimiter))[:MAX_ROWS+1]
        except csv.Error as exc: return {"status":"failed","message":f"Delimited text parsing failed: {exc}"}
        if not rows: return {"status":"failed","message":"Input is empty."}
        headers=rows[0]; data=rows[1:]
        if action=="csv_headers": return {"status":"succeeded","headers":headers,"column_count":len(headers)}
        if action=="csv_count_rows": return {"status":"succeeded","row_count":len(data),"column_count":len(headers)}
        if action=="csv_validate_shape":
            counts=Counter(len(row) for row in rows)
            return {"status":"succeeded","valid":len(counts)==1,"expected_columns":len(headers),"row_width_counts":dict(counts)}
        if action=="csv_column_unique":
            try: col=int(step.get("column_index",0))
            except (TypeError,ValueError): col=0
            if col<0 or col>=len(headers): return {"status":"failed","message":"column_index is outside the available columns."}
            vals=list(dict.fromkeys(row[col] for row in data if col<len(row)))
            return {"status":"succeeded","values":vals[:MAX_ITEMS],"unique_count":len(vals)}
        if action=="csv_remove_blank_rows": data=[row for row in data if any(cell.strip() for cell in row)]
        if action=="csv_reverse_rows": data=list(reversed(data))
        if action=="csv_sample_rows":
            try: sample=int(step.get("sample_size",10))
            except (TypeError,ValueError): sample=10
            if not 1<=sample<=200: return {"status":"failed","message":"sample_size must be 1–200."}
            data=data[:sample]
        if action=="csv_to_json":
            if not headers: return {"status":"failed","message":"CSV needs a header row."}
            items=[{headers[i]:row[i] if i<len(row) else "" for i in range(len(headers))} for row in data]
            return {"status":"succeeded","json":json.dumps(items,ensure_ascii=False)[:MAX_TEXT],"row_count":len(items)}
        output=io.StringIO(); writer=csv.writer(output,delimiter="\\t" if action=="csv_to_tsv" else ",")
        writer.writerow(headers); writer.writerows(data)
        return {"status":"succeeded","text":output.getvalue()[:MAX_TEXT],"row_count":len(data)}
    if action == "extract_list_items":
        items=[]
        for line in value.splitlines():
            match=re.match(r"^\\s*(?:[-*+]\\s+|\\d+[.)]\\s+)(.+)$",line)
            if match: items.append(match.group(1).strip())
        return {"status":"succeeded","items":items[:MAX_ITEMS],"count":len(items)}
    if action == "extract_numbered_lists":
        items=re.findall(r"(?m)^\\s*\\d+[.)]\\s+(.+)$",value)
        return {"status":"succeeded","items":[x.strip() for x in items[:MAX_ITEMS]],"count":len(items)}
    if action == "extract_bullet_lists":
        items=re.findall(r"(?m)^\\s*[-*+]\\s+(.+)$",value)
        return {"status":"succeeded","items":[x.strip() for x in items[:MAX_ITEMS]],"count":len(items)}
    if action in {"extract_first_paragraph","extract_last_paragraph"}:
        paragraphs=[p.strip() for p in re.split(r"\\n\\s*\\n",value.strip()) if p.strip()]
        selected=(paragraphs[:1] if action=="extract_first_paragraph" else paragraphs[-1:])
        return {"status":"succeeded","paragraph":selected[0] if selected else "","paragraph_count":len(paragraphs)}
    if action == "word_count_by_sentence":
        sentences=[s for s in re.split(r"(?<=[.!?])\\s+",value.strip()) if s]
        return {"status":"succeeded","sentences":[{"sentence":s[:2000],"word_count":len(re.findall(r"\\S+",s))} for s in sentences[:MAX_ITEMS]],"sentence_count":len(sentences)}
    if action == "count_code_lines":
        lines=value.splitlines()
        blank=sum(not line.strip() for line in lines)
        comments=sum(line.lstrip().startswith(("#","//","/*","*","<!--")) for line in lines if line.strip())
        return {"status":"succeeded","total_lines":len(lines),"blank_lines":blank,"comment_like_lines":comments,"non_blank_lines":len(lines)-blank,"note":"Comment classification is heuristic and language-independent."}
    if action == "strip_comments":
        result=re.sub(r"(?s)<!--.*?-->","",value)
        result=re.sub(r"(?m)^\\s*(?:#|//).*$","",result)
        return {"status":"succeeded","text":result[:MAX_TEXT],"note":"Removes full-line hash/slash comments and HTML comments only."}
    if action == "extract_html_ids":
        ids=re.findall(r"""(?i)\\bid\\s*=\\s*["']([^"']+)["']""",value)
        return {"status":"succeeded","ids":list(dict.fromkeys(ids))[:MAX_ITEMS]}
    if action == "extract_css_classes":
        classes=re.findall(r"""(?i)\\bclass\\s*=\\s*["']([^"']+)["']""",value)
        tokens=[]
        for item in classes: tokens.extend(item.split())
        return {"status":"succeeded","classes":list(dict.fromkeys(tokens))[:MAX_ITEMS]}
    if action == "find_email_domains":
        emails=re.findall(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\\.[A-Z]{2,})",value,re.I)
        return {"status":"succeeded","domains":list(dict.fromkeys(x.lower() for x in emails))[:MAX_ITEMS]}
    if action == "extract_urls_domains":
        urls=re.findall(r"https?://[^\\s<>\\\"']+",value,re.I)
        result=[]
        for url in urls:
            host=urlparse(url).hostname
            if host: result.append({"url":url,"domain":host.lower()})
        return {"status":"succeeded","items":result[:MAX_ITEMS]}
    if action == "extract_ip_addresses":
        candidates=re.findall(r"(?<![\\w.])(?:\\d{1,3}\\.){3}\\d{1,3}(?![\\w.])",value)
        valid=[x for x in candidates if all(0<=int(part)<=255 for part in x.split("."))]
        return {"status":"succeeded","addresses":list(dict.fromkeys(valid))[:MAX_ITEMS]}

    if action == "extract_words":
        words = re.findall(r"[\\w’'-]+", value, re.UNICODE)
        return {"status":"succeeded","words":words[:MAX_ITEMS],"count":len(words),"truncated":len(words)>MAX_ITEMS}
    if action == "extract_unique_words":
        words = list(dict.fromkeys(re.findall(r"[\\w’'-]+", value.casefold(), re.UNICODE)))
        return {"status":"succeeded","words":words[:MAX_ITEMS],"count":len(words),"truncated":len(words)>MAX_ITEMS}
    if action == "word_count_by_paragraph":
        paragraphs=[p for p in re.split(r"\\n\\s*\\n",value.strip()) if p.strip()]
        return {"status":"succeeded","paragraphs":[{"index":i,"word_count":len(re.findall(r"\\S+",p)),"text":p[:1000]} for i,p in enumerate(paragraphs[:MAX_ITEMS],1)],"count":len(paragraphs)}
    if action == "sentence_count":
        sentences=[s for s in re.split(r"(?<=[.!?])\\s+",value.strip()) if s]
        return {"status":"succeeded","sentence_count":len(sentences)}
    if action == "count_punctuation":
        return {"status":"succeeded","punctuation_count":sum(unicodedata.category(ch).startswith("P") for ch in value),"counts":dict(Counter(ch for ch in value if unicodedata.category(ch).startswith("P")).most_common(100))}
    if action == "count_uppercase":
        return {"status":"succeeded","uppercase_characters":sum(ch.isupper() for ch in value),"lowercase_characters":sum(ch.islower() for ch in value)}
    if action == "count_digits":
        return {"status":"succeeded","digit_count":sum(ch.isdigit() for ch in value),"digits":re.findall(r"\\d",value)[:MAX_ITEMS]}
    if action in {"strip_accents","transliterate_ascii"}:
        normalized=unicodedata.normalize("NFKD",value)
        stripped="".join(ch for ch in normalized if not unicodedata.combining(ch))
        if action=="transliterate_ascii": stripped=stripped.encode("ascii","ignore").decode("ascii")
        return {"status":"succeeded","text":stripped[:MAX_TEXT]}
    if action == "mask_digits":
        return {"status":"succeeded","text":re.sub(r"\\d","*",value)}
    if action == "mask_emails":
        return {"status":"succeeded","text":re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}","[REDACTED_EMAIL]",value,flags=re.I)}
    if action == "mask_phone_numbers":
        return {"status":"succeeded","text":re.sub(r"(?<!\\w)\\+?\\d[\\d ().-]{6,}\\d(?!\\w)","[REDACTED_PHONE]",value)}
    if action == "mask_credit_card_candidates":
        return {"status":"succeeded","text":re.sub(r"(?<!\\d)(?:\\d[ -]?){13,19}(?!\\d)","[REDACTED_CARD_CANDIDATE]",value),"note":"Pattern-based masking; no card validity check is performed."}
    if action == "extract_email_domains":
        domains=re.findall(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\\.[A-Z]{2,})",value,re.I)
        return {"status":"succeeded","domains":list(dict.fromkeys(x.lower() for x in domains))[:MAX_ITEMS]}
    if action == "extract_urls_with_paths":
        urls=re.findall(r"https?://[^\\s<>\\\"']+",value,re.I)
        result=[]
        for url in urls:
            parsed=urlparse(url)
            if parsed.hostname: result.append({"url":url,"host":parsed.hostname,"path":parsed.path,"query":parsed.query})
        return {"status":"succeeded","urls":result[:MAX_ITEMS]}
    if action == "extract_query_params":
        urls=re.findall(r"https?://[^\\s<>\\\"']+",value,re.I)
        results=[]
        for url in urls:
            parsed=urlparse(url)
            if parsed.scheme in {"http","https"} and parsed.hostname: results.append({"url":url,"params":parse_qs(parsed.query)})
        return {"status":"succeeded","urls":results[:MAX_ITEMS]}
    if action == "url_join_preview":
        base=step.get("base_url","")
        if not isinstance(base,str) or urlparse(base).scheme not in {"http","https"} or not urlparse(base).hostname:
            return {"status":"failed","message":"base_url must be an absolute HTTP/HTTPS URL."}
        from urllib.parse import urljoin
        return {"status":"succeeded","url":urljoin(base,value.strip())[:4000],"note":"Preview only; no network request is made."}
    if action in {"format_json_compact","json_minify","json_sort_keys"}:
        try: obj=json.loads(value)
        except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        compact=action in {"format_json_compact","json_minify"}
        result=json.dumps(obj,ensure_ascii=False,separators=(",",":") if compact else (",",": "),sort_keys=action=="json_sort_keys")
        return {"status":"succeeded","json":result[:MAX_TEXT],"truncated":len(result)>MAX_TEXT}
    if action in {"json_array_unique","json_array_length"}:
        try: obj=json.loads(value)
        except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if not isinstance(obj,list): return {"status":"failed","message":"JSON root must be an array."}
        if action=="json_array_length": return {"status":"succeeded","length":len(obj)}
        unique=[];seen=set()
        for item in obj:
            key=json.dumps(item,sort_keys=True,ensure_ascii=False)
            if key not in seen: seen.add(key);unique.append(item)
        return {"status":"succeeded","items":unique[:MAX_ITEMS],"unique_count":len(unique),"original_count":len(obj)}

    if action in {"csv_filter_by_value","csv_rename_header","csv_column_summary","csv_quote_values","csv_to_html_table","html_table_to_csv"}:
        if action=="html_table_to_csv":
            tables=re.findall(r"(?is)<table\\b.*?</table\\s*>",value)
            if not tables: return {"status":"failed","message":"No HTML table found."}
            rows=[]
            for row in re.findall(r"(?is)<tr\\b.*?</tr\\s*>",tables[0]):
                cells=re.findall(r"(?is)<t[dh]\\b[^>]*>(.*?)</t[dh]\\s*>",row)
                rows.append([re.sub(r"<[^>]*>","",cell).strip() for cell in cells])
            if not rows: return {"status":"failed","message":"No table rows found."}
            out=io.StringIO();csv.writer(out).writerows(rows[:MAX_ROWS])
            return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
        try: rows=list(csv.DictReader(io.StringIO(value)))[:MAX_ROWS]
        except csv.Error as exc: return {"status":"failed","message":str(exc)}
        if not rows: return {"status":"failed","message":"CSV must contain a header row and data."}
        fields=list(rows[0].keys())
        if action=="csv_filter_by_value":
            col,needle=step.get("column"),str(step.get("contains",""))
            if col not in fields: return {"status":"failed","message":"Column does not exist."}
            rows=[row for row in rows if needle.casefold() in str(row.get(col,"")).casefold()]
        elif action=="csv_rename_header":
            col,new=step.get("column"),step.get("new_name")
            if col not in fields or not isinstance(new,str) or not new.strip() or (new in fields and new!=col): return {"status":"failed","message":"Provide an existing column and a unique new_name."}
            fields=[new if k==col else k for k in fields];rows=[{(new if k==col else k):v for k,v in row.items()} for row in rows]
        elif action=="csv_column_summary":
            col=step.get("column")
            if col not in fields: return {"status":"failed","message":"Column does not exist."}
            vals=[str(row.get(col,"") or "") for row in rows]
            return {"status":"succeeded","column":col,"non_empty":sum(bool(x.strip()) for x in vals),"unique_count":len(set(vals)),"sample_values":list(dict.fromkeys(vals))[:20]}
        esc=lambda x: str(x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
        if action=="csv_to_html_table":
            html="<table><thead><tr>"+"".join("<th>"+esc(k)+"</th>" for k in fields)+"</tr></thead><tbody>"
            html+="".join("<tr>"+"".join("<td>"+esc(row.get(k,""))+"</td>" for k in fields)+"</tr>" for row in rows[:200])+"</tbody></table>"
            return {"status":"succeeded","html":html[:MAX_TEXT],"row_count":len(rows)}
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields,quoting=csv.QUOTE_ALL if action=="csv_quote_values" else csv.QUOTE_MINIMAL);writer.writeheader();writer.writerows(rows)
        return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
    if action == "extract_markdown_code_languages":
        languages=re.findall(r"(?m)^\\s*\x60{3}([^\\s\x60]*)",value)
        return {"status":"succeeded","languages":list(dict.fromkeys(x or "unspecified" for x in languages))[:MAX_ITEMS]}
    if action == "extract_markdown_links_and_images":
        links=[{"type":"link","label":label,"url":url} for label,url in re.findall(r"(?<!!)\\[([^\\]]+)\\]\\(([^)]+)\\)",value)]
        links.extend({"type":"image","label":label,"url":url} for label,url in re.findall(r"!\\[([^\\]]*)\\]\\(([^)]+)\\)",value))
        return {"status":"succeeded","items":links[:MAX_ITEMS],"count":len(links)}
    if action == "extract_html_headings":
        headings=[]
        for level,title in re.findall(r"(?is)<h([1-6])\\b[^>]*>(.*?)</h[1-6]\\s*>",value):
            headings.append({"level":int(level),"text":re.sub(r"<[^>]*>","",title).strip()})
        return {"status":"succeeded","headings":headings[:MAX_ITEMS],"count":len(headings)}
    if action == "extract_html_emails":
        stripped=re.sub(r"<[^>]*>"," ",value)
        emails=re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}",stripped,re.I)
        return {"status":"succeeded","emails":list(dict.fromkeys(emails))[:MAX_ITEMS]}
    if action == "extract_css_colors":
        colors=re.findall(r"(?i)#[0-9a-f]{3,8}\\b|\\brgba?\\([^)]*\\)|\\bhsl\\([^)]*\\)",value)
        return {"status":"succeeded","colors":list(dict.fromkeys(x.upper() if x.startswith("#") else x for x in colors))[:MAX_ITEMS]}
    if action == "extract_sql_columns":
        clauses=re.findall(r"(?is)\\bselect\\s+(.*?)\\s+from\\b",value)
        columns=[]
        for clause in clauses:
            columns.extend(item.strip().split()[-1].strip(chr(96)+'"[]') for item in clause.split(",") if item.strip())
        return {"status":"succeeded","columns":list(dict.fromkeys(columns))[:MAX_ITEMS],"note":"SQL source parsing heuristic; no query is executed."}
    if action == "extract_sql_parameters":
        params=re.findall(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)|(?<!%)%\\(([A-Za-z_][A-Za-z0-9_]*)\\)s|\\$\\d+",value)
        flat=[next((x for x in group if x), "") for group in params]
        flat.extend(re.findall(r"\\$\\d+",value))
        return {"status":"succeeded","parameters":list(dict.fromkeys(flat))[:MAX_ITEMS]}
    if action == "extract_api_endpoints":
        paths=re.findall(r"(?i)\\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\\s+(/[^\\s\"'<>]+)",value)
        return {"status":"succeeded","endpoints":[{"method":m.upper(),"path":p} for m,p in paths[:MAX_ITEMS]]}
    if action == "extract_env_variable_names":
        names=re.findall(r"(?m)^\\s*(?:export\\s+)?([A-Z_][A-Z0-9_]*)\\s*=",value)
        return {"status":"succeeded","variables":list(dict.fromkeys(names))[:MAX_ITEMS]}
    if action == "extract_git_hashes":
        hashes=re.findall(r"(?i)\\b(?:[0-9a-f]{40}|[0-9a-f]{64})\\b",value)
        return {"status":"succeeded","hashes":list(dict.fromkeys(hashes))[:MAX_ITEMS]}
    if action == "extract_semver_versions":
        versions=re.findall(r"(?<![\\w])v?\\d+\\.\\d+\\.\\d+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?",value)
        return {"status":"succeeded","versions":list(dict.fromkeys(versions))[:MAX_ITEMS]}
    if action == "extract_ipv6_candidates":
        candidates=re.findall(r"(?i)(?<![\\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\\w:])",value)
        return {"status":"succeeded","candidates":list(dict.fromkeys(candidates))[:MAX_ITEMS],"note":"Candidates are not fully validated as IPv6 addresses."}
    if action == "extract_mac_addresses":
        vals=re.findall(r"(?i)\\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\\b",value)
        return {"status":"succeeded","addresses":list(dict.fromkeys(x.upper().replace("-",":") for x in vals))[:MAX_ITEMS]}
    if action == "extract_port_numbers":
        vals=re.findall(r"(?i)\\b(?:port\\s*[:=]?\\s*)(\\d{1,5})\\b",value)
        valid=[int(x) for x in vals if 1<=int(x)<=65535]
        return {"status":"succeeded","ports":list(dict.fromkeys(valid))[:MAX_ITEMS]}
    if action in {"parse_ini_preview","parse_env_preview"}:
        result={}
        for line in value.splitlines():
            line=line.strip()
            if not line or line.startswith(("#",";")): continue
            if action=="parse_ini_preview" and line.startswith("["): continue
            if "=" in line:
                key,val=line.split("=",1);key=key.strip()
                if key and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*",key): result[key]=val.strip().strip('"').strip("'")
        return {"status":"succeeded","values":dict(list(result.items())[:MAX_ITEMS]),"count":len(result),"note":"Preview parser; does not load configuration into the app."}
    if action == "parse_log_timestamps":
        stamps=re.findall(r"\\b\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?\\b",value)
        return {"status":"succeeded","timestamps":list(dict.fromkeys(stamps))[:MAX_ITEMS]}
    if action == "count_log_levels":
        levels=re.findall(r"(?i)\\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\\b",value)
        return {"status":"succeeded","counts":dict(Counter(x.upper() for x in levels)),"total_matches":len(levels)}
    if action == "extract_error_lines":
        lines=[line for line in value.splitlines() if re.search(r"(?i)\\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\\b",line)]
        return {"status":"succeeded","lines":lines[:MAX_ITEMS],"count":len(lines),"truncated":len(lines)>MAX_ITEMS}

    if action == "json_merge_objects":
        try:
            left = json.loads(value)
            right_raw = step.get("second_input", "")
            right = json.loads(right_raw) if isinstance(right_raw, str) else right_raw
        except (json.JSONDecodeError, TypeError) as exc:
            return {"status":"failed","message":"Provide valid JSON in input and second_input."}
        if not isinstance(left, dict) or not isinstance(right, dict):
            return {"status":"failed","message":"Both JSON values must be objects."}
        merged = {**left, **right}
        rendered = json.dumps(merged, ensure_ascii=False, indent=2)
        return {"status":"succeeded","json":rendered[:MAX_TEXT],"keys":len(merged),"note":"Shallow merge; values in second_input replace matching first-object keys."}
    from app.tools.builtin.extra_actions import execute_extra
    return execute_extra(action, step, value)


# Additional bounded productivity actions.
# These actions operate only on explicitly supplied content and never access external accounts.
EXTENDED_ACTIONS.update({
    "csv_column_sort",
    "csv_select_rows",
    "csv_find_value",
    "csv_split_columns",
    "json_array_filter_by_type",
    "json_array_unique_by_key",
    "extract_urls_from_markdown",
    "extract_xml_cdata",
    "extract_http_methods",
    "extract_http_status_lines",
    "parse_duration_iso8601",
    "format_duration_iso8601",
    "format_phone_candidate",
    "mask_urls",
    "extract_top_words",
    "count_word_frequency",
    "extract_nonempty_lines",
    "sort_numeric_lines",
    "csv_column_sort",
    "csv_select_rows",
    "csv_find_value",
    "csv_split_columns",
    "jsonl_count_lines",
    "json_schema_preview",
    "json_type_report",
    "json_array_group_by",
    "json_array_count_by_key",
    "extract_xml_namespaces",
    "extract_xml_comments",
    "extract_html_attributes",
    "extract_css_selectors",
    "extract_css_media_queries",
    "extract_js_imports",
    "extract_js_exports",
    "extract_python_decorators",
    "extract_python_constants",
    "extract_python_docstrings",
    "extract_sql_comments",
    "extract_sql_indexes",
    "extract_http_headers",
    "redact_secrets",
    "extract_stack_frames",
    "parse_duration",
    "format_duration",
    "convert_seconds_to_minutes",
    "convert_minutes_to_seconds",
    "convert_milliseconds_to_seconds",
    "calculate_square_root",
    "calculate_power",
    "calculate_logarithm",
    "calculate_permutation",
    "calculate_combination",
    "calculate_compound_rate",
    "calculate_sales_tax",
    "calculate_average_speed",
    "calculate_distance",
    "calculate_time",
    "convert_percentage_decimal",
    "convert_decimal_percentage",
    "convert_fraction_decimal",
    "decimal_to_fraction",
    "fraction_to_decimal",
    "roman_numeral_validate",
    "format_bytes",
    "format_number_commas",
    "parse_number_locale",
    "format_currency_preview",
    "convert_milliseconds_to_duration",
    "extract_iban_candidates",
    "validate_iban",
    "validate_bic",
    "extract_postal_codes",
    "extract_coordinates",
    "validate_latitude_longitude",
    "json_merge_arrays",
    "json_array_filter_contains",
    "json_array_slice",
    "json_object_pick",
    "json_object_omit",
    "json_object_rename_key",
    "json_object_remove_key",
    "json_object_get",
    "json_object_set",
    "json_object_to_pairs",
    "json_pairs_to_object",
    "json_escape_string",
    "json_unescape_string",
    "json_count_nodes",
    "json_max_depth",
    "json_extract_strings",
    "json_extract_numbers",
    "json_extract_booleans",
    "json_extract_nulls",
    "jsonl_to_json",
    "json_to_jsonl",
    "csv_column_values",
    "csv_column_count",
    "csv_count_blank_cells",
    "csv_column_trim",
    "csv_column_lowercase",
    "csv_column_uppercase",
    "csv_filter_exact",
    "csv_filter_numeric",
    "csv_fill_blank_cells",
    "csv_rename_columns",
    "csv_drop_columns",
    "csv_append_row",
    "csv_prepend_row",
    "csv_column_to_json",
    "csv_sort_by_numeric",
    "count_non_ascii",
    "extract_ascii",
    "remove_non_ascii",
    "replace_regex",
    "split_by_regex",
    "join_unique_lines",
    "count_unique_lines",
    "extract_line_numbers",
    "line_length_stats",
    "word_length_stats",
    "extract_capitalized_words",
    "extract_quoted_strings",
    "extract_parenthetical_text",
    "extract_bracket_contents",
    "normalize_quotes",
    "normalize_dashes",
    "normalize_bullets",
    "remove_duplicate_spaces",
    "remove_trailing_spaces",
    "remove_leading_spaces",
    "strip_markdown_links",
    "validate_url",
    "validate_domain",
    "validate_phone_candidate",
    "validate_date_iso",
    "validate_datetime_iso",
    "validate_json_lines",
    "validate_csv",
    "validate_xml_wellformed",
    "validate_semver",
    "validate_hex_color",
    "validate_mac",
    "validate_ipv6",
    "validate_port",
    "validate_base64",
    "validate_sha256",
    "validate_slug",
    "validate_credit_card_candidate",
    "calculate_mean",
    "calculate_mode",
    "calculate_variance",
    "calculate_standard_deviation",
    "calculate_range",
    "calculate_ratio",
    "calculate_proportion",
    "calculate_markup",
    "calculate_profit_margin",
    "calculate_compound_growth",
    "calculate_tip",
    "calculate_split_bill",
    "calculate_gcd",
    "calculate_lcm",
    "is_prime",
    "factorize_integer",
    "convert_number_base",
    "binary_to_decimal",
    "decimal_to_binary",
    "roman_to_integer",
    "integer_to_roman",
    "unix_to_datetime",
    "datetime_to_unix",
    "seconds_to_duration",
    "duration_to_seconds",
    "days_until_date",
    "weekday_for_date",
    "count_weekdays",
    "next_weekday",
    "add_months",
    "iso_week_number",
    "quarter_for_date",
    "json_flatten",
    "json_deep_merge",
    "json_path_values",
    "json_array_flatten",
    "json_array_reverse",
    "json_array_sort",
    "sort_json_keys",
    "json_pretty_print",
    "json_compact_print",
    "csv_to_xml_preview",
    "csv_column_sum",
    "csv_column_average",
    "csv_column_min_max",
    "csv_transpose",
    "csv_group_count",
    "csv_find_duplicates",
    "csv_remove_duplicates",
    "csv_to_sql_inserts_preview",
    "csv_column_median",
    "csv_column_frequency",
    "csv_validate_email_column",
    "csv_validate_numbers",
    "markdown_table_to_json",
    "json_to_markdown_list",
    "extract_json_objects",
    "extract_xml_text",
    "extract_html_text",
    "extract_css_variables",
    "extract_javascript_functions",
    "extract_python_classes",
    "extract_python_imports",
    "count_word_lengths",
    "word_length_histogram",
    "sentence_case",
    "title_case",
    "camel_case",
    "pascal_case",
    "snake_case",
    "kebab_case",
    "normalize_unicode_nfc",
    "normalize_unicode_nfkc",
    "mask_custom_pattern",
    "extract_lines_unique",
    "compare_lists",
    "extract_semver",
    "extract_uuids",
    "extract_hex_numbers",
    "extract_markdown_headings",
    "extract_html_title",
    "extract_html_meta",
    "extract_html_links_text",
    "business_days_between",
    "add_business_days",
    "is_leap_year",
    "days_in_month",
    "age_from_date",
    "format_datetime",
    "convert_timezone",
    "json_array_flatten",
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
    "extract_domains", "extract_file_extensions", "json_keys", "json_value_types",
    "lines_to_json_array", "extract_todo_comments", "extract_functions", "extract_imports",
    "extract_log_levels", "numeric_summary", "sum_numbers", "average_numbers",
    "median_numbers", "min_max_numbers", "percent_change", "parse_key_value_lines",
    "key_value_to_json", "json_to_key_value", "redact_urls", "redact_ip_addresses",
    "extract_xml_tags", "strip_xml_tags", "extract_sql_tables", "extract_json_paths", "json_query", "json_filter_array",
    "json_sort_array", "json_unique_array", "json_to_markdown_table", "markdown_table_to_csv",
    "extract_csv_emails", "csv_column_rename", "csv_column_remove", "csv_rows_to_json",
    "json_to_xml_preview", "extract_xml_attributes", "extract_html_forms", "extract_html_scripts",
    "extract_css_urls", "extract_sql_statements", "extract_markdown_images", "markdown_heading_slugs",
    "text_to_html_paragraphs", "count_sentiment_terms", "readability_estimate", "extract_acronyms",
    "normalize_phone_candidates", "extract_hex_colors",
    "calculate_percentage", "calculate_discount", "calculate_tax", "calculate_simple_interest",
    "calculate_compound_interest", "calculate_loan_payment", "date_difference", "add_days",
    "parse_iso_datetime", "generate_uuid", "generate_timestamp", "json_minify", "json_sort_keys",
    "csv_to_json", "csv_count_rows", "csv_headers", "csv_column_unique", "csv_remove_blank_rows",
    "csv_reverse_rows", "csv_sample_rows", "csv_validate_shape", "tsv_to_csv", "csv_to_tsv",
    "extract_list_items", "extract_numbered_lists", "extract_bullet_lists",
    "extract_first_paragraph", "extract_last_paragraph", "word_count_by_sentence",
    "count_code_lines", "strip_comments", "extract_html_ids", "extract_css_classes",
    "find_email_domains", "extract_urls_domains", "extract_ip_addresses",
    "extract_words", "extract_unique_words", "word_count_by_paragraph", "sentence_count",
    "count_punctuation", "count_uppercase", "count_digits", "strip_accents", "transliterate_ascii",
    "mask_digits", "mask_emails", "mask_phone_numbers", "mask_credit_card_candidates",
    "extract_email_domains", "extract_urls_with_paths", "extract_query_params", "url_join_preview",
    "format_json_compact", "json_merge_objects", "json_array_unique", "json_array_length",
    "csv_filter_by_value", "csv_rename_header", "csv_column_summary", "csv_quote_values",
    "csv_to_html_table", "html_table_to_csv", "extract_markdown_code_languages",
    "extract_markdown_links_and_images", "extract_html_headings", "extract_html_emails",
    "extract_css_colors", "extract_sql_columns", "extract_sql_parameters", "extract_api_endpoints",
    "extract_env_variable_names", "extract_git_hashes", "extract_semver_versions",
    "extract_ipv6_candidates", "extract_mac_addresses", "extract_port_numbers",
    "parse_ini_preview", "parse_env_preview", "parse_log_timestamps", "count_log_levels", "extract_error_lines",
})
