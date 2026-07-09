from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import RATE_LIMIT_PER_HOUR, _ticket_counts, app
from tests.helpers.contracts import load_contract

SAMPLE_BUNDLE = load_contract("diagnostic-bundle.v1.golden.json")


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_rate_limit():
    _ticket_counts.clear()
    yield
    _ticket_counts.clear()


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_threshold(client, monkeypatch):
    monkeypatch.setenv("SUPPORT_RATE_LIMIT_PER_HOUR", "2")
    import importlib
    import src.main as main_module

    importlib.reload(main_module)
    main_module._ticket_counts.clear()

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(2):
            res = await ac.post("/v1/tickets", json=SAMPLE_BUNDLE)
            assert res.status_code == 202
        res = await ac.post("/v1/tickets", json=SAMPLE_BUNDLE)
        assert res.status_code == 429


def test_rate_limit_window_is_one_hour_characterization():
    import inspect
    import src.main as main_module

    source = inspect.getsource(main_module._rate_limit_ok)
    assert "3600" in source


def test_default_rate_limit_from_env():
    assert RATE_LIMIT_PER_HOUR >= 1