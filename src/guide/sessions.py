from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from .settings import guide_settings

# Share the support DB file by default (separate tables).
DB_PATH = Path(os.environ.get("SUPPORT_DB_PATH", "/data/support.db"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def init_guide_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guide_sessions (
                id TEXT PRIMARY KEY,
                locale TEXT NOT NULL DEFAULT 'en',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guide_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES guide_sessions(id)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_guide_messages_session "
            "ON guide_messages(session_id, created_at)"
        )
        await db.commit()


async def create_session(locale: str = "en") -> dict:
    session_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO guide_sessions (id, locale, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, locale or "en", now, now),
        )
        await db.commit()
    return {"session_id": session_id, "created_at": now, "locale": locale or "en"}


async def get_session(session_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, locale, created_at, updated_at FROM guide_sessions WHERE id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "session_id": row["id"],
        "locale": row["locale"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _is_expired(created_at: str) -> bool:
    ttl_hours = guide_settings()["session_ttl_hours"]
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return _now() - created > timedelta(hours=ttl_hours)


async def ensure_session_active(session_id: str) -> dict | None:
    session = await get_session(session_id)
    if session is None:
        return None
    if _is_expired(session["created_at"]):
        return None
    return session


async def count_messages(session_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM guide_messages WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def add_message(session_id: str, role: str, content: str) -> dict:
    message_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO guide_messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, now),
        )
        await db.execute(
            "UPDATE guide_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    return {
        "message_id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": now,
    }


async def list_messages(session_id: str, *, limit: int | None = None) -> list[dict]:
    if limit is None:
        limit = guide_settings()["max_history_turns"] * 2
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM guide_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    messages = [
        {
            "message_id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    if limit and len(messages) > limit:
        return messages[-limit:]
    return messages


async def history_for_prompt(session_id: str) -> list[dict]:
    """Return last N user/assistant pairs for the model (role + content only)."""
    turns = guide_settings()["max_history_turns"]
    messages = await list_messages(session_id, limit=turns * 2)
    return [{"role": m["role"], "content": m["content"]} for m in messages]
