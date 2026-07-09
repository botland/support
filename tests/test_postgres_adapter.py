from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.billing.postgres import PostgresBillingAdapter
from src.schemas import EntitlementResponse


@pytest.mark.asyncio
async def test_postgres_adapter_entitled_for_ai_assisted_support():
    adapter = PostgresBillingAdapter()
    row = {"status": "active", "trial_ends_at": None}

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(adapter, "_get_pool", AsyncMock(return_value=pool)):
        result = await adapter.check_entitlement("NC-STUDIO-TEST01")

    assert result == EntitlementResponse(entitled=True, tier="paid")


@pytest.mark.asyncio
async def test_postgres_adapter_denied_when_only_priority_support():
    adapter = PostgresBillingAdapter()

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=1)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(adapter, "_get_pool", AsyncMock(return_value=pool)):
        result = await adapter.check_entitlement("NC-STUDIO-TEST01")

    assert result.entitled is False
    assert "AI-assisted" in (result.message or "")


@pytest.mark.asyncio
async def test_postgres_adapter_denied_for_unknown_appliance():
    adapter = PostgresBillingAdapter()

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(adapter, "_get_pool", AsyncMock(return_value=pool)):
        result = await adapter.check_entitlement("NC-STUDIO-UNKNOWN")

    assert result.entitled is False
    assert "Unknown appliance" in (result.message or "")


@pytest.mark.asyncio
async def test_postgres_adapter_denied_when_trial_expired():
    adapter = PostgresBillingAdapter()
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    row = {"status": "trialing", "trial_ends_at": expired}

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(adapter, "_get_pool", AsyncMock(return_value=pool)):
        result = await adapter.check_entitlement("NC-STUDIO-TEST01")

    assert result.entitled is False
    assert "trial" in (result.message or "").lower()