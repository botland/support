from __future__ import annotations

import pytest

from src.ai.errors import CLIPermanentError
from src.jobs import diagnose as diagnose_job
from src.schemas import DiagnosticBundle
from src import tickets
from tests.helpers.contracts import load_contract


@pytest.fixture
def bundle() -> DiagnosticBundle:
    return DiagnosticBundle.model_validate(load_contract("diagnostic-bundle.v1.golden.json"))


@pytest.mark.asyncio
async def test_permanent_and_generic_errors_produce_same_failed_status(bundle, monkeypatch):
    calls: list[str] = []

    async def capture_notify(ticket, bundle):
        calls.append("notify")

    monkeypatch.setattr(diagnose_job, "send_ticket_notification", capture_notify)

    class PermanentAdapter:
        async def diagnose(self, *, bundle, code_roots, prompt_template):
            raise CLIPermanentError("bad")

    monkeypatch.setattr(diagnose_job, "get_adapter", lambda: PermanentAdapter())
    monkeypatch.setattr(diagnose_job, "resolve_code_roots", lambda _bundle: [])
    monkeypatch.setattr(diagnose_job, "load_prompt_template", lambda: "t")

    ticket_id = await tickets.create_ticket(bundle)
    await diagnose_job.run_diagnosis(ticket_id, bundle)
    permanent = await tickets.get_ticket(ticket_id)
    assert permanent is not None
    assert permanent.status == "failed"
    assert permanent.error == "Support analysis could not be completed. Please try again later."

    class BoomAdapter:
        async def diagnose(self, *, bundle, code_roots, prompt_template):
            raise RuntimeError("boom")

    monkeypatch.setattr(diagnose_job, "get_adapter", lambda: BoomAdapter())
    ticket_id_2 = await tickets.create_ticket(bundle)
    await diagnose_job.run_diagnosis(ticket_id_2, bundle)
    generic = await tickets.get_ticket(ticket_id_2)
    assert generic is not None
    assert generic.status == permanent.status
    assert generic.error == permanent.error