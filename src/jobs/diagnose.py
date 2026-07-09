from __future__ import annotations

import asyncio
import logging
import os

from ..ai.errors import CLIPermanentError, CLITransientError
from ..ai.prompt import load_prompt_template
from ..ai.registry import get_adapter
from ..code_context.errors import CodeContextError
from ..code_context.manager import prepare_code_roots, release_code_roots
from ..schemas import DiagnosisResult, DiagnosticBundle
from ..vendor.email_alert import USER_SAFE_CODE_CONTEXT_ERROR, send_code_context_alert
from ..vendor.notify import send_ticket_notification
from ..vendor.workflow import run_post_diagnosis_workflow
from .. import tickets

logger = logging.getLogger(__name__)

DIAGNOSIS_TIMEOUT_SEC = int(os.environ.get("DIAGNOSIS_TIMEOUT_SEC", "180"))
DIAGNOSIS_MAX_RETRIES = int(os.environ.get("DIAGNOSIS_MAX_RETRIES", "2"))
DIAGNOSIS_RETRY_BACKOFF_SEC = float(os.environ.get("DIAGNOSIS_RETRY_BACKOFF_SEC", "2"))


def _keep_ticket_worktrees() -> bool:
    """When true, leave worktrees + _ai artifacts for human investigation."""
    return os.environ.get("SUPPORT_KEEP_TICKET_WORKTREES", "").lower() in (
        "1",
        "true",
        "yes",
    )


async def _notify_failure(ticket_id: str, bundle: DiagnosticBundle) -> None:
    ticket = await tickets.get_ticket(ticket_id)
    if ticket is not None:
        await send_ticket_notification(ticket=ticket, bundle=bundle)


async def run_diagnosis(ticket_id: str, bundle: DiagnosticBundle) -> None:
    await tickets.update_ticket_status(ticket_id, status="diagnosing")
    prompt_template = load_prompt_template()

    try:
        code_roots = await asyncio.to_thread(prepare_code_roots, ticket_id, bundle)
    except CodeContextError as exc:
        logger.error(
            "Code context failed for ticket %s reason=%s repo=%s ref=%s: %s",
            ticket_id,
            exc.reason,
            exc.repo_key,
            exc.ref,
            exc.detail or exc,
        )
        await tickets.update_ticket_status(
            ticket_id,
            status="failed",
            error=USER_SAFE_CODE_CONTEXT_ERROR,
        )
        await asyncio.to_thread(
            send_code_context_alert,
            ticket_id=ticket_id,
            bundle=bundle,
            error=exc,
        )
        await asyncio.to_thread(release_code_roots, ticket_id)
        await _notify_failure(ticket_id, bundle)
        return

    try:
        last_error: Exception | None = None
        for attempt in range(DIAGNOSIS_MAX_RETRIES + 1):
            try:
                adapter = get_adapter()
                result: DiagnosisResult = await asyncio.wait_for(
                    adapter.diagnose(
                        bundle=bundle,
                        code_roots=code_roots,
                        prompt_template=prompt_template,
                        ticket_id=ticket_id,
                    ),
                    timeout=DIAGNOSIS_TIMEOUT_SEC,
                )
                await tickets.update_ticket_status(ticket_id, status="complete", diagnosis=result)
                await run_post_diagnosis_workflow(ticket_id, bundle, result)
                logger.info(
                    "Diagnosis complete for ticket %s (attempt=%s, code_roots=%s)",
                    ticket_id,
                    attempt + 1,
                    len(code_roots),
                )
                return
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Diagnosis timeout for ticket %s (attempt %s/%s)",
                    ticket_id,
                    attempt + 1,
                    DIAGNOSIS_MAX_RETRIES + 1,
                )
            except CLITransientError as exc:
                last_error = exc
                logger.warning(
                    "Transient CLI error for ticket %s (attempt %s/%s): %s",
                    ticket_id,
                    attempt + 1,
                    DIAGNOSIS_MAX_RETRIES + 1,
                    exc,
                )
            except CLIPermanentError as exc:
                logger.error("Permanent CLI error for ticket %s: %s", ticket_id, exc)
                await tickets.update_ticket_status(
                    ticket_id,
                    status="failed",
                    error="Support analysis could not be completed. Please try again later.",
                )
                await _notify_failure(ticket_id, bundle)
                return
            except Exception:
                logger.exception("Diagnosis failed for ticket %s", ticket_id)
                await tickets.update_ticket_status(
                    ticket_id,
                    status="failed",
                    error="Support analysis could not be completed. Please try again later.",
                )
                await _notify_failure(ticket_id, bundle)
                return

            if attempt < DIAGNOSIS_MAX_RETRIES:
                await asyncio.sleep(DIAGNOSIS_RETRY_BACKOFF_SEC * (attempt + 1))

        logger.error(
            "Diagnosis exhausted retries for ticket %s: %s",
            ticket_id,
            last_error,
        )
        await tickets.update_ticket_status(
            ticket_id,
            status="failed",
            error="Support analysis timed out. Please try again later.",
        )
        await _notify_failure(ticket_id, bundle)
    finally:
        if _keep_ticket_worktrees():
            logger.info(
                "Keeping ticket worktrees/artifacts for investigation (SUPPORT_KEEP_TICKET_WORKTREES): %s",
                ticket_id,
            )
        else:
            await asyncio.to_thread(release_code_roots, ticket_id)
