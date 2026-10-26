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
    "extract_domains", "extract_file_extensions", "json_keys", "json_value_types",
    "lines_to_json_array", "extract_todo_comments", "extract_functions", "extract_imports",
    "extract_log_levels", "numeric_summary", "sum_numbers", "average_numbers",
    "median_numbers", "min_max_numbers", "percent_change", "parse_key_value_lines",
    "key_value_to_json", "json_to_key_value", "redact_urls", "redact_ip_addresses",
    "extract_xml_tags", "strip_xml_tags", "extract_sql_tables",
})
