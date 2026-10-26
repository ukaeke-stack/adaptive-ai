from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from app.tools.registry import get_tool, list_tools
from app.api.agent_runtime import SAFE_ACTIONS
from app.tools.builtin.text_tools import EXTENDED_ACTIONS

router = APIRouter(prefix="/v1")


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, Any]


_AGENT_DESCRIPTIONS = {
    "count_words": "Count words, characters, and non-empty paragraphs.",
    "extract_bullets": "Extract non-empty lines as bullet points.",
    "summarize_text": "Create a short extractive summary by selecting initial sentences.",
    "extract_contacts": "Extract email addresses and phone-number candidates from supplied text.",
    "extract_dates": "Extract date strings from supplied text.",
    "draft_message": "Prepare a message draft; never sends it.",
    "calculate": "Evaluate basic arithmetic using a restricted expression parser.",
    "create_reminder": "Save an in-app reminder record; device notification scheduling is not included.",
    "count_characters": "Count characters, non-whitespace characters, lines, and words.",
    "estimate_reading_time": "Estimate reading time at 200 words per minute.",
    "word_frequency": "Rank frequent words while excluding a small common-word list.",
    "deduplicate_lines": "Remove duplicate lines while preserving first occurrence order.",
    "sort_lines": "Sort lines alphabetically without changing their contents.",
    "convert_case": "Convert supplied text to lower, upper, title, or sentence case.",
    "slugify": "Create a bounded ASCII URL-style slug from supplied text.",
    "extract_urls": "Extract HTTP/HTTPS URLs from supplied text.",
    "extract_headings": "Extract Markdown ATX headings and levels.",
    "validate_json": "Validate supplied JSON and report its root type.",
    "format_json": "Pretty-print valid JSON.",
    "summarize_csv": "Report CSV columns, row count, and sample rows.",
    "csv_to_markdown": "Convert CSV into a Markdown table.",
    "replace_text": "Perform literal, non-regex find-and-replace.",
    "hash_text": "Compute a text digest using an allowlisted hash algorithm.",
    "extract_numbers": "Extract distinct numeric strings from supplied text.",
    "extract_hashtags": "Extract hashtags from supplied text.",
    "extract_mentions": "Extract @mentions from supplied text.",
    "reverse_lines": "Reverse the order of supplied lines.",
    "trim_lines": "Trim leading and trailing whitespace from each line.",
}


@router.get("/capabilities")
def capabilities():
    registered = list_tools()
    known = {item["name"] for item in registered}
    registered.extend(
        {"name": name, "description": description, "status": "implemented"}
        for name, description in _AGENT_DESCRIPTIONS.items()
        if name in SAFE_ACTIONS | EXTENDED_ACTIONS and name not in known
    )
    return {
        "capabilities": registered,
        "scope": "Only listed capabilities are executable in the current backend runtime.",
        "not_implemented_by_this_endpoint": [
            "provider OAuth account linking", "general-purpose web browsing automation",
            "arbitrary app control", "unattended external side effects",
            "cross-app background execution", "payment and financial transactions",
        ],
    }


@router.post("/tools/execute")
def execute_tool(request: ToolRequest):
    tool = get_tool(request.name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown tool")
    try:
        result = tool(request.arguments)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": request.name, "result": result}
