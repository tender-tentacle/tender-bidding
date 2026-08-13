"""Reproduction test for multiple results in GET /bids/by-source/{source_ref}."""

import pytest
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.helpers import api_client
from core.database import SessionLocal
from models.bid import Bid


@pytest.mark.asyncio
async def test_get_bid_by_source_handles_multiple_results():
    """Verify GET /bids/by-source/{source_ref} does not crash with 500 when multiple rows match."""
    target_id = str(uuid.uuid4())

    async with SessionLocal() as db:
        # Row 1: source_ref == target_id
        b1 = Bid(id=str(uuid.uuid4()), source_ref=target_id, enriching_id="enrich-1", title="Duplicate Bid 1", status="draft")
        # Row 2: enriching_id == target_id
        b2 = Bid(id=str(uuid.uuid4()), source_ref=f"ref-2-{uuid.uuid4()}", enriching_id=target_id, title="Duplicate Bid 2", status="draft")
        db.add_all([b1, b2])
        await db.commit()

    async with api_client() as client:
        res = await client.get(f"/bids/by-source/{target_id}")
        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
