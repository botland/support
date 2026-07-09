from __future__ import annotations

import asyncio

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
async def test_ticket_lifecycle_queued_to_complete(client):
    create = await client.post("/v1/tickets", json=SAMPLE_BUNDLE)
    assert create.status_code == 202
    body = create.json()
    assert body["status"] == "queued"
    ticket_id = body["ticket_id"]

    seen = set()
    for _ in range(40):
        poll = await client.get(f"/v1/tickets/{ticket_id}")
        assert poll.status_code == 200
        status = poll.json()["status"]
        seen.add(status)
        if status == "complete":
            assert poll.json()["diagnosis"]["verdict"] in (
                "likely_bug",
                "operator_actionable",
                "insufficient_data",
                "unknown",
            )
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail(f"ticket did not complete; saw statuses={seen}")

    # Stub adapter may complete within a single poll window.
    assert "complete" in seen