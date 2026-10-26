"""Persistent, user-scoped scheduled automations with bounded actions and execution history.

This scheduler only runs allowlisted local actions against saved input. It does not send
messages, publish content, place calls, or perform payments. Each run is persisted.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.memory.store import _ready_engine
from app.security.sessions import require_user
from app.tools.builtin.text_tools import EXTENDED_ACTIONS, execute_extended

router = APIRouter(prefix="/v1/automations", tags=["scheduled automations"])
MIN_INTERVAL = 60
MAX_INTERVAL = 365 * 24 * 60 * 60
MAX_INPUT = 120_000
_worker_task: asyncio.Task | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="next_run_at must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="next_run_at must include a timezone offset.")
    return parsed.astimezone(timezone.utc)


def _ensure_tables() -> None:
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_automations (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            action TEXT NOT NULL, input_json TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
            next_run_at TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            max_retries INTEGER NOT NULL DEFAULT 2, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, last_status TEXT NOT NULL DEFAULT 'never_run')"""))
        conn.execute(text("""CREATE INDEX IF NOT EXISTS adaptive_automations_due
            ON adaptive_automations(enabled, next_run_at)"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_automation_runs (
            id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, user_id TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT NOT NULL, status TEXT NOT NULL,
            attempt INTEGER NOT NULL, result_json TEXT NOT NULL, error_text TEXT NOT NULL DEFAULT '')"""))
        conn.execute(text("""CREATE INDEX IF NOT EXISTS adaptive_automation_runs_owner
            ON adaptive_automation_runs(user_id, automation_id, started_at)"""))


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    action: str = Field(min_length=2, max_length=80)
    input: dict = Field(default_factory=dict)
    interval_seconds: int = Field(ge=MIN_INTERVAL, le=MAX_INTERVAL)
    next_run_at: str
    max_retries: int = Field(default=2, ge=0, le=5)


class AutomationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    interval_seconds: int | None = Field(default=None, ge=MIN_INTERVAL, le=MAX_INTERVAL)
    next_run_at: str | None = None
    max_retries: int | None = Field(default=None, ge=0, le=5)


def _validate_action(action: str, args: dict) -> None:
    if action not in EXTENDED_ACTIONS:
        raise HTTPException(status_code=422, detail="Only registered bounded local actions can be scheduled.")
    try:
        encoded = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Action input must be JSON data.") from exc
    if len(encoded) > MAX_INPUT:
        raise HTTPException(status_code=413, detail="Automation input exceeds the size limit.")


def _public(row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "action": row["action"],
        "input": json.loads(row["input_json"]), "interval_seconds": row["interval_seconds"],
        "next_run_at": row["next_run_at"], "enabled": bool(row["enabled"]),
        "max_retries": row["max_retries"], "last_status": row["last_status"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


@router.post("")
def create_automation(body: AutomationCreate, request: Request):
    user = require_user(request)
    _ensure_tables()
    _validate_action(body.action, body.input)
    next_run = _parse(body.next_run_at)
    if next_run <= _now():
        raise HTTPException(status_code=422, detail="next_run_at must be in the future.")
    now = _iso(_now())
    identifier = str(uuid4())
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_automations
            (id,user_id,name,action,input_json,interval_seconds,next_run_at,enabled,max_retries,
             created_at,updated_at,last_status)
            VALUES (:id,:uid,:name,:action,:input,:interval,:next,1,:retries,:created,:updated,'never_run')"""),
            {"id": identifier, "uid": user["id"], "name": body.name.strip(),
             "action": body.action, "input": json.dumps(body.input, ensure_ascii=False),
             "interval": body.interval_seconds, "next": _iso(next_run),
             "retries": body.max_retries, "created": now, "updated": now})
        row = conn.execute(text("SELECT * FROM adaptive_automations WHERE id=:id AND user_id=:uid"),
                           {"id": identifier, "uid": user["id"]}).mappings().first()
    return {"automation": _public(row), "message": "Automation saved. Scheduled execution runs only registered bounded local actions."}


@router.get("")
def list_automations(request: Request, limit: int = 50):
    user = require_user(request)
    _ensure_tables()
    limit = max(1, min(limit, 100))
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT * FROM adaptive_automations
            WHERE user_id=:uid ORDER BY updated_at DESC LIMIT :limit"""),
            {"uid": user["id"], "limit": limit}).mappings().all()
    return {"automations": [_public(row) for row in rows]}


