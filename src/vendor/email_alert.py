from __future__ import annotations

import json
import logging
import os
import smtplib
from email.message import EmailMessage

from ..code_context.errors import CodeContextError
from ..redact import scrub_dict
from ..schemas import DiagnosticBundle

logger = logging.getLogger(__name__)

DEFAULT_ALERT_TO = "support@ownedge.ai"
USER_SAFE_CODE_CONTEXT_ERROR = (
    "Support could not load matching product source for this appliance version."
)


def _alert_to() -> str:
    return os.environ.get("SUPPORT_ALERT_EMAIL", DEFAULT_ALERT_TO).strip() or DEFAULT_ALERT_TO


def _smtp_config() -> dict[str, str | int] | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None
    port_raw = os.environ.get("SMTP_PORT", "587").strip() or "587"
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    return {
        "host": host,
        "port": port,
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "from_addr": os.environ.get("SMTP_FROM", "").strip() or "noreply@ownedge.ai",
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
    }


def build_code_context_alert_body(
    *,
    ticket_id: str,
    bundle: DiagnosticBundle,
    error: CodeContextError,
) -> str:
    scrubbed = scrub_dict(bundle.model_dump())
    lines = [
        "Code context preparation failed for a support ticket.",
        "",
        f"ticket_id: {ticket_id}",
        f"appliance_id: {bundle.appliance_id}",
        f"console_version: {bundle.software.console_version}",
        f"controller_version: {bundle.software.controller_version}",
        f"reason: {error.reason}",
        f"repo_key: {error.repo_key or '-'}",
        f"ref: {error.ref or '-'}",
        f"detail: {error.detail or str(error)}",
        "",
        f"topology: {bundle.topology.model_dump()}",
        f"health_state: {bundle.health.get('state')}",
        f"last_error: {bundle.health.get('last_error')}",
        f"user_note: {bundle.user_note or '(none)'}",
        "",
        "redacted_bundle_json:",
        json.dumps(scrubbed, indent=2, default=str)[:50_000],
    ]
    return "\n".join(lines)


def send_code_context_alert(
    *,
    ticket_id: str,
    bundle: DiagnosticBundle,
    error: CodeContextError,
) -> bool:
    """Email ops about a code-context failure. Returns True if SMTP accepted the message."""
    subject = f"[support] code context failed for ticket {ticket_id} ({bundle.appliance_id})"
    body = build_code_context_alert_body(ticket_id=ticket_id, bundle=bundle, error=error)
    to_addr = _alert_to()
    smtp = _smtp_config()

    if smtp is None:
        logger.error(
            "Code context alert not sent (SMTP_HOST unset). to=%s ticket=%s reason=%s detail=%s",
            to_addr,
            ticket_id,
            error.reason,
            error.detail or str(error),
        )
        logger.error("Alert body:\n%s", body[:4000])
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = str(smtp["from_addr"])
    message["To"] = to_addr
    message.set_content(body)

    try:
        with smtplib.SMTP(str(smtp["host"]), int(smtp["port"]), timeout=30) as client:
            if smtp["use_tls"]:
                client.starttls()
            user = str(smtp["user"])
            password = str(smtp["password"])
            if user:
                client.login(user, password)
            client.send_message(message)
        logger.info("Code context alert emailed to %s for ticket %s", to_addr, ticket_id)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Failed to send code context alert for ticket %s: %s", ticket_id, exc)
        return False
