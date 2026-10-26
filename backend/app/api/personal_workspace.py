"""User-scoped notes and to-do items with bounded CRUD and search."""
from __future__ import annotations
import json
import csv
import io
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.memory.store import _ready_engine
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/workspace", tags=["personal workspace"])

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _tables() -> None:
    with _ready_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_notes (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            body TEXT NOT NULL, tags_json TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)"""))
        conn.execute(text("""CREATE INDEX IF NOT EXISTS adaptive_notes_owner_updated
            ON adaptive_notes(user_id, updated_at)"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_todos (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT NOT NULL, due_at TEXT, priority TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""))
        conn.execute(text("""CREATE INDEX IF NOT EXISTS adaptive_todos_owner_status
            ON adaptive_todos(user_id, status, due_at)"""))

class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=100000)
    tags: list[str] = Field(default_factory=list, max_length=30)

class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100000)
    tags: list[str] | None = Field(default=None, max_length=30)

class TodoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    due_at: str | None = Field(default=None, max_length=64)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")

class TodoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: str | None = Field(default=None, max_length=64)
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|cancelled)$")

def _tags(tags: list[str]) -> list[str]:
    if any(not isinstance(t, str) or len(t.strip()) > 40 for t in tags):
        raise HTTPException(status_code=422, detail="Tags must be text up to 40 characters.")
    return list(dict.fromkeys(t.strip() for t in tags if t.strip()))[:30]

