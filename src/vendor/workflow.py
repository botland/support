from __future__ import annotations

import logging

from ..schemas import DiagnosisResult, DiagnosticBundle
from .. import tickets
from .github import maybe_create_github_issue
from .notify import send_ticket_notification

logger = logging.getLogger(__name__)


async def run_post_diagnosis_workflow(
    ticket_id: str,
    bundle: DiagnosticBundle,
    diagnosis: DiagnosisResult,
) -> None:
    issue_url = await maybe_create_github_issue(
        ticket_id=ticket_id,
        bundle=bundle,
        diagnosis=diagnosis,
    )
    if issue_url:
        await tickets.set_github_issue_url(ticket_id, issue_url)

    ticket = await tickets.get_ticket(ticket_id)
    if ticket is None:
        return
    await send_ticket_notification(ticket=ticket, bundle=bundle)