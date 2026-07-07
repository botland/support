from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.schemas import DiagnosisResult, DiagnosticBundle, TicketStatusResponse
from src.vendor.github import maybe_create_github_issue, _should_file_issue
from src.vendor.notify import send_ticket_notification

FIXTURE = Path(__file__).parent / "fixtures" / "sample-bundle.json"


def _bundle() -> DiagnosticBundle:
    return DiagnosticBundle.model_validate(json.loads(FIXTURE.read_text()))


def _diagnosis(**kwargs) -> DiagnosisResult:
    base = {
        "verdict": "likely_bug",
        "summary": "Process crashed",
        "confidence": "high",
        "recommended_actions": ["wait"],
        "engineering_notes": "check reconciler",
        "evidence": ["exit_code=1"],
    }
    base.update(kwargs)
    return DiagnosisResult.model_validate(base)


def test_should_file_issue_only_high_confidence_bugs():
    assert _should_file_issue(_diagnosis()) is True
    assert _should_file_issue(_diagnosis(confidence="medium")) is False
    assert _should_file_issue(_diagnosis(verdict="operator_actionable")) is False


@pytest.mark.asyncio
async def test_github_issue_skipped_when_disabled(monkeypatch):
    monkeypatch.delenv("GITHUB_ISSUE_ENABLED", raising=False)
    url = await maybe_create_github_issue(
        ticket_id="t1",
        bundle=_bundle(),
        diagnosis=_diagnosis(),
    )
    assert url is None


@pytest.mark.asyncio
async def test_github_issue_created(monkeypatch):
    monkeypatch.setenv("GITHUB_ISSUE_ENABLED", "true")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "org/repo")

    class _Response:
        status_code = 201

        def json(self):
            return {"html_url": "https://github.com/org/repo/issues/42"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            assert "org/repo" in url
            assert headers["Authorization"] == "Bearer test-token"
            return _Response()

    monkeypatch.setattr("src.vendor.github.httpx.AsyncClient", lambda **kwargs: _Client())

    url = await maybe_create_github_issue(
        ticket_id="t1",
        bundle=_bundle(),
        diagnosis=_diagnosis(),
    )
    assert url == "https://github.com/org/repo/issues/42"


@pytest.mark.asyncio
async def test_webhook_notification(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("SUPPORT_WEBHOOK_URL", "https://hooks.example/support")
    monkeypatch.setenv("SUPPORT_WEBHOOK_SECRET", "secret")

    class _Response:
        status_code = 204

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            calls.append({"url": url, "headers": headers, "json": json})
            return _Response()

    monkeypatch.setattr("src.vendor.notify.httpx.AsyncClient", lambda **kwargs: _Client())

    ticket = TicketStatusResponse(
        ticket_id="t1",
        status="complete",
        diagnosis=_diagnosis(),
        created_at="2026-07-07T12:00:00Z",
        updated_at="2026-07-07T12:01:00Z",
    )
    ok = await send_ticket_notification(ticket=ticket, bundle=_bundle())
    assert ok is True
    assert calls[0]["headers"]["X-Support-Webhook-Secret"] == "secret"
    assert calls[0]["json"]["event"] == "support.ticket.updated"