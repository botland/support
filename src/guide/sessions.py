from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .. import db
from .settings import guide_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS guide_sessions (
  id TEXT PRIMARY KEY,
  locale TEXT NOT NULL DEFAULT 'en',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS guide_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES guide_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guide_messages_session
  ON guide_messages(session_id, created_at);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | str) -> str:
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


async def init_guide_db() -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


async def create_session(locale: str = "en") -> dict:
    session_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """
        INSERT INTO guide_sessions (id, locale, created_at, updated_at)
        VALUES ($1, $2, $3, $4)
        """,
        session_id,
        locale or "en",
        now,
        now,
    )
    return {"session_id": session_id, "created_at": _iso(now), "locale": locale or "en"}


async def get_session(session_id: str) -> dict | None:
    row = await db.fetchrow(
        "SELECT id, locale, created_at, updated_at FROM guide_sessions WHERE id = $1",
        session_id,
    )
    if row is None:
        return None
    return {
        "session_id": row["id"],
        "locale": row["locale"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
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
    val = await db.fetchval(
        "SELECT COUNT(*) FROM guide_messages WHERE session_id = $1",
        session_id,
    )
    return int(val or 0)


async def add_message(session_id: str, role: str, content: str) -> dict:
    message_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """
        INSERT INTO guide_messages (id, session_id, role, content, created_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        message_id,
        session_id,
        role,
        content,
        now,
    )
    await db.execute(
        "UPDATE guide_sessions SET updated_at = $1 WHERE id = $2",
        now,
        session_id,
    )
    return {
        "message_id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": _iso(now),
    }


async def list_messages(session_id: str, *, limit: int | None = None) -> list[dict]:
    if limit is None:
        limit = guide_settings()["max_history_turns"] * 2
    rows = await db.fetch(
        """
        SELECT id, session_id, role, content, created_at
        FROM guide_messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    messages = [
        {
            "message_id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": _iso(row["created_at"]),
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
