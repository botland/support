from __future__ import annotations

import json

import pytest

from src.schemas import DiagnosisResult, DiagnosticBundle
from src import tickets
from tests.helpers.contracts import load_contract


@pytest.mark.asyncio
async def test_row_to_status_and_list_projection_match():
    bundle = DiagnosticBundle.model_validate(load_contract("diagnostic-bundle.v1.golden.json"))
    ticket_id = await tickets.create_ticket(bundle)
    diagnosis = DiagnosisResult(
        verdict="likely_bug",
        summary="test",
        confidence="medium",
        recommended_actions=["a"],
    )
    await tickets.update_ticket_status(ticket_id, status="complete", diagnosis=diagnosis)

    status = await tickets.get_ticket(ticket_id)
    assert status is not None
    listed = await tickets.list_tickets_for_appliance(bundle.appliance_id)
    match = next(item for item in listed if item.ticket_id == ticket_id)

    assert status.diagnosis is not None
    assert match.verdict == status.diagnosis.verdict
    assert match.summary == status.diagnosis.summary
    assert match.confidence == status.diagnosis.confidence