@router.patch("/{automation_id}")
def update_automation(automation_id: str, body: AutomationUpdate, request: Request):
    user = require_user(request)
    _ensure_tables()
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    if changes.get("next_run_at") is not None:
        next_run = _parse(changes["next_run_at"])
        if next_run <= _now():
            raise HTTPException(status_code=422, detail="next_run_at must be in the future.")
        changes["next_run_at"] = _iso(next_run)
    if "enabled" in changes:
        changes["enabled"] = 1 if changes["enabled"] else 0
    changes["updated_at"] = _iso(_now())
    assignments = ", ".join(f"{key}=:{key}" for key in changes)
    params = {**changes, "id": automation_id, "uid": user["id"]}
    with _ready_engine().begin() as conn:
        result = conn.execute(text(f"UPDATE adaptive_automations SET {assignments} WHERE id=:id AND user_id=:uid"), params)
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Automation not found.")
        row = conn.execute(text("SELECT * FROM adaptive_automations WHERE id=:id AND user_id=:uid"),
                           {"id": automation_id, "uid": user["id"]}).mappings().first()
    return {"automation": _public(row)}


@router.delete("/{automation_id}")
def delete_automation(automation_id: str, request: Request):
    user = require_user(request)
    _ensure_tables()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("DELETE FROM adaptive_automations WHERE id=:id AND user_id=:uid"),
                              {"id": automation_id, "uid": user["id"]})
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Automation not found.")
        conn.execute(text("DELETE FROM adaptive_automation_runs WHERE automation_id=:id AND user_id=:uid"),
                     {"id": automation_id, "uid": user["id"]})
    return {"deleted": True, "id": automation_id}


@router.get("/{automation_id}/runs")
def automation_runs(automation_id: str, request: Request, limit: int = 50):
    user = require_user(request)
    _ensure_tables()
    limit = max(1, min(limit, 100))
    with _ready_engine().connect() as conn:
        exists = conn.execute(text("SELECT id FROM adaptive_automations WHERE id=:id AND user_id=:uid"),
                              {"id": automation_id, "uid": user["id"]}).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Automation not found.")
        rows = conn.execute(text("""SELECT * FROM adaptive_automation_runs
            WHERE automation_id=:id AND user_id=:uid ORDER BY started_at DESC LIMIT :limit"""),
            {"id": automation_id, "uid": user["id"], "limit": limit}).mappings().all()
    return {"runs": [{"id": r["id"], "started_at": r["started_at"], "finished_at": r["finished_at"],
                      "status": r["status"], "attempt": r["attempt"],
                      "result": json.loads(r["result_json"]), "error": r["error_text"]} for r in rows]}


def _claim_due():
    """Atomically claim due rows to reduce duplicate execution across worker processes."""
    now = _iso(_now())
    with _ready_engine().begin() as conn:
        due = conn.execute(text("""SELECT * FROM adaptive_automations
            WHERE enabled=1 AND next_run_at<=:now ORDER BY next_run_at LIMIT 20"""), {"now": now}).mappings().all()
        claimed = []
        for row in due:
            next_at = _iso(_now() + timedelta(seconds=row["interval_seconds"]))
            result = conn.execute(text("""UPDATE adaptive_automations SET next_run_at=:next,
                updated_at=:now,last_status='running'
                WHERE id=:id AND enabled=1 AND next_run_at=:old_next"""),
                {"next": next_at, "now": now, "id": row["id"], "old_next": row["next_run_at"]})
            if result.rowcount:
                claimed.append(dict(row))
    return claimed


def _run_one(row: dict) -> None:
    started = _iso(_now())
    final = {"status": "failed", "message": "Action failed."}
    error = ""
    attempts = row["max_retries"] + 1
    for attempt in range(1, attempts + 1):
        try:
            result = execute_extended({"action": row["action"], **json.loads(row["input_json"])})
            if result is None:
                raise ValueError("Action is not implemented.")
            final = result
            error = result.get("message", "") if result.get("status") != "succeeded" else ""
            if result.get("status") == "succeeded":
                break
        except Exception as exc:
            final = {"status": "failed", "message": "Automation action failed."}
            error = str(exc)[:1000]
        if attempt < attempts:
            continue
    status = "succeeded" if final.get("status") == "succeeded" else "failed"
    finished = _iso(_now())
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_automation_runs
            (id,automation_id,user_id,started_at,finished_at,status,attempt,result_json,error_text)
            VALUES (:id,:automation,:uid,:started,:finished,:status,:attempt,:result,:error)"""),
            {"id": str(uuid4()), "automation": row["id"], "uid": row["user_id"],
             "started": started, "finished": finished, "status": status,
             "attempt": attempt, "result": json.dumps(final, ensure_ascii=False), "error": error})
        conn.execute(text("UPDATE adaptive_automations SET last_status=:status,updated_at=:now WHERE id=:id AND user_id=:uid"),
                     {"status": status, "now": finished, "id": row["id"], "uid": row["user_id"]})


async def _worker_loop():
    while True:
        try:
            _ensure_tables()
            rows = await asyncio.to_thread(_claim_due)
            for row in rows:
                await asyncio.to_thread(_run_one, row)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The next loop retries after the short sleep; never crash the API process.
            pass
        await asyncio.sleep(15)


def start_automation_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _ensure_tables()
        _worker_task = asyncio.create_task(_worker_loop())


async def stop_automation_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
