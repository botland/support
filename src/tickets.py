from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from .schemas import DiagnosisResult, DiagnosticBundle, TicketStatusResponse, TicketSummary

DB_PATH = Path(os.environ.get("SUPPORT_DB_PATH", "/data/support.db"))
RETENTION_DAYS = int(os.environ.get("SUPPORT_TICKET_RETENTION_DAYS", "30"))
LIST_LIMIT = int(os.environ.get("SUPPORT_TICKET_LIST_LIMIT", "20"))


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                appliance_id TEXT NOT NULL,
                status TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                diagnosis_json TEXT,
                error TEXT,
                github_issue_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_appliance ON tickets(appliance_id)"
        )
        await _migrate_columns(db)
        await db.commit()


async def _migrate_columns(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(tickets)") as cursor:
        rows = await cursor.fetchall()
    columns = {row[1] for row in rows}
    if "github_issue_url" not in columns:
        await db.execute("ALTER TABLE tickets ADD COLUMN github_issue_url TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retention_cutoff() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    return cutoff.isoformat()


async def create_ticket(bundle: DiagnosticBundle) -> str:
    ticket_id = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO tickets (id, appliance_id, status, bundle_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, bundle.appliance_id, "queued", bundle.model_dump_json(), now, now),
        )
        await db.commit()
    return ticket_id


def _row_to_status(row: aiosqlite.Row) -> TicketStatusResponse:
    diagnosis = None
    if row["diagnosis_json"]:
        diagnosis = DiagnosisResult.model_validate(json.loads(row["diagnosis_json"]))
    return TicketStatusResponse(
        ticket_id=row["id"],
        status=row["status"],
        diagnosis=diagnosis,
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        github_issue_url=row["github_issue_url"],
    )


async def get_ticket(ticket_id: str) -> TicketStatusResponse | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, status, diagnosis_json, error, github_issue_url, created_at, updated_at
            FROM tickets WHERE id = ?
            """,
            (ticket_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_status(row)


async def list_tickets_for_appliance(appliance_id: str, *, limit: int | None = None) -> list[TicketSummary]:
    max_items = limit or LIST_LIMIT
    cutoff = _retention_cutoff()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, status, diagnosis_json, github_issue_url, created_at, updated_at
            FROM tickets
            WHERE appliance_id = ? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (appliance_id, cutoff, max_items),
        ) as cursor:
            rows = await cursor.fetchall()

    summaries: list[TicketSummary] = []
    for row in rows:
        verdict = None
        summary = None
        confidence = None
        if row["diagnosis_json"]:
            diagnosis = DiagnosisResult.model_validate(json.loads(row["diagnosis_json"]))
            verdict = diagnosis.verdict
            summary = diagnosis.summary
            confidence = diagnosis.confidence
        summaries.append(
            TicketSummary(
                ticket_id=row["id"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                verdict=verdict,
                summary=summary,
                confidence=confidence,
                github_issue_url=row["github_issue_url"],
            )
        )
    return summaries


async def update_ticket_status(
    ticket_id: str,
    *,
    status: str,
    diagnosis: DiagnosisResult | None = None,
    error: str | None = None,
) -> None:
    now = _now()
    diagnosis_json = diagnosis.model_dump_json() if diagnosis else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE tickets
            SET status = ?, diagnosis_json = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, diagnosis_json, error, now, ticket_id),
        )
        await db.commit()


async def set_github_issue_url(ticket_id: str, url: str) -> None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET github_issue_url = ?, updated_at = ? WHERE id = ?",
            (url, now, ticket_id),
        )
        await db.commit()


async def load_bundle(ticket_id: str) -> DiagnosticBundle | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT bundle_json FROM tickets WHERE id = ?",
            (ticket_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return DiagnosticBundle.model_validate(json.loads(row["bundle_json"]))