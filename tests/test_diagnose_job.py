from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.ai.errors import CLITransientError
from src.code_context.errors import CodeContextError
from src.jobs import diagnose as diagnose_job
from src.schemas import DiagnosticBundle
from src.vendor.email_alert import USER_SAFE_CODE_CONTEXT_ERROR
from src import tickets

FIXTURE = Path(__file__).parent / "fixtures" / "sample-bundle.json"


@pytest.fixture
def bundle() -> DiagnosticBundle:
    return DiagnosticBundle.model_validate(json.loads(FIXTURE.read_text()))


class _FlakyAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def diagnose(self, *, bundle, code_roots, prompt_template, ticket_id=""):
        self.calls += 1
        if self.calls < 2:
            raise CLITransientError("temporary")
        from src.schemas import DiagnosisResult

        return DiagnosisResult(
            verdict="operator_actionable",
            summary="recovered",
            confidence="medium",
            recommended_actions=["done"],
        )


@pytest.mark.asyncio
async def test_run_diagnosis_retries_transient_errors(bundle, monkeypatch):
    adapter = _FlakyAdapter()
    releases: list[str] = []

    monkeypatch.setattr(diagnose_job, "get_adapter", lambda: adapter)
    monkeypatch.setattr(
        diagnose_job,
        "prepare_code_roots",
        lambda ticket_id, _bundle: [Path(f"/tmp/{ticket_id}/root")],
    )
    monkeypatch.setattr(
        diagnose_job,
        "release_code_roots",
        lambda ticket_id: releases.append(ticket_id),
    )
    monkeypatch.setattr(diagnose_job, "load_prompt_template", lambda: "template")
    monkeypatch.setattr(diagnose_job, "DIAGNOSIS_MAX_RETRIES", 2)
    monkeypatch.setattr(diagnose_job, "DIAGNOSIS_RETRY_BACKOFF_SEC", 0.01)

    ticket_id = await tickets.create_ticket(bundle)
    await diagnose_job.run_diagnosis(ticket_id, bundle)

    ticket = await tickets.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == "complete"
    assert ticket.diagnosis is not None
    assert ticket.diagnosis.summary == "recovered"
    assert adapter.calls == 2
    assert releases == [ticket_id]


@pytest.mark.asyncio
async def test_run_diagnosis_timeout_marks_failed(bundle, monkeypatch):
    class _SlowAdapter:
        async def diagnose(self, *, bundle, code_roots, prompt_template, ticket_id=""):
            await asyncio.sleep(5)
            raise AssertionError("should not complete")

    releases: list[str] = []
    monkeypatch.setattr(diagnose_job, "get_adapter", lambda: _SlowAdapter())
    monkeypatch.setattr(diagnose_job, "prepare_code_roots", lambda ticket_id, _bundle: [])
    monkeypatch.setattr(
        diagnose_job,
        "release_code_roots",
        lambda ticket_id: releases.append(ticket_id),
    )
    monkeypatch.setattr(diagnose_job, "load_prompt_template", lambda: "template")
    monkeypatch.setattr(diagnose_job, "DIAGNOSIS_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(diagnose_job, "DIAGNOSIS_MAX_RETRIES", 0)
    monkeypatch.setattr(diagnose_job, "DIAGNOSIS_RETRY_BACKOFF_SEC", 0.01)

    ticket_id = await tickets.create_ticket(bundle)
    await diagnose_job.run_diagnosis(ticket_id, bundle)

    ticket = await tickets.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == "failed"
    assert "timed out" in (ticket.error or "").lower()
    assert releases == [ticket_id]


@pytest.mark.asyncio
async def test_run_diagnosis_code_context_failure_alerts(bundle, monkeypatch):
    alerts: list[tuple] = []
    adapter_calls = 0

    class _Adapter:
        async def diagnose(self, *, bundle, code_roots, prompt_template, ticket_id=""):
            nonlocal adapter_calls
            adapter_calls += 1
            raise AssertionError("AI should not run")

    def _prepare(_ticket_id, _bundle):
        raise CodeContextError(
            "bad version",
            reason="invalid_version",
            repo_key="appliance-console",
            ref="dev",
        )

    monkeypatch.setattr(diagnose_job, "get_adapter", lambda: _Adapter())
    monkeypatch.setattr(diagnose_job, "prepare_code_roots", _prepare)
    monkeypatch.setattr(diagnose_job, "release_code_roots", lambda _ticket_id: None)
    monkeypatch.setattr(
        diagnose_job,
        "send_code_context_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )
    monkeypatch.setattr(diagnose_job, "load_prompt_template", lambda: "template")

    ticket_id = await tickets.create_ticket(bundle)
    await diagnose_job.run_diagnosis(ticket_id, bundle)

    ticket = await tickets.get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == "failed"
    assert ticket.error == USER_SAFE_CODE_CONTEXT_ERROR
    assert adapter_calls == 0
    assert len(alerts) == 1
    assert alerts[0]["ticket_id"] == ticket_id
    assert alerts[0]["error"].reason == "invalid_version"
