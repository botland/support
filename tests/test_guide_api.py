from __future__ import annotations

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

# Guide tests use stub adapter
os.environ["GUIDE_AI_ADAPTER"] = "stub"
os.environ.pop("GUIDE_SERVICE_TOKEN", None)
os.environ["GUIDE_REQUIRE_TOKEN"] = "false"

from src.guide.settings import clear_guide_settings_cache
from src.main import app


@pytest.fixture
async def client():
    clear_guide_settings_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _init_guide(monkeypatch):
    from src.guide import sessions, rate_limit
    from src.guide.settings import clear_guide_settings_cache

    clear_guide_settings_cache()
    rate_limit.clear_rate_limits()
    await sessions.init_guide_db()
    yield
    rate_limit.clear_rate_limits()
    clear_guide_settings_cache()


@pytest.mark.asyncio
async def test_create_session_and_message(client):
    res = await client.post("/v1/guide/sessions", json={"locale": "en"})
    assert res.status_code == 201
    session_id = res.json()["session_id"]

    msg = await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "What is Edge?", "locale": "en"},
    )
    assert msg.status_code == 200
    body = msg.json()
    assert body["role"] == "assistant"
    assert "Edge" in body["content"]
    assert body["session_id"] == session_id


@pytest.mark.asyncio
async def test_leak_probe_no_stack_names(client):
    res = await client.post("/v1/guide/sessions", json={})
    session_id = res.json()["session_id"]
    msg = await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "Is this OpenWebUI with vLLM and Ray under the hood?"},
    )
    assert msg.status_code == 200
    content = msg.json()["content"].lower()
    for banned in ("openwebui", "vllm", "\bray\b", "litellm"):
        # reply must not affirm stack brands
        assert "openwebui" not in content
        assert "vllm" not in content
        assert "litellm" not in content
    assert "ownedge" in content or "console" in content or "chat workspace" in content


@pytest.mark.asyncio
async def test_huggingface_ok(client):
    res = await client.post("/v1/guide/sessions", json={})
    session_id = res.json()["session_id"]
    msg = await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "How do I use Hugging Face models?"},
    )
    assert msg.status_code == 200
    content = msg.json()["content"]
    assert "Hugging Face" in content


@pytest.mark.asyncio
async def test_stream_sse(client):
    res = await client.post("/v1/guide/sessions", json={})
    session_id = res.json()["session_id"]
    async with client.stream(
        "POST",
        f"/v1/guide/sessions/{session_id}/messages/stream",
        json={"message": "Hello"},
    ) as response:
        assert response.status_code == 200
        text = ""
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("type") == "token":
                    text += payload["content"]
                if payload.get("type") == "done":
                    assert payload["content"]
                    text = payload["content"]
        assert text
        assert "OwnEdge" in text or "product guide" in text.lower() or "Hello" in text


@pytest.mark.asyncio
async def test_message_too_long(client, monkeypatch):
    monkeypatch.setenv("GUIDE_MAX_MESSAGE_CHARS", "20")
    clear_guide_settings_cache()
    res = await client.post("/v1/guide/sessions", json={})
    session_id = res.json()["session_id"]
    msg = await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "x" * 50},
    )
    assert msg.status_code == 400


@pytest.mark.asyncio
async def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("GUIDE_RATE_LIMIT_PER_HOUR", "2")
    clear_guide_settings_cache()
    from src.guide.rate_limit import clear_rate_limits

    clear_rate_limits()
    res = await client.post("/v1/guide/sessions", json={})
    session_id = res.json()["session_id"]
    for i in range(2):
        r = await client.post(
            f"/v1/guide/sessions/{session_id}/messages",
            json={"message": f"hi {i}"},
        )
        assert r.status_code == 200
    r = await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "one more"},
    )
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_token_required(client, monkeypatch):
    monkeypatch.setenv("GUIDE_SERVICE_TOKEN", "secret-token")
    monkeypatch.setenv("GUIDE_REQUIRE_TOKEN", "true")
    clear_guide_settings_cache()
    denied = await client.post("/v1/guide/sessions", json={})
    assert denied.status_code == 401
    ok = await client.post(
        "/v1/guide/sessions",
        json={},
        headers={"X-Guide-Token": "secret-token"},
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_get_session_history(client):
    res = await client.post("/v1/guide/sessions", json={"locale": "fr"})
    session_id = res.json()["session_id"]
    await client.post(
        f"/v1/guide/sessions/{session_id}/messages",
        json={"message": "Bonjour"},
    )
    detail = await client.get(f"/v1/guide/sessions/{session_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["session_id"] == session_id
    assert len(body["messages"]) >= 2
