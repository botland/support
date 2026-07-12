from __future__ import annotations

import os
import subprocess
import time
import uuid

import pytest

# Default test DB (compose maps host 5433 → container 5432)
os.environ.setdefault(
    "SUPPORT_DATABASE_URL",
    "postgresql://support:support@127.0.0.1:5433/support",
)
os.environ.setdefault("SUPPORT_FREE_FOR_ALL", "true")


def _ping_postgres(url: str) -> bool:
    import asyncio
    import asyncpg

    async def ping():
        conn = await asyncpg.connect(url, timeout=2)
        await conn.close()

    try:
        asyncio.run(ping())
        return True
    except Exception:
        return False


def _ensure_test_postgres() -> None:
    """Start compose db if nothing answers on SUPPORT_DATABASE_URL host."""
    url = os.environ["SUPPORT_DATABASE_URL"]
    if _ping_postgres(url):
        return

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    subprocess.run(
        ["docker", "compose", "up", "-d", "db"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    deadline = time.time() + 60
    last_err = "timeout"
    while time.time() < deadline:
        if _ping_postgres(url):
            return
        time.sleep(1)
    raise RuntimeError(f"Test Postgres not reachable at {url}: {last_err}")


_ensure_test_postgres()


@pytest.fixture(autouse=True)
async def _init_db():
    from src import db
    from src import tickets
    from src.guide import sessions

    await db.close_pool()
    await tickets.init_db()
    await sessions.init_guide_db()
    # Isolate tests with truncate
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE guide_messages, guide_sessions, tickets CASCADE")
    yield
    await db.close_pool()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    import src.main as main_module

    main_module._ticket_counts.clear()
    yield
    main_module._ticket_counts.clear()
