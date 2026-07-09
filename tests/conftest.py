from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPPORT_DB_PATH", str(Path("/tmp/appliance-support-test.db")))
os.environ.setdefault("SUPPORT_FREE_FOR_ALL", "true")


@pytest.fixture(autouse=True)
async def _init_db():
    from src import tickets

    if Path(os.environ["SUPPORT_DB_PATH"]).exists():
        Path(os.environ["SUPPORT_DB_PATH"]).unlink()
    await tickets.init_db()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    import src.main as main_module

    main_module._ticket_counts.clear()
    yield
    main_module._ticket_counts.clear()