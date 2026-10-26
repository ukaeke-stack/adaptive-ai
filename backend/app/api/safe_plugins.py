"""Declarative plugin lifecycle. Only allow-listed built-in capabilities may be activated."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.memory.store import _ready_engine
from app.security.sessions import require_user
from app.tools.registry import get_tool
from app.tools.builtin.text_tools import EXTENDED_ACTIONS

router = APIRouter(prefix="/v1/plugin-runtime", tags=["safe plugin runtime"])
ALLOWED = frozenset(EXTENDED_ACTIONS) | {"count_words", "extract_bullets", "draft_message"}

def _tables():
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_safe_plugins (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
        capabilities_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
        reviewed_by TEXT, reviewed_at TEXT)"""))

class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=48)
    capabilities: list[str] = Field(min_length=1, max_length=20)

@router.post("/proposals")
def propose(body: Manifest, request: Request):
    user = require_user(request)
    if len(set(body.capabilities)) != len(body.capabilities) or set(body.capabilities) - ALLOWED:
        raise HTTPException(status_code=422, detail="Only unique allow-listed built-in capabilities are accepted.")
    _tables()
    pid, now = str(uuid4()), datetime.now(timezone.utc).isoformat()
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_safe_plugins
        (id,user_id,name,capabilities_json,status,created_at)
        VALUES (:id,:uid,:name,:caps,'pending_review',:at)"""),
        {"id":pid,"uid":user["id"],"name":body.name.strip(),"caps":json.dumps(body.capabilities),"at":now})
    return {"id":pid,"name":body.name.strip(),"capabilities":body.capabilities,"status":"pending_review","executable":False}

@router.get("/plugins")
def list_plugins(request: Request):
    user = require_user(request)
    _tables()
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT id,name,capabilities_json,status,created_at,reviewed_at
        FROM adaptive_safe_plugins WHERE user_id=:uid ORDER BY created_at DESC LIMIT 100"""),
        {"uid":user["id"]}).mappings().all()
    return {"plugins":[{"id":r["id"],"name":r["name"],"capabilities":json.loads(r["capabilities_json"]),
    "status":r["status"],"created_at":r["created_at"],"reviewed_at":r["reviewed_at"],
    "executable":r["status"]=="active"} for r in rows]}

@router.post("/plugins/{plugin_id}/approve")
def approve(plugin_id: str, request: Request):
    user = require_user(request)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the platform owner can approve plugins.")
    _tables()
    now = datetime.now(timezone.utc).isoformat()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("""UPDATE adaptive_safe_plugins SET status='approved',
        reviewed_by=:reviewer,reviewed_at=:at WHERE id=:id AND status='pending_review'"""),
        {"reviewer":user["id"],"at":now,"id":plugin_id})
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Pending plugin proposal not found.")
    return {"approved":True,"id":plugin_id,"status":"approved","activation_required":True}

@router.post("/plugins/{plugin_id}/activate")
def activate(plugin_id: str, request: Request):
    user = require_user(request)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the platform owner can activate plugins.")
    _tables()
    with _ready_engine().begin() as conn:
        result = conn.execute(text("UPDATE adaptive_safe_plugins SET status='active' WHERE id=:id AND status='approved'"), {"id":plugin_id})
    if not result.rowcount:
        raise HTTPException(status_code=409, detail="Plugin must be approved before activation.")
    return {"activated":True,"id":plugin_id,"status":"active","execution_model":"allow-listed built-ins only","user_code_execution":False}

class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str
    input: str = Field(default="", max_length=120000)
    arguments: dict = Field(default_factory=dict, max_length=40)

@router.post("/plugins/{plugin_id}/run")
def run_plugin(plugin_id: str, body: RunInput, request: Request):
    import re
    user = require_user(request)
    _tables()
    with _ready_engine().connect() as conn:
        row = conn.execute(text("""SELECT capabilities_json,status FROM adaptive_safe_plugins
        WHERE id=:id AND user_id=:uid"""), {"id":plugin_id,"uid":user["id"]}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found.")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail="Plugin is not active.")
    if body.capability not in json.loads(row["capabilities_json"]):
        raise HTTPException(status_code=403, detail="Capability was not approved for this plugin.")
    value = body.input
    if body.capability == "count_words":
        result = {"word_count":len(value.split()),"character_count":len(value)}
    elif body.capability == "extract_bullets":
        result = {"bullets":[line.strip(" -*•") for line in value.splitlines() if line.strip()][:100]}
    elif body.capability == "draft_message":
        result = {"draft":value,"sent":False}
    else:
        tool = get_tool(body.capability)
        if tool is None:
            raise HTTPException(status_code=422, detail="Capability is not registered in the server tool allowlist.")
        arguments = dict(body.arguments)
        if value and "input" not in arguments:
            arguments["input"] = value
        try:
            result = tool(arguments)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"plugin_id":plugin_id,"capability":body.capability,"result":result,
            "executed":True,"execution_mode":"fixed-built-in-allowlist","user_code_executed":False}
