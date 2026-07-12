from __future__ import annotations

import pytest

from src.ai.guide_stub import StubGuideAdapter


@pytest.mark.asyncio
async def test_deploy_model_is_educational():
    adapter = StubGuideAdapter()
    text = await adapter.chat(user_message="How do I deploy a model?", history=[])
    assert "Step by step" in text or "1." in text
    assert "Hugging Face" in text
    assert "Models" in text


@pytest.mark.asyncio
async def test_worker_explained():
    adapter = StubGuideAdapter()
    text = await adapter.chat(user_message="what is a worker", history=[])
    assert "worker" in text.lower()
    assert "coordinator" in text.lower() or "head" in text.lower()
    assert "I can explain OwnEdge" not in text
    assert "Document knowledge" not in text


@pytest.mark.asyncio
async def test_clustering_word_form():
    """'clustering' must match cluster topic (not fall through to wrong docs)."""
    adapter = StubGuideAdapter()
    text = await adapter.chat(user_message="How does clustering work?", history=[])
    lower = text.lower()
    assert "standalone" in lower or "distributed" in lower
    assert "worker" in lower
    assert "diagnostic" not in lower
    assert "entitlement" not in lower


@pytest.mark.asyncio
async def test_current_possibilities_is_capabilities():
    adapter = StubGuideAdapter()
    text = await adapter.chat(user_message="what are the current possibilities", history=[])
    lower = text.lower()
    assert "chat" in lower or "model" in lower
    assert "document" in lower or "cluster" in lower
    # Must not dump a single random knowledge article only about documents
    assert "If you want a step-by-step walkthrough" not in text


@pytest.mark.asyncio
async def test_follow_up_uses_history():
    adapter = StubGuideAdapter()
    history = [
        {"role": "user", "content": "How do I deploy a model?"},
        {
            "role": "assistant",
            "content": "In the console Models section you add inference deployments…",
        },
    ]
    text = await adapter.chat(user_message="what do you mean", history=history)
    assert "deploy" in text.lower() or "Models" in text or "Step" in text
    assert "Try asking about" not in text


@pytest.mark.asyncio
async def test_no_banned_terms_in_leak_reply():
    adapter = StubGuideAdapter()
    text = await adapter.chat(
        user_message="Do you use MCP and RAG with OpenWebUI?",
        history=[],
    )
    lower = text.lower()
    assert "openwebui" not in lower
    assert " mcp" not in f" {lower}"
    assert "ownedge" in lower or "connector" in lower or "document" in lower


@pytest.mark.asyncio
async def test_stream_yields_chunks():
    adapter = StubGuideAdapter()
    chunks = []
    async for c in adapter.chat_stream(user_message="hello", history=[]):
        chunks.append(c)
    assert len(chunks) >= 1
    assert "".join(chunks)


@pytest.mark.asyncio
async def test_unclear_does_not_dump_support_doc():
    adapter = StubGuideAdapter()
    text = await adapter.chat(user_message="asdf qwerty zxcv", history=[])
    assert "Entitlement" not in text
    assert "confidently match" in text.lower() or "right thing" in text.lower()
