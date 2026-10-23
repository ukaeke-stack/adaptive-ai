"""Small SQLite-backed conversation store for the single-user MVP."""
from datetime import datetime, timezone
import os
import sqlite3
from pathlib import Path
from uuid import uuid4


def _connect():
    path = Path(os.getenv("ADAPTIVE_AI_DB_PATH", "adaptive_ai.sqlite3"))
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    connection.commit()
    return connection


def create_conversation() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conversation_id = str(uuid4())
    with _connect() as connection:
        connection.execute("INSERT INTO conversations(id, created_at, updated_at) VALUES (?, ?, ?)", (conversation_id, now, now))
    return {"id": conversation_id, "created_at": now, "updated_at": now}


def list_conversations() -> list[dict]:
    with _connect() as connection:
        rows = connection.execute("SELECT id, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 100").fetchall()
    return [dict(row) for row in rows]


def conversation_exists(conversation_id: str) -> bool:
    with _connect() as connection:
        return connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone() is not None


def add_message(conversation_id: str, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute("INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)", (conversation_id, role, content, now))
        connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


def get_messages(conversation_id: str, limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    with _connect() as connection:
        rows = connection.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def delete_conversation(conversation_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.rowcount > 0
