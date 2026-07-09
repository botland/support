from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.helpers.contracts import load_contract

SAMPLE_BUNDLE = load_contract("diagnostic-bundle.v1.golden.json")


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("SUPPORT_FREE_FOR_ALL", "false")
    import importlib
    import src.entitlement as entitlement
    import src.billing.stub as billing_stub

    importlib.reload(billing_stub)
    importlib.reload(entitlement)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_ticket_subscription_required(client):
    res = await client.post("/v1/tickets", json=SAMPLE_BUNDLE)
    assert res.status_code == 403
    body = res.json()
    assert body["error"] == "subscription_required"


@pytest.mark.asyncio
async def test_list_tickets_subscription_required(client):
    res = await client.get("/v1/tickets", params={"appliance_id": SAMPLE_BUNDLE["appliance_id"]})
    assert res.status_code == 403
    assert res.json()["error"] == "subscription_required"