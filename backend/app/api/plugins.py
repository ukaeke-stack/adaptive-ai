"""Authenticated plugin proposal API. Generated code is never executed here."""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.memory.store import _ready_engine
from app.security.sessions import require_user
from app.tools.plugin_sandbox import validate_plugin

router = APIRouter(prefix="/v1/plugins", tags=["plugins"])

class PluginProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=48)
    source: str = Field(min_length=1, max_length=12000)

def _ensure_plugin_table():
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_plugin_proposals (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            source TEXT NOT NULL, source_sha256 TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL)"""))

@router.post("/proposals")
def create_proposal(body: PluginProposal, request: Request):
    user = require_user(request)
    try:
        validated = validate_plugin(body.name, body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _ensure_plugin_table()
    plugin_id, created = str(uuid4()), datetime.now(timezone.utc).isoformat()
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_plugin_proposals
            (id,user_id,name,source,source_sha256,status,created_at)
            VALUES (:id,:uid,:name,:source,:digest,'pending_review',:created)"""),
            {"id": plugin_id, "uid": user["id"], "name": validated["name"],
             "source": body.source, "digest": validated["source_sha256"], "created": created})
    return {"plugin": {"id": plugin_id, "name": validated["name"], "status": "pending_review",
                       "source_sha256": validated["source_sha256"], "created_at": created,
                       "executable": False},
            "message": "Proposal stored for review. It cannot run or gain permissions until an isolated runtime and approval workflow are configured."}

@router.get("/proposals")
def list_proposals(request: Request):
    user = require_user(request)
    _ensure_plugin_table()
    with _ready_engine().connect() as conn:
        rows = conn.execute(text("""SELECT id,name,source_sha256,status,created_at
            FROM adaptive_plugin_proposals WHERE user_id=:uid ORDER BY created_at DESC LIMIT 100"""),
            {"uid": user["id"]}).mappings().all()
    return {"plugins": [dict(row) for row in rows]}

@router.get("/proposals/{plugin_id}")
def get_proposal(plugin_id: str, request: Request):
    user = require_user(request)
    _ensure_plugin_table()
    with _ready_engine().connect() as conn:
        row = conn.execute(text("""SELECT id,name,source,source_sha256,status,created_at
            FROM adaptive_plugin_proposals WHERE id=:id AND user_id=:uid"""),
            {"id": plugin_id, "uid": user["id"]}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Plugin proposal not found")
    return {"plugin": dict(row), "executable": False}
