"""Durable conversation store using PostgreSQL when DATABASE_URL is set.

SQLite remains available for local development. Hosted deployments should set
DATABASE_URL to a dedicated Adaptive AI PostgreSQL database.
"""
from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy import event


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # Neon and many hosts supply a generic PostgreSQL URL; use psycopg v3.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    path = Path(os.getenv("ADAPTIVE_AI_DB_PATH", "adaptive_ai.sqlite3"))
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + str(path)


@lru_cache(maxsize=1)
def _engine() -> Engine:
    url = _database_url()
    if url.startswith("sqlite:"):
        engine = create_engine(url, connect_args={"timeout": 10})
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()
        return engine
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


def _ensure_schema(engine: Engine) -> None:
    message_id = "INTEGER PRIMARY KEY AUTOINCREMENT" if engine.dialect.name == "sqlite" else "BIGSERIAL PRIMARY KEY"
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        connection.execute(text(f"""
            CREATE TABLE IF NOT EXISTS messages (
                id {message_id},
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """))


def _ready_engine() -> Engine:
    engine = _engine()
    _ensure_schema(engine)
    return engine


def create_conversation() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conversation_id = str(uuid4())
    engine = _ready_engine()
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO conversations(id, created_at, updated_at) VALUES (:id, :created, :updated)"
        ), {"id": conversation_id, "created": now, "updated": now})
    return {"id": conversation_id, "created_at": now, "updated_at": now}


def list_conversations() -> list[dict]:
    engine = _ready_engine()
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT id, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 100"
        )).mappings().all()
    return [dict(row) for row in rows]


def conversation_exists(conversation_id: str) -> bool:
    engine = _ready_engine()
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT 1 FROM conversations WHERE id = :id"
        ), {"id": conversation_id}).first()
    return row is not None


def add_message(conversation_id: str, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    engine = _ready_engine()
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES (:conversation_id, :role, :content, :created_at)"
        ), {"conversation_id": conversation_id, "role": role, "content": content, "created_at": now})
        connection.execute(text(
            "UPDATE conversations SET updated_at = :updated_at WHERE id = :id"
        ), {"updated_at": now, "id": conversation_id})


def get_messages(conversation_id: str, limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    engine = _ready_engine()
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT role, content FROM ("
            "SELECT id, role, content FROM messages WHERE conversation_id = :id "
            "ORDER BY id DESC LIMIT :limit"
            ") recent ORDER BY id ASC"
        ), {"id": conversation_id, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def delete_conversation(conversation_id: str) -> bool:
    engine = _ready_engine()
    with engine.begin() as connection:
        result = connection.execute(text(
            "DELETE FROM conversations WHERE id = :id"
        ), {"id": conversation_id})
        return result.rowcount > 0
