"""User-scoped productivity features: reminders, document text tools, and safe workflows.

Workflow execution is deliberately limited to deterministic, side-effect-free actions.
Device permissions are reported as guidance; Android remains the source of truth.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.memory.store import _ready_engine
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/assistant", tags=["assistant productivity"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables() -> None:
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_reminders (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            due_at TEXT, notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
            created_at TEXT NOT NULL)"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_workflows (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            steps_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"""))


class ReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    due_at: str | None = Field(default=None, max_length=64)
    notes: str = Field(default="", max_length=2000)


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=100)
    steps: list[dict] = Field(min_length=1, max_length=10)


_ALLOWED_STEP_TYPES = {"summarize_text", "draft_message", "create_reminder"}


def _validate_steps(steps: list[dict]) -> list[dict]:
    clean = []
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"type", "input", "title", "due_at", "notes"}:
            raise HTTPException(status_code=422, detail="Each workflow step may contain only type, input, title, due_at, and notes.")
        kind = step.get("type")
        if kind not in _ALLOWED_STEP_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported workflow step type.")
        if kind in {"summarize_text", "draft_message"}:
            value = step.get("input", "")
            if not isinstance(value, str) or len(value) > 12000:
                raise HTTPException(status_code=422, detail="Workflow text input must be a string of at most 12000 characters.")
        if kind == "create_reminder":
            title = step.get("title", "")
            if not isinstance(title, str) or not title.strip() or len(title) > 160:
                raise HTTPException(status_code=422, detail="Reminder steps require a title of at most 160 characters.")
        clean.append(step)
    return clean


@router.get("/permissions")
def permission_guidance(request: Request):
    user = require_user(request)
    return {
        "account": {"signed_in": True, "role": user.get("role", "user")},
        "device_permissions": [
            {"permission": "microphone", "purpose": "Voice input", "status": "check_on_device", "revocable_in": "Android app permissions"},
            {"permission": "camera", "purpose": "Photo and video capture", "status": "check_on_device", "revocable_in": "Android app permissions"},
            {"permission": "contacts", "purpose": "Open contacts app; contact contents are not read by this API", "status": "not_requested_by_backend", "revocable_in": "Android app permissions"},
            {"permission": "phone_and_sms", "purpose": "Open dialler or SMS composer; no silent calls or sending", "status": "user_confirmation_required", "revocable_in": "Android app permissions"},
        ],
        "safety": {"plugin_execution": False, "automatic_message_sending": False, "automatic_calls": False, "self_deployment": False},
    }


@router.post("/reminders")
def create_reminder(body: ReminderInput, request: Request):
    user = require_user(request)
    if body.due_at:
        try:
            datetime.fromisoformat(body.due_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="due_at must be an ISO-8601 date/time.") from exc
    _ensure_tables()
    reminder_id, created = str(uuid4()), _now()
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_reminders
            (id,user_id,title,due_at,notes,status,created_at)
            VALUES (:id,:uid,:title,:due,:notes,'active',:created)"""),
            {"id": reminder_id, "uid": user["id"], "title": body.title.strip(),
             "due": body.due_at, "notes": body.notes, "created": created})
    return {"reminder": {"id": reminder_id, "title": body.title.strip(), "due_at": body.due_at,
                         "notes": body.notes, "status": "active", "created_at": created},
            "notification_scheduled": False,
            "message": "Reminder saved. Device notifications require a separate Android notification scheduler."}


@router.get("/reminders")
def list_reminders(request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT id,title,due_at,notes,status,created_at FROM adaptive_reminders
            WHERE user_id=:uid ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at LIMIT 200"""),
            {"uid": user["id"]}).mappings().all()
    return {"reminders": [dict(row) for row in rows]}


@router.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: str, request: Request, status: str = "completed"):
    user = require_user(request)
    if status not in {"active", "completed", "cancelled"}:
        raise HTTPException(status_code=422, detail="Status must be active, completed, or cancelled.")
    _ensure_tables()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("""UPDATE adaptive_reminders SET status=:status
            WHERE id=:id AND user_id=:uid"""), {"status": status, "id": reminder_id, "uid": user["id"]})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"updated": True, "id": reminder_id, "status": status}


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("DELETE FROM adaptive_reminders WHERE id=:id AND user_id=:uid"),
                              {"id": reminder_id, "uid": user["id"]})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"deleted": True, "id": reminder_id}


