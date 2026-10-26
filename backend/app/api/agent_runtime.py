"""Persistent, user-scoped task planning and safe execution for Norah.

This is a bounded agent runtime, not arbitrary code execution. A task is planned,
persisted, explicitly run, and each step result is recorded. External actions such
as sending messages, making calls, payments, publishing, or controlling other apps
are intentionally not executable through this runtime.
"""
from __future__ import annotations

import ast
import json
import os
import math
import operator
import re
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.memory.store import _ready_engine
from app.security.sessions import require_user
from app.tools.builtin.text_tools import execute_extended

router = APIRouter(prefix="/v1/agent", tags=["autonomous agent"])

STATUSES = {"planned", "running", "succeeded", "partially_failed", "failed", "cancelled"}
TEXT_ACTIONS = {"count_words", "extract_bullets", "summarize_text", "extract_contacts", "extract_dates"}
SAFE_ACTIONS = TEXT_ACTIONS | {"draft_message", "calculate", "create_reminder"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_table() -> None:
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_agent_tasks (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, goal TEXT NOT NULL,
            context_json TEXT NOT NULL, plan_json TEXT NOT NULL, results_json TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""))
        conn.execute(text("""CREATE INDEX IF NOT EXISTS adaptive_agent_tasks_user_updated
            ON adaptive_agent_tasks(user_id, updated_at)"""))


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=3, max_length=2000)
    context: dict[str, str] = Field(default_factory=dict, max_length=10)


