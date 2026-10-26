"""Deterministic, bounded local tools for Norah's agent runtime.

These tools process user-supplied data only. They do not access accounts, the network,
or the device, and they never execute user-provided code.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from urllib.parse import urlparse

EXTENDED_ACTIONS = {
    "count_characters", "estimate_reading_time", "word_frequency",
    "deduplicate_lines", "sort_lines", "convert_case", "slugify",
    "extract_urls", "extract_headings", "validate_json", "format_json",
    "summarize_csv", "csv_to_markdown", "replace_text", "hash_text",
    "extract_numbers", "extract_hashtags", "extract_mentions",
    "reverse_lines", "trim_lines", "normalize_whitespace",
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

    value = _text(step)
    if not value.strip():
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
    if action == "normalize_whitespace":
        normalized = re.sub(r"\\s+", " ", value).strip()
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
            candidate = candidate.rstrip(".,;:!?)\]")
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
            return str(item or "").replace("|", "\|").replace("\n", " ")
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
