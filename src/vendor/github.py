from __future__ import annotations

import logging
import os

import httpx

from ..schemas import DiagnosisResult, DiagnosticBundle

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("GITHUB_ISSUE_ENABLED", "").lower() in ("1", "true", "yes")


def _should_file_issue(diagnosis: DiagnosisResult) -> bool:
    min_confidence = os.environ.get("GITHUB_ISSUE_MIN_CONFIDENCE", "high").lower()
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    return (
        diagnosis.verdict == "likely_bug"
        and confidence_rank.get(diagnosis.confidence, 0) >= confidence_rank.get(min_confidence, 2)
    )


def _build_issue_body(bundle: DiagnosticBundle, diagnosis: DiagnosisResult, ticket_id: str) -> str:
    lines = [
        "## Support ticket",
        f"- Ticket ID: `{ticket_id}`",
        f"- Appliance ID: `{bundle.appliance_id}`",
        f"- Submitted: {bundle.submitted_at}",
        f"- Controller version: {bundle.software.controller_version}",
        f"- Console version: {bundle.software.console_version}",
        "",
        "## Diagnosis",
        f"**Verdict:** {diagnosis.verdict}",
        f"**Confidence:** {diagnosis.confidence}",
        "",
        diagnosis.summary,
        "",
    ]
    if diagnosis.engineering_notes:
        lines.extend(["## Engineering notes", diagnosis.engineering_notes, ""])
    if diagnosis.evidence:
        lines.append("## Evidence")
        lines.extend(f"- {item}" for item in diagnosis.evidence)
    if bundle.user_note:
        lines.extend(["", "## Admin note", bundle.user_note])
    return "\n".join(lines)


async def maybe_create_github_issue(
    *,
    ticket_id: str,
    bundle: DiagnosticBundle,
    diagnosis: DiagnosisResult,
) -> str | None:
    if not _enabled():
        return None
    if not _should_file_issue(diagnosis):
        return None

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if not token or not repo:
        logger.warning("GitHub issue filing enabled but GITHUB_TOKEN or GITHUB_REPO missing")
        return None

    title = (
        f"[Support] {bundle.appliance_id}: {diagnosis.summary[:80]}"
        if diagnosis.summary
        else f"[Support] {bundle.appliance_id} ({ticket_id[:8]})"
    )
    body = _build_issue_body(bundle, diagnosis, ticket_id)
    labels = [
        label.strip()
        for label in os.environ.get("GITHUB_ISSUE_LABELS", "support,appliance").split(",")
        if label.strip()
    ]

    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            logger.error("GitHub issue creation failed: %s %s", response.status_code, response.text[:300])
            return None
        issue_url = response.json().get("html_url")
        logger.info("Created GitHub issue for ticket %s: %s", ticket_id, issue_url)
        return issue_url
    except httpx.HTTPError as exc:
        logger.error("GitHub issue request failed for ticket %s: %s", ticket_id, exc)
        return None