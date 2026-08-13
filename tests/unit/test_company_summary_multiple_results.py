"""Reproduction test for multiple results in company summary lookup."""

import pytest
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.helpers import api_client
from core.database import SessionLocal
from models.bid import Bid


@pytest.mark.asyncio
async def test_company_summary_handles_multiple_bid_results():
    """Verify GET and POST /bids/{bid_id}/company-summary do not crash with 500 when multiple rows match bid_id."""
    target_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())

    async with SessionLocal() as db:
        # Row 1: id == target_id
        b1 = Bid(id=target_id, source_ref=f"ref-1-{uuid.uuid4()}", enriching_id="enrich-1", title="Duplicate Bid 1", status="draft")
        # Row 2: source_ref == target_id
        b2 = Bid(id=other_id, source_ref=target_id, enriching_id="enrich-2", title="Duplicate Bid 2", status="draft")
        db.add_all([b1, b2])
        await db.commit()

    async with api_client() as client:
        # GET company-summary with target_id (which matches 2 rows via or_(Bid.id == target_id, Bid.source_ref == target_id))
        res_get = await client.get(f"/bids/{target_id}/company-summary")
        assert res_get.status_code == 200, f"Expected 200 OK, got {res_get.status_code}: {res_get.text}"

        # POST company-summary/extract with target_id
        res_extract = await client.post(
            f"/bids/{target_id}/company-summary/extract",
            json={"company_name": "Test Duplicates GmbH"}
        )
        assert res_extract.status_code == 200, f"Expected 200 OK, got {res_extract.status_code}: {res_extract.text}"