def _plan(goal: str, context: dict[str, str]) -> list[dict]:
    """Create a transparent, bounded plan from intent; unsupported goals stay unexecutable."""
    lower = goal.lower()
    plan: list[dict] = []
    text_value = context.get("text", "")
    if any(term in lower for term in ("count words", "word count", "how many words")):
        plan.append({"id": "step-1", "action": "count_words", "input": text_value,
                     "requires_context": not bool(text_value), "status": "pending"})
    elif any(term in lower for term in ("extract bullets", "key points", "bullet points")):
        plan.append({"id": "step-1", "action": "extract_bullets", "input": text_value,
                     "requires_context": not bool(text_value), "status": "pending"})
    elif any(term in lower for term in ("extract contact", "find email address", "find phone number", "extract emails")):
        plan.append({"id": "step-1", "action": "extract_contacts", "input": text_value, "requires_context": not bool(text_value), "status": "pending"})
    elif any(term in lower for term in ("extract dates", "find dates", "find deadlines", "list dates")):
        plan.append({"id": "step-1", "action": "extract_dates", "input": text_value, "requires_context": not bool(text_value), "status": "pending"})
    elif any(term in lower for term in ("summarize", "summary of", "give me a summary")):
        plan.append({"id": "step-1", "action": "summarize_text", "input": text_value, "requires_context": not bool(text_value), "status": "pending"})
    elif any(term in lower for term in ("draft a message", "write a message", "draft message", "write an email")):
        plan.append({"id": "step-1", "action": "draft_message", "input": context.get("instructions", goal),
                     "status": "pending", "external_send": False})
    elif any(term in lower for term in ("calculate", "work out", "what is")) and context.get("expression"):
        plan.append({"id": "step-1", "action": "calculate", "expression": context["expression"],
                     "status": "pending"})
    elif "remind me" in lower or "create a reminder" in lower:
        title = context.get("reminder_title", "").strip()
        due_at = context.get("due_at", "").strip()
        if title:
            plan.append({"id": "step-1", "action": "create_reminder", "title": title,
                         "due_at": due_at or None, "notes": context.get("notes", ""),
                         "status": "pending", "device_notification_scheduled": False})
    # Deterministic local data tools. The executor uses a fixed allowlist and never evals input.
    extended_patterns = [
        (("count characters", "character count", "how many characters"), "count_characters"),
        (("reading time", "how long to read", "estimate reading"), "estimate_reading_time"),
        (("word frequency", "most common words", "frequent words"), "word_frequency"),
        (("remove duplicate lines", "deduplicate lines", "unique lines"), "deduplicate_lines"),
        (("sort lines", "sort this list", "alphabetize lines"), "sort_lines"),
        (("uppercase", "upper case", "convert to uppercase"), "convert_case"),
        (("lowercase", "lower case", "convert to lowercase"), "convert_case"),
        (("title case", "convert to title case"), "convert_case"),
        (("slugify", "make a slug", "url slug"), "slugify"),
        (("extract urls", "extract links", "find urls"), "extract_urls"),
        (("extract headings", "list headings", "find markdown headings"), "extract_headings"),
        (("validate json", "check json validity", "is this valid json"), "validate_json"),
        (("format json", "pretty print json", "prettify json"), "format_json"),
        (("summarize csv", "csv summary", "analyze csv"), "summarize_csv"),
        (("convert csv to markdown", "csv to markdown", "make markdown table"), "csv_to_markdown"),
        (("replace text", "replace words", "find and replace"), "replace_text"),
        (("hash this text", "text checksum", "sha256"), "hash_text"),
        (("extract numbers", "find numbers in this text", "list numbers"), "extract_numbers"),
        (("extract hashtags", "find hashtags"), "extract_hashtags"),
        (("extract mentions", "find @mentions", "extract mentions"), "extract_mentions"),
        (("reverse lines", "reverse the line order"), "reverse_lines"),
        (("trim lines", "remove whitespace from lines"), "trim_lines"),
        (("normalize whitespace", "collapse whitespace", "clean extra spaces"), "normalize_whitespace"),
        (("count lines", "line count", "how many lines"), "count_lines"),
        (("extract sentences", "list sentences", "split into sentences"), "extract_sentences"),
        (("redact sensitive data", "redact emails and phones", "mask personal data"), "redact_sensitive_data"),
        (("strip html", "remove html tags", "extract text from html"), "strip_html"),
        (("compare these texts", "compare text", "diff these texts"), "compare_texts"),
        (("split text into chunks", "chunk this text", "split text"), "split_text"),
        (("encode base64", "base64 encode"), "base64_encode"),
        (("decode base64", "base64 decode"), "base64_decode"),
        (("parse this url", "parse url", "url components"), "parse_url"),
        (("extract markdown links", "list markdown links"), "extract_markdown_links"),
        (("generate checklist", "turn this into a checklist"), "generate_checklist"),
        (("wrap text", "wrap lines", "line wrap"), "wrap_text"),
        (("convert units", "unit conversion", "convert km", "convert kg", "convert celsius", "convert fahrenheit"), "convert_units"),
    ]
    if not plan:
        for phrases, action in extended_patterns:
            if any(phrase in lower for phrase in phrases):
                step = {"id": "step-1", "action": action, "input": text_value,
                        "requires_context": not bool(text_value), "status": "pending"}
                if action == "convert_case":
                    step["mode"] = "upper" if "upper" in lower else ("title" if "title" in lower else "lower")
                if action == "replace_text":
                    step["find"] = context.get("find", "")
                    step["replacement"] = context.get("replacement", "")
                if action == "hash_text":
                    step["algorithm"] = context.get("algorithm", "sha256")
                if action == "compare_texts":
                    step["second_input"] = context.get("second_text", "")
                if action == "split_text":
                    step["chunk_size"] = context.get("chunk_size", "2000")
                if action == "wrap_text":
                    step["width"] = context.get("width", "80")
                if action == "convert_units":
                    step["number"] = context.get("number", "")
                    step["from_unit"] = context.get("from_unit", "")
                    step["to_unit"] = context.get("to_unit", "")
                plan.append(step)
                break
    if not plan:
        plan.append({"id": "step-1", "action": "unsupported_goal", "status": "blocked",
                     "reason": "This goal needs an integration or tool that is not enabled in the current safe runtime."})
    return plan


