from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from . import db
from .schemas import DiagnosisResult, DiagnosticBundle, TicketStatusResponse, TicketSummary

RETENTION_DAYS = int(os.environ.get("SUPPORT_TICKET_RETENTION_DAYS", "30"))
LIST_LIMIT = int(os.environ.get("SUPPORT_TICKET_LIST_LIMIT", "20"))

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  appliance_id TEXT NOT NULL,
  status TEXT NOT NULL,
  bundle_json TEXT NOT NULL,
  diagnosis_json TEXT,
  error TEXT,
  github_issue_url TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_appliance ON tickets(appliance_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at);
"""


async def init_db() -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _retention_cutoff() -> datetime:
    return _now() - timedelta(days=RETENTION_DAYS)


async def create_ticket(bundle: DiagnosticBundle) -> str:
    ticket_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """
        INSERT INTO tickets (id, appliance_id, status, bundle_json, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        ticket_id,
        bundle.appliance_id,
        "queued",
        bundle.model_dump_json(),
        now,
        now,
    )
    return ticket_id


def _row_to_status(row) -> TicketStatusResponse:
    diagnosis = None
    if row["diagnosis_json"]:
        diagnosis = DiagnosisResult.model_validate(json.loads(row["diagnosis_json"]))
    created = row["created_at"]
    updated = row["updated_at"]
    return TicketStatusResponse(
        ticket_id=row["id"],
        status=row["status"],
        diagnosis=diagnosis,
        error=row["error"],
        created_at=created.isoformat() if hasattr(created, "isoformat") else created,
        updated_at=updated.isoformat() if hasattr(updated, "isoformat") else updated,
        github_issue_url=row["github_issue_url"],
    )


async def get_ticket(ticket_id: str) -> TicketStatusResponse | None:
    row = await db.fetchrow(
        """
        SELECT id, status, diagnosis_json, error, github_issue_url, created_at, updated_at
        FROM tickets WHERE id = $1
        """,
        ticket_id,
    )
    if row is None:
        return None
    return _row_to_status(row)


async def list_tickets_for_appliance(appliance_id: str, *, limit: int | None = None) -> list[TicketSummary]:
    max_items = limit or LIST_LIMIT
    cutoff = _retention_cutoff()
    rows = await db.fetch(
        """
        SELECT id, status, diagnosis_json, github_issue_url, created_at, updated_at
        FROM tickets
        WHERE appliance_id = $1 AND created_at >= $2
        ORDER BY created_at DESC
        LIMIT $3
        """,
        appliance_id,
        cutoff,
        max_items,
    )

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
        created = row["created_at"]
        updated = row["updated_at"]
        summaries.append(
            TicketSummary(
                ticket_id=row["id"],
                status=row["status"],
                created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
                updated_at=updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
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
    await db.execute(
        """
        UPDATE tickets
        SET status = $1, diagnosis_json = $2, error = $3, updated_at = $4
        WHERE id = $5
        """,
        status,
        diagnosis_json,
        error,
        now,
        ticket_id,
    )


async def set_github_issue_url(ticket_id: str, url: str) -> None:
    now = _now()
    await db.execute(
        "UPDATE tickets SET github_issue_url = $1, updated_at = $2 WHERE id = $3",
        url,
        now,
        ticket_id,
    )


async def load_bundle(ticket_id: str) -> DiagnosticBundle | None:
    row = await db.fetchrow("SELECT bundle_json FROM tickets WHERE id = $1", ticket_id)
    if row is None:
        return None
    return DiagnosticBundle.model_validate(json.loads(row["bundle_json"]))