@router.post("/notes")
def create_note(body: NoteCreate, request: Request):
    user=require_user(request); _tables(); now=_now(); note_id=str(uuid4()); tags=_tags(body.tags)
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_notes
            (id,user_id,title,body,tags_json,created_at,updated_at)
            VALUES (:id,:uid,:title,:body,:tags,:created,:updated)"""),
            {"id":note_id,"uid":user["id"],"title":body.title.strip(),"body":body.body,
             "tags":json.dumps(tags),"created":now,"updated":now})
    return {"note":{"id":note_id,"title":body.title.strip(),"body":body.body,"tags":tags,"created_at":now,"updated_at":now}}

@router.get("/notes")
def list_notes(request: Request, q: str = "", limit: int = 50):
    user=require_user(request); _tables(); limit=max(1,min(limit,100)); q=q.strip()[:200]
    with _ready_engine().connect() as conn:
        rows=conn.execute(text("""SELECT * FROM adaptive_notes WHERE user_id=:uid
            AND (:q='' OR lower(title) LIKE :pattern OR lower(body) LIKE :pattern)
            ORDER BY updated_at DESC LIMIT :limit"""),
            {"uid":user["id"],"q":q,"pattern":"%"+q.lower()+"%","limit":limit}).mappings().all()
    return {"notes":[{"id":r["id"],"title":r["title"],"body":r["body"],"tags":json.loads(r["tags_json"]),
                      "created_at":r["created_at"],"updated_at":r["updated_at"]} for r in rows]}

@router.get("/notes/{note_id}")
def get_note(note_id: str, request: Request):
    user=require_user(request); _tables()
    with _ready_engine().connect() as conn:
        row=conn.execute(text("SELECT * FROM adaptive_notes WHERE id=:id AND user_id=:uid"),
                         {"id":note_id,"uid":user["id"]}).mappings().first()
    if not row: raise HTTPException(status_code=404,detail="Note not found.")
    return {"note":{"id":row["id"],"title":row["title"],"body":row["body"],"tags":json.loads(row["tags_json"]),
                    "created_at":row["created_at"],"updated_at":row["updated_at"]}}

@router.patch("/notes/{note_id}")
def update_note(note_id: str, body: NoteUpdate, request: Request):
    user=require_user(request); _tables(); changes=body.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(status_code=422,detail="Provide at least one field.")
    if "tags" in changes: changes["tags_json"]=json.dumps(_tags(changes.pop("tags")))
    if "title" in changes and changes["title"] is not None: changes["title"]=changes["title"].strip()
    changes["updated_at"]=_now(); assignments=", ".join(f"{k}=:{k}" for k in changes)
    with _ready_engine().begin() as conn:
        result=conn.execute(text(f"UPDATE adaptive_notes SET {assignments} WHERE id=:id AND user_id=:uid"),
                            {**changes,"id":note_id,"uid":user["id"]})
        if not result.rowcount: raise HTTPException(status_code=404,detail="Note not found.")
    return {"updated":True,"id":note_id}

@router.delete("/notes/{note_id}")
def delete_note(note_id: str, request: Request):
    user=require_user(request); _tables()
    with _ready_engine().begin() as conn:
        result=conn.execute(text("DELETE FROM adaptive_notes WHERE id=:id AND user_id=:uid"),
                            {"id":note_id,"uid":user["id"]})
    if not result.rowcount: raise HTTPException(status_code=404,detail="Note not found.")
    return {"deleted":True,"id":note_id}

@router.post("/todos")
def create_todo(body: TodoCreate, request: Request):
    user=require_user(request); _tables(); now=_now(); todo_id=str(uuid4())
    if body.due_at:
        try:
            dt=datetime.fromisoformat(body.due_at.replace("Z","+00:00"))
            if dt.tzinfo is None: raise ValueError()
        except ValueError as exc: raise HTTPException(status_code=422,detail="due_at must be ISO-8601 with timezone.") from exc
    with _ready_engine().begin() as conn:
        conn.execute(text("""INSERT INTO adaptive_todos
            (id,user_id,title,description,due_at,priority,status,created_at,updated_at)
            VALUES (:id,:uid,:title,:description,:due,:priority,'open',:created,:updated)"""),
            {"id":todo_id,"uid":user["id"],"title":body.title.strip(),"description":body.description,
             "due":body.due_at,"priority":body.priority,"created":now,"updated":now})
    return {"todo":{"id":todo_id,"title":body.title.strip(),"description":body.description,"due_at":body.due_at,
                    "priority":body.priority,"status":"open","created_at":now,"updated_at":now}}

@router.get("/todos")
def list_todos(request: Request, status: str = "all", q: str = "", limit: int = 100):
    user=require_user(request); _tables(); limit=max(1,min(limit,200))
    if status not in {"all","open","in_progress","done","cancelled"}: raise HTTPException(status_code=422,detail="Invalid todo status.")
    q=q.strip()[:200]
    with _ready_engine().connect() as conn:
        rows=conn.execute(text("""SELECT * FROM adaptive_todos WHERE user_id=:uid
            AND (:status='all' OR status=:status)
            AND (:q='' OR lower(title) LIKE :pattern OR lower(description) LIKE :pattern)
            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
            due_at LIMIT :limit"""),
            {"uid":user["id"],"status":status,"q":q,"pattern":"%"+q.lower()+"%","limit":limit}).mappings().all()
    return {"todos":[dict(r) for r in rows]}

@router.patch("/todos/{todo_id}")
def update_todo(todo_id: str, body: TodoUpdate, request: Request):
    user=require_user(request); _tables(); changes=body.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(status_code=422,detail="Provide at least one field.")
    if changes.get("due_at"):
        try:
            dt=datetime.fromisoformat(changes["due_at"].replace("Z","+00:00"))
            if dt.tzinfo is None: raise ValueError()
        except ValueError as exc: raise HTTPException(status_code=422,detail="due_at must be ISO-8601 with timezone.") from exc
    if "title" in changes and changes["title"] is not None: changes["title"]=changes["title"].strip()
    changes["updated_at"]=_now(); assignments=", ".join(f"{k}=:{k}" for k in changes)
    with _ready_engine().begin() as conn:
        result=conn.execute(text(f"UPDATE adaptive_todos SET {assignments} WHERE id=:id AND user_id=:uid"),
                            {**changes,"id":todo_id,"uid":user["id"]})
        if not result.rowcount: raise HTTPException(status_code=404,detail="To-do item not found.")
    return {"updated":True,"id":todo_id}

@router.delete("/todos/{todo_id}")
def delete_todo(todo_id: str, request: Request):
    user=require_user(request); _tables()
    with _ready_engine().begin() as conn:
        result=conn.execute(text("DELETE FROM adaptive_todos WHERE id=:id AND user_id=:uid"),
                            {"id":todo_id,"uid":user["id"]})
    if not result.rowcount: raise HTTPException(status_code=404,detail="To-do item not found.")
    return {"deleted":True,"id":todo_id}


@router.get("/export")
def export_workspace(request: Request, format: str = "json"):
    """Export the signed-in user's notes and to-dos; CSV values are protected from formula injection."""
    user=require_user(request); _tables()
    if format not in {"json","csv"}:
        raise HTTPException(status_code=422,detail="format must be json or csv.")
    with _ready_engine().connect() as conn:
        notes=conn.execute(text("SELECT id,title,body,tags_json,created_at,updated_at FROM adaptive_notes WHERE user_id=:uid ORDER BY updated_at DESC LIMIT 1000"),{"uid":user["id"]}).mappings().all()
        todos=conn.execute(text("SELECT id,title,description,due_at,priority,status,created_at,updated_at FROM adaptive_todos WHERE user_id=:uid ORDER BY updated_at DESC LIMIT 1000"),{"uid":user["id"]}).mappings().all()
    payload={"notes":[{"id":r["id"],"title":r["title"],"body":r["body"],"tags":json.loads(r["tags_json"]),"created_at":r["created_at"],"updated_at":r["updated_at"]} for r in notes],
             "todos":[dict(r) for r in todos],"exported_at":_now()}
    if format=="json":
        return Response(content=json.dumps(payload,ensure_ascii=False,indent=2),media_type="application/json",
                        headers={"Content-Disposition":'attachment; filename="norah-workspace-export.json"'})
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["record_type","id","title","body_or_description","tags","due_at","priority","status","created_at","updated_at"])
    def safe_cell(value):
        value=str(value if value is not None else "")
        return "'"+value if value.startswith(("=","+","-","@","\\t","\\r")) else value
    for note in payload["notes"]:
        writer.writerow([safe_cell(x) for x in ["note",note["id"],note["title"],note["body"],", ".join(note["tags"]),"","","",note["created_at"],note["updated_at"]]])
    for todo in payload["todos"]:
        writer.writerow([safe_cell(x) for x in ["todo",todo["id"],todo["title"],todo["description"],"",todo["due_at"],todo["priority"],todo["status"],todo["created_at"],todo["updated_at"]]])
    return Response(content=output.getvalue(),media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":'attachment; filename="norah-workspace-export.csv"'})