def _ai_plan(goal: str, context: dict[str, str]) -> list[dict] | None:
    """Ask the configured model to plan only among the registered safe actions.

    Any malformed or untrusted plan is rejected; callers fall back to deterministic
    planning. The model never supplies code and cannot add new action names.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    parsed = urlparse(base_url)
    if not api_key or not model or parsed.scheme != "https" or parsed.hostname != "api.groq.com":
        return None
    system = (
        "You are a task planner for a constrained assistant. Return JSON only, shaped as "
        '{"steps":[{"action":"count_words|extract_bullets|summarize_text|extract_contacts|extract_dates|draft_message|calculate|create_reminder",'
        '"input":"optional text","expression":"optional arithmetic","title":"optional reminder title",'
        '"due_at":"optional ISO-8601 datetime","notes":"optional reminder notes"}]}. '
        "Use 1 to 5 steps. Only use these exact action names: count_words, extract_bullets, summarize_text, "
        "extract_contacts, extract_dates, draft_message, calculate, create_reminder. Never invent tools. Never plan sending messages, "
        "calls, payments, publishing, arbitrary code, browser control, or device control. "
        "If the goal cannot be completed using the allowed actions, return {\"steps\":[]}."
    )
    safe_context = {str(k)[:40]: str(v)[:4000] for k, v in list(context.items())[:10] if k != "text"}
    safe_context["text_available"] = "true" if context.get("text", "").strip() else "false"
    try:
        with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps({"goal": goal[:2000], "context": safe_context})},
                ], "temperature": 0.1, "max_completion_tokens": 700, "response_format": {"type": "json_object"}},
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
        parsed_plan = json.loads(raw)
        raw_steps = parsed_plan.get("steps") if isinstance(parsed_plan, dict) else None
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 5:
            return None
        plan = []
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict) or item.get("action") not in SAFE_ACTIONS:
                return None
            action = item["action"]
            step = {"id": f"step-{index}", "action": action, "status": "pending"}
            if action in TEXT_ACTIONS:
                value = context.get("text", "")
                if not isinstance(value, str) or len(value) > 12000:
                    return None
                step["input"] = value
                step["requires_context"] = not bool(value.strip())
            elif action == "draft_message":
                value = item.get("input", safe_context.get("instructions", goal))
                if not isinstance(value, str) or len(value) > 4000:
                    return None
                step["input"] = value
                step["external_send"] = False
            elif action == "calculate":
                expression = item.get("expression", safe_context.get("expression", ""))
                if not isinstance(expression, str) or len(expression) > 120:
                    return None
                step["expression"] = expression
            elif action == "create_reminder":
                title = item.get("title", safe_context.get("reminder_title", "")).strip()
                if not title or len(title) > 160:
                    return None
                due_at = item.get("due_at", safe_context.get("due_at")) or None
                notes = item.get("notes", safe_context.get("notes", ""))
                if due_at is not None and (not isinstance(due_at, str) or len(due_at) > 64):
                    return None
                if not isinstance(notes, str) or len(notes) > 2000:
                    return None
                step.update({"title": title, "due_at": due_at, "notes": notes,
                             "device_notification_scheduled": False})
            plan.append(step)
        return plan
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


def _calculate(expression: str) -> float | int:
    if not expression or len(expression) > 120:
        raise ValueError("Provide a short arithmetic expression.")
    tree = ast.parse(expression, mode="eval")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
           ast.UAdd: operator.pos}

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 10**12:
                raise ValueError("Numbers must be within 1 trillion.")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent is too large.")
            result = ops[type(node.op)](left, right)
            if not isinstance(result, (int, float)) or not math.isfinite(result):
                raise ValueError("Result must be a finite real number.")
            if abs(result) > 10**15:
                raise ValueError("Result is too large.")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](visit(node.operand))
        raise ValueError("Only basic arithmetic operators and numeric values are allowed.")

    result = visit(tree)
    if isinstance(result, float) and not result.is_integer():
        return round(result, 10)
    return int(result) if isinstance(result, float) else result


def _execute_step(step: dict) -> dict:
    action = step.get("action")
    try:
        extended_result = execute_extended(step)
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "failed", "message": str(exc)}
    if extended_result is not None:
        return extended_result
    if action in TEXT_ACTIONS:
        value = step.get("input", "")
        if not isinstance(value, str) or not value.strip():
            return {"status": "needs_input", "message": "Add text in the task context before running this step."}
        if action == "count_words":
            return {"status": "succeeded", "word_count": len(re.findall(r"\S+", value)),
                    "character_count": len(value), "paragraph_count": len([x for x in value.splitlines() if x.strip()])}
        if action == "extract_bullets":
            bullets = [line.strip(" \t-*•") for line in value.splitlines() if line.strip()]
            return {"status": "succeeded", "bullets": bullets[:100]}
        if action == "summarize_text":
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", value.strip())) if s.strip()]
            return {"status": "succeeded", "summary": " ".join(sentences[:5])[:3000],
                    "method": "extractive sentence selection", "word_count": len(value.split())}
        if action == "extract_contacts":
            emails = sorted(set(re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", value, re.I)))
            candidates = re.findall(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)", value)
            phones = sorted(set(" ".join(candidate.split()) for candidate in candidates
                                if 7 <= sum(ch.isdigit() for ch in candidate) <= 15))
            return {"status": "succeeded", "emails": emails[:100], "phone_numbers": phones[:100]}
        if action == "extract_dates":
            dates = re.findall(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})\b", value, re.I)
            return {"status": "succeeded", "dates": list(dict.fromkeys(dates))[:100]}
    if action == "draft_message":
        return {"status": "succeeded", "draft": step.get("input", ""),
                "sent": False, "message": "Draft prepared only. Nothing was sent."}
    if action == "calculate":
        try:
            return {"status": "succeeded", "expression": step.get("expression"),
                    "result": _calculate(step.get("expression", ""))}
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
            return {"status": "failed", "message": str(exc)}
    if action == "create_reminder":
        title = step.get("title", "").strip()
        due_at = step.get("due_at")
        if due_at:
            try:
                datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return {"status": "failed", "message": "Reminder date must be ISO-8601."}
        reminder_id, created = str(uuid4()), _now()
        with _ready_engine().begin() as conn:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_reminders (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
                due_at TEXT, notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
                created_at TEXT NOT NULL)"""))
            conn.execute(text("""INSERT INTO adaptive_reminders
                (id,user_id,title,due_at,notes,status,created_at)
                VALUES (:id,:uid,:title,:due,:notes,'active',:created)"""),
                {"id": reminder_id, "uid": step["_user_id"], "title": title,
                 "due": due_at, "notes": step.get("notes", ""), "created": created})
        return {"status": "succeeded", "reminder_id": reminder_id, "title": title,
                "due_at": due_at, "device_notification_scheduled": False}
    return {"status": "blocked", "message": "Action is not available in the safe runtime."}


