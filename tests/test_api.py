from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


SAMPLE_BUNDLE = {
    "bundle_version": 1,
    "appliance_id": "forge-demo-001",
    "submitted_at": "2026-07-07T12:00:00Z",
    "software": {
        "console_version": "dev",
        "controller_version": "dev",
        "support_client_version": "1.0.0",
    },
    "topology": {
        "serving_mode": "distributed",
        "role": "coordinator",
        "node_count": 3,
        "local_node_id": "node-1",
    },
    "health": {
        "state": "DEGRADED",
        "last_error": "reconcile failed",
        "actual": {"exit_code": 1, "log_snippet": "CUDA OOM"},
    },
    "events": [],
    "deployments_summary": [],
    "nodes_summary": [],
}


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_entitlement_free_tier(client):
    res = await client.get("/v1/entitlement/forge-demo-001")
    assert res.status_code == 200
    body = res.json()
    assert body["entitled"] is True
    assert body["tier"] == "free"


@pytest.mark.asyncio
async def test_create_and_poll_ticket(client):
    res = await client.post("/v1/tickets", json=SAMPLE_BUNDLE)
    assert res.status_code == 202
    ticket_id = res.json()["ticket_id"]

    import asyncio

    for _ in range(20):
        poll = await client.get(f"/v1/tickets/{ticket_id}")
        assert poll.status_code == 200
        body = poll.json()
        if body["status"] == "complete":
            assert body["diagnosis"]["verdict"] in (
                "likely_bug",
                "operator_actionable",
                "insufficient_data",
                "unknown",
            )
            return
        await asyncio.sleep(0.05)

    pytest.fail("ticket did not complete in time")


@pytest.mark.asyncio
async def test_denied_appliance(monkeypatch, client):
    monkeypatch.setenv("SUPPORT_DENIED_APPLIANCE_IDS", "denied-001")
    monkeypatch.setenv("SUPPORT_FREE_FOR_ALL", "false")

    bundle = {**SAMPLE_BUNDLE, "appliance_id": "denied-001"}
    res = await client.post("/v1/tickets", json=bundle)
    assert res.status_code == 403
    assert res.json()["error"] == "subscription_required"