from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.code_context.errors import CodeContextError
from src.schemas import DiagnosticBundle
from src.vendor import email_alert


@pytest.fixture
def bundle() -> DiagnosticBundle:
    raw = json.loads((Path(__file__).parent / "fixtures" / "sample-bundle.json").read_text())
    return DiagnosticBundle.model_validate(raw)


def test_build_alert_body_includes_context(bundle):
    error = CodeContextError(
        "bad ref",
        reason="unknown_ref",
        repo_key="appliance-console",
        ref="deadbeef",
        detail="not found",
    )
    body = email_alert.build_code_context_alert_body(
        ticket_id="t-1",
        bundle=bundle,
        error=error,
    )
    assert "t-1" in body
    assert bundle.appliance_id in body
    assert "unknown_ref" in body
    assert "appliance-console" in body
    assert "deadbeef" in body


def test_send_without_smtp_logs_and_returns_false(bundle, monkeypatch, caplog):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    error = CodeContextError("x", reason="invalid_version", repo_key="appliance-backend", ref="dev")
    with caplog.at_level("ERROR"):
        ok = email_alert.send_code_context_alert(ticket_id="t-2", bundle=bundle, error=error)
    assert ok is False
    assert "SMTP_HOST unset" in caplog.text


def test_send_with_smtp_uses_client(bundle, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "noreply@ownedge.ai")
    monkeypatch.setenv("SUPPORT_ALERT_EMAIL", "support@ownedge.ai")
    monkeypatch.setenv("SMTP_USE_TLS", "false")

    error = CodeContextError("x", reason="fetch_failed", repo_key="appliance-console", ref="abc")

    smtp_instance = MagicMock()
    smtp_instance.__enter__ = MagicMock(return_value=smtp_instance)
    smtp_instance.__exit__ = MagicMock(return_value=False)

    with patch.object(email_alert.smtplib, "SMTP", return_value=smtp_instance) as smtp_cls:
        ok = email_alert.send_code_context_alert(ticket_id="t-3", bundle=bundle, error=error)

    assert ok is True
    smtp_cls.assert_called_once()
    smtp_instance.send_message.assert_called_once()