@router.post("/documents/analyze")
def analyze_document(request: Request, body: dict):
    require_user(request)
    if set(body) - {"text", "task"}:
        raise HTTPException(status_code=422, detail="Only text and task are accepted.")
    value, task = body.get("text"), body.get("task", "summarize")
    if not isinstance(value, str) or not value.strip() or len(value) > 100000:
        raise HTTPException(status_code=422, detail="Document text must contain 1–100000 characters.")
    if task not in {"summarize", "extract_bullets", "count_words"}:
        raise HTTPException(status_code=422, detail="Task must be summarize, extract_bullets, or count_words.")
    words = re.findall(r"\S+", value)
    if task == "count_words":
        result = {"word_count": len(words), "character_count": len(value), "paragraph_count": len([p for p in value.splitlines() if p.strip()])}
    elif task == "extract_bullets":
        result = {"bullets": [line.strip(" \t-*•") for line in value.splitlines() if line.strip()][:100]}
    else:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", value.strip()))
        limit = 5 if len(words) > 120 else 3
        result = {"summary": " ".join(sentences[:limit])[:3000], "word_count": len(words),
                  "note": "Extractive summary generated locally by simple text rules; not an AI-generated semantic summary."}
    return {"task": task, "result": result, "processed_by": "deterministic-local-text-rules"}


@router.post("/workflows")
def create_workflow(body: WorkflowInput, request: Request):
    user = require_user(request)
    steps = _validate_steps(body.steps)
    _ensure_tables()
    workflow_id, created = str(uuid4()), _now()
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_workflows
            (id,user_id,name,steps_json,status,created_at)
            VALUES (:id,:uid,:name,:steps,'draft',:created)"""),
            {"id": workflow_id, "uid": user["id"], "name": body.name.strip(),
             "steps": json.dumps(steps), "created": created})
    return {"workflow": {"id": workflow_id, "name": body.name.strip(), "steps": steps,
                         "status": "draft", "created_at": created},
            "message": "Workflow saved as a draft. No actions have run."}


@router.get("/workflows")
def list_workflows(request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT id,name,steps_json,status,created_at FROM adaptive_workflows
            WHERE user_id=:uid ORDER BY created_at DESC LIMIT 100"""), {"uid": user["id"]}).mappings().all()
    return {"workflows": [{"id": r["id"], "name": r["name"], "steps": json.loads(r["steps_json"]),
                            "status": r["status"], "created_at": r["created_at"]} for r in rows]}


@router.post("/workflows/{workflow_id}/approve")
def approve_workflow(workflow_id: str, request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("""UPDATE adaptive_workflows SET status='approved'
            WHERE id=:id AND user_id=:uid AND status='draft'"""), {"id": workflow_id, "uid": user["id"]})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Draft workflow not found.")
    return {"approved": True, "id": workflow_id, "status": "approved",
            "message": "Approval recorded. Execution is not enabled; review each step before running it."}


@router.post("/workflows/{workflow_id}/preview")
def preview_workflow(workflow_id: str, request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().connect() as conn:
        row = conn.execute(text("""SELECT id,name,steps_json,status FROM adaptive_workflows
            WHERE id=:id AND user_id=:uid"""), {"id": workflow_id, "uid": user["id"]}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    steps = json.loads(row["steps_json"])
    preview = []
    for step in steps:
        if step["type"] == "summarize_text":
            words = re.findall(r"\S+", step.get("input", ""))
            preview.append({"type": step["type"], "word_count": len(words), "will_execute": False})
        elif step["type"] == "draft_message":
            preview.append({"type": step["type"], "draft": step.get("input", ""), "will_send": False})
        else:
            preview.append({"type": step["type"], "title": step["title"], "will_schedule_notification": False})
    return {"id": workflow_id, "status": row["status"], "preview": preview,
            "executed": False, "message": "Preview only. No messages are sent and no reminders are created."}
