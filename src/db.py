"""Support app Postgres pool (tickets + guide). Separate from nocloud commercial DB."""

from __future__ import annotations

import os
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

_pool: Any = None


def support_database_url() -> str:
    url = os.environ.get("SUPPORT_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "SUPPORT_DATABASE_URL is required (Postgres). "
            "Example: postgresql://support:support@localhost:5433/support"
        )
    return url


async def get_pool():
    global _pool
    if asyncpg is None:
        raise RuntimeError("asyncpg is required for the support database")
    if _pool is None:
        _pool = await asyncpg.create_pool(support_database_url(), min_size=1, max_size=8)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def execute(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)
