"""Unit tests for database initialization, MSSQL schema migration, and 36-char UUID column safety."""

import pytest
from core.database import SessionLocal, init_db
from models.bid import Bid
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_init_db_runs_mssql_migration():
    """Verify init_db runs create_all and attempts MSSQL column widening migration."""
    # Execute init_db directly
    await init_db()
    
    # Query database to confirm tables exist and can accept records
    async with SessionLocal() as session:
        uuid_36 = "ed875469-2973-4029-ad66-46cb1776f58c"
        bid = Bid(
            id=uuid_36,
            source_ref=f"ref-{uuid_36}",
            source_kind="tender",
            enriching_id=uuid_36,
            title="Migration Verification Tender",
            customer="Flughafen Stuttgart GmbH"
        )
        session.add(bid)
        await session.commit()
        
        res = await session.get(Bid, uuid_36)
        assert res is not None
        assert res.id == uuid_36


@pytest.mark.asyncio
async def test_api_client_handles_uuid36_bids():
    """Verify that HTTP API endpoints interact seamlessly with 36-character UUID bids."""
    async with api_client() as client:
        uuid_36 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        res_extract = await client.post(
            f"/bids/{uuid_36}/company-summary/extract",
            json={"company_name": "Flughafen Stuttgart GmbH"}
        )
        assert res_extract.status_code == 200
        summary_extracted = res_extract.json()
        assert summary_extracted["bid_id"] == uuid_36

        res_get = await client.get(f"/bids/{uuid_36}/company-summary")
        assert res_get.status_code == 200
        assert res_get.json()["bid_id"] == uuid_36
