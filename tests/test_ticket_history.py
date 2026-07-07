from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.schemas import DiagnosisResult, DiagnosticBundle
from src import tickets

FIXTURE = Path(__file__).parent / "fixtures" / "sample-bundle.json"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_tickets_for_appliance(client):
    bundle = DiagnosticBundle.model_validate(json.loads(FIXTURE.read_text()))
    ticket_id = await tickets.create_ticket(bundle)
    await tickets.update_ticket_status(
        ticket_id,
        status="complete",
        diagnosis=DiagnosisResult(
            verdict="operator_actionable",
            summary="test summary",
            confidence="medium",
            recommended_actions=["step"],
        ),
    )

    res = await client.get("/v1/tickets", params={"appliance_id": bundle.appliance_id})
    assert res.status_code == 200
    body = res.json()
    assert body["appliance_id"] == bundle.appliance_id
    assert len(body["tickets"]) >= 1
    assert body["tickets"][0]["summary"] == "test summary"


@pytest.mark.asyncio
async def test_list_tickets_denied_without_entitlement(monkeypatch, client):
    monkeypatch.setenv("SUPPORT_DENIED_APPLIANCE_IDS", "denied-001")
    monkeypatch.setenv("SUPPORT_FREE_FOR_ALL", "false")
    res = await client.get("/v1/tickets", params={"appliance_id": "denied-001"})
    assert res.status_code == 403