def _public_task(row) -> dict:
    return {"id": row["id"], "goal": row["goal"], "context": json.loads(row["context_json"]),
            "plan": json.loads(row["plan_json"]), "results": json.loads(row["results_json"]),
            "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


@router.post("/tasks")
def create_task(body: TaskCreate, request: Request):
    user = require_user(request)
    _ensure_table()
    task_id, now = str(uuid4()), _now()
    plan = _plan(body.goal.strip(), body.context)
    if plan and plan[0].get("action") == "unsupported_goal":
        plan = _ai_plan(body.goal.strip(), body.context) or plan
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_agent_tasks
            (id,user_id,goal,context_json,plan_json,results_json,status,created_at,updated_at)
            VALUES (:id,:uid,:goal,:context,:plan,'[]','planned',:created,:updated)"""),
            {"id": task_id, "uid": user["id"], "goal": body.goal.strip(),
             "context": json.dumps(body.context), "plan": json.dumps(plan), "created": now, "updated": now})
    return {"task": {"id": task_id, "goal": body.goal.strip(), "context": body.context,
                     "plan": plan, "results": [], "status": "planned",
                     "created_at": now, "updated_at": now},
            "executed": False, "message": "Plan saved. Review it, then explicitly run it to execute supported steps."}


@router.get("/tasks")
def list_tasks(request: Request, limit: int = 50):
    user = require_user(request)
    _ensure_table()
    limit = max(1, min(limit, 100))
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT * FROM adaptive_agent_tasks WHERE user_id=:uid
            ORDER BY updated_at DESC LIMIT :limit"""), {"uid": user["id"], "limit": limit}).mappings().all()
    return {"tasks": [_public_task(row) for row in rows]}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    user = require_user(request)
    _ensure_table()
    with _ready_engine().connect() as conn:
        row = conn.execute(text("SELECT * FROM adaptive_agent_tasks WHERE id=:id AND user_id=:uid"),
                           {"id": task_id, "uid": user["id"]}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task": _public_task(row)}


@router.post("/tasks/{task_id}/run")
def run_task(task_id: str, request: Request):
    user = require_user(request)
    _ensure_table()
    with _ready_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM adaptive_agent_tasks WHERE id=:id AND user_id=:uid"),
                           {"id": task_id, "uid": user["id"]}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found.")
        if row["status"] in {"succeeded", "cancelled"}:
            raise HTTPException(status_code=409, detail=f"Task is already {row['status']}.")
        plan = json.loads(row["plan_json"])
        previous = json.loads(row["results_json"])
        if any(step.get("action") == "unsupported_goal" for step in plan):
            raise HTTPException(status_code=422, detail="This goal is not supported by the enabled tools. No action was executed.")
        if previous:
            raise HTTPException(status_code=409, detail="This task already has results. Create a new task to avoid duplicate actions.")
        conn.execute(text("UPDATE adaptive_agent_tasks SET status='running',updated_at=:now WHERE id=:id"),
                     {"now": _now(), "id": task_id})
    results = []
    for step in plan:
        execution_step = dict(step)
        execution_step["_user_id"] = user["id"]
        result = _execute_step(execution_step)
        results.append({"step_id": step["id"], "action": step["action"], "result": result, "completed_at": _now()})
        if result.get("status") != "succeeded":
            break
    succeeded = bool(results) and all(item["result"].get("status") == "succeeded" for item in results)
    status = "succeeded" if succeeded else ("partially_failed" if results and any(item["result"].get("status") == "succeeded" for item in results) else "failed")
    now = _now()
    with _ready_engine().begin() as conn:
        conn.execute(text("""UPDATE adaptive_agent_tasks SET results_json=:results,status=:status,updated_at=:now
            WHERE id=:id AND user_id=:uid"""),
            {"results": json.dumps(results), "status": status, "now": now, "id": task_id, "uid": user["id"]})
        row = conn.execute(text("SELECT * FROM adaptive_agent_tasks WHERE id=:id AND user_id=:uid"),
                           {"id": task_id, "uid": user["id"]}).mappings().first()
    return {"task": _public_task(row), "verified": succeeded,
            "message": "Supported steps finished and their results were recorded." if succeeded else "Task did not fully complete; review the recorded step result."}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, request: Request):
    user = require_user(request)
    _ensure_table()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("""UPDATE adaptive_agent_tasks SET status='cancelled',updated_at=:now
            WHERE id=:id AND user_id=:uid AND status IN ('planned','failed','partially_failed')"""),
            {"now": _now(), "id": task_id, "uid": user["id"]})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Cancellable task not found.")
    return {"cancelled": True, "id": task_id, "status": "cancelled"}
