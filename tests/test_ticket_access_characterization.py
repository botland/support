from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.helpers.contracts import load_contract

SAMPLE_BUNDLE = load_contract("diagnostic-bundle.v1.golden.json")


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_ticket_without_appliance_id_returns_200_characterization(client):
    """REFACTO P0: entitlement check will invert this — update test when fixed."""
    create = await client.post("/v1/tickets", json=SAMPLE_BUNDLE)
    assert create.status_code == 202
    ticket_id = create.json()["ticket_id"]

    poll = await client.get(f"/v1/tickets/{ticket_id}")
    assert poll.status_code == 200
    assert poll.json()["ticket_id"] == ticket_id


@pytest.mark.asyncio
async def test_get_ticket_for_unknown_id_returns_404(client):
    res = await client.get("/v1/tickets/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404