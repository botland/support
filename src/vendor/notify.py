from __future__ import annotations

import logging
import os

import httpx

from ..schemas import DiagnosisResult, DiagnosticBundle, TicketStatusResponse

logger = logging.getLogger(__name__)


def _webhook_url() -> str | None:
    url = os.environ.get("SUPPORT_WEBHOOK_URL", "").strip()
    return url or None


async def send_ticket_notification(
    *,
    ticket: TicketStatusResponse,
    bundle: DiagnosticBundle,
) -> bool:
    url = _webhook_url()
    if not url:
        return False

    diagnosis: DiagnosisResult | None = ticket.diagnosis
    payload = {
        "event": "support.ticket.updated",
        "ticket_id": ticket.ticket_id,
        "appliance_id": bundle.appliance_id,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "verdict": diagnosis.verdict if diagnosis else None,
        "confidence": diagnosis.confidence if diagnosis else None,
        "summary": diagnosis.summary if diagnosis else None,
        "github_issue_url": ticket.github_issue_url,
        "user_note": bundle.user_note or None,
        "topology": bundle.topology.model_dump(),
        "health_state": bundle.health.get("state"),
    }

    headers = {"Content-Type": "application/json"}
    secret = os.environ.get("SUPPORT_WEBHOOK_SECRET", "").strip()
    if secret:
        headers["X-Support-Webhook-Secret"] = secret

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            logger.error("Webhook failed for ticket %s: %s", ticket.ticket_id, response.status_code)
            return False
        logger.info("Webhook delivered for ticket %s", ticket.ticket_id)
        return True
    except httpx.HTTPError as exc:
        logger.error("Webhook request failed for ticket %s: %s", ticket.ticket_id, exc)
        return False