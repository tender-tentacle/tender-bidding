"""Test setup: mock mode + isolated temp SQLite, fresh schema per test.

SQLITE_DATA_DIR and BIDDING_MOCK must be set before core.database / core.config
import, because the engine URL and mock flag are resolved at import time.
"""

import os
import tempfile

os.environ.setdefault("SQLITE_DATA_DIR", tempfile.mkdtemp(prefix="bidding-test-"))
os.environ.setdefault("BIDDING_MOCK", "1")

import models.bid  # noqa: F401 — register mappers
import pytest_asyncio
from core.database import Base, engine
from services.portal_guide import seed_portal_guides


@pytest_asyncio.fixture(autouse=True)
async def _fresh_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_portal_guides()
    yield
