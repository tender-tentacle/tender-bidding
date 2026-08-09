"""Unit test for Company Data Summary backend logic & fallback handling in tender-bidding."""

import pytest
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_company_summary_aor_fallback():
    """Verify that when North Data is absent (e.g. AÖR entity), red flags and solvency fallback are generated."""
    async with api_client() as client:
        # Request extraction for an AÖR institution with no North Data
        res = await client.post(
            "/bids/test-aor-bid/company-summary/extract",
            json={"company_name": "Landesbetrieb Liegenschafts- und Baubetreuung", "is_aor": True}
        )
        assert res.status_code == 200
        data = res.json()
        assert any("AÖR" in flag or "Anstalt des öffentlichen Rechts" in flag for flag in data["red_flag_banners"])
        assert "AÖR" in data["financial_solvency_badges"]["solvency_status"]


@pytest.mark.asyncio
async def test_company_summary_persistence():
    """Verify saving and loading company summary to DB."""
    async with api_client() as client:
        bid_id = "bid-persistence-001"
        res_extract = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": "Flughafen Stuttgart GmbH"}
        )
        assert res_extract.status_code == 200
        summary_extracted = res_extract.json()

        res_get = await client.get(f"/bids/{bid_id}/company-summary")
        assert res_get.status_code == 200
        assert res_get.json()["short_summary"] == summary_extracted["short_summary"]


@pytest.mark.asyncio
async def test_company_summary_formatted_uuid_36_chars():
    """Verify that a 36-character UUID string (e.g. ed875469-2973-4029-ad66-46cb1776f58c) creates a Bid and extracts summary without 500 error."""
    async with api_client() as client:
        uuid_36 = "ed875469-2973-4029-ad66-46cb1776f58c"
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

