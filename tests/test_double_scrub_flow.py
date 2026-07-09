from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.helpers.contracts import load_contract

BASE = load_contract("diagnostic-bundle.v1.golden.json")


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_scrubbed_bundle_is_accepted(client):
    bundle = {**BASE, "health": {**BASE["health"], "last_error": "Bearer abc.def-ghi leaked"}}
    res = await client.post("/v1/tickets", json=bundle)
    assert res.status_code == 202


@pytest.mark.asyncio
async def test_scrubbed_secret_in_last_error_is_accepted(client):
    bundle = {
        **BASE,
        "health": {
            **BASE["health"],
            "last_error": "failed with hf_abcdefghijklmnopqrstuvwxyz token",
        },
    }
    res = await client.post("/v1/tickets", json=bundle)
    assert res.status_code == 202