"""
E2E & Smoke Test for Bidding MS <-> AI Service Company Data Summary Pipeline.

Tests the full end-to-end extraction workflow using target tender data:
Tender ID: ed875469-2973-4029-ad66-46cb1776f58c
Company: Flughafen Stuttgart GmbH
Ref: 10005247 - Green Hydrogen Investments in India
"""

import pytest
from unittest.mock import AsyncMock, patch
from tests.helpers import api_client
from core.ai_client import RealAIClient


@pytest.mark.asyncio
async def test_e2e_bidding_to_ai_service_company_summary_flow():
    """
    E2E / Smoke test:
    1. Sends extraction request for Tender ID ed875469-2973-4029-ad66-46cb1776f58c to Bidding MS.
    2. Bidding MS relays prompt request to AI Service connector.
    3. AI Service returns structured executive intelligence payload.
    4. Bidding MS persists the summary to Bid.company_summary and returns HTTP 200.
    5. GET /bids/{bid_id}/company-summary retrieves the cached executive intelligence.
    """
    bid_id = "ed875469-2973-4029-ad66-46cb1776f58c"
    company_name = "Flughafen Stuttgart GmbH"

    async with api_client() as client:
        # Step 1: Trigger extraction via Bidding MS API
        extract_resp = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={
                "company_name": company_name,
                "is_aor": True
            }
        )
        assert extract_resp.status_code == 200, f"Extraction failed with status {extract_resp.status_code}"
        
        summary = extract_resp.json()

        # Step 2: Validate 6-part executive intelligence structure
        assert summary["bid_id"] == bid_id
        assert summary["company_name"] == company_name
        assert "short_summary" in summary and len(summary["short_summary"]) > 0
        assert "long_summary" in summary and len(summary["long_summary"]) > 0
        assert "bid_manager_summary" in summary and len(summary["bid_manager_summary"]) > 0

        # Step 3: Validate Solvency & Financial Badges
        financial = summary.get("financial_solvency_badges", {})
        assert "solvency_status" in financial
        assert "credit_score" in financial
        assert "financial_trend" in financial
        assert "AÖR" in financial["solvency_status"] or "Solid" in financial["solvency_status"]

        # Step 4: Validate Kununu Sentiment Indicators
        kununu = summary.get("kununu_sentiment", {})
        assert "work_life_balance" in kununu
        assert "management_rating" in kununu
        assert "retention_score" in kununu

        # Step 5: Validate Active Hiring Radar & Red Flags
        assert isinstance(summary.get("active_hiring_radar"), list)
        assert isinstance(summary.get("red_flag_banners"), list)
        assert len(summary["red_flag_banners"]) > 0

        # Step 6: Verify Database Retrieval Endpoint
        get_resp = await client.get(f"/bids/{bid_id}/company-summary")
        assert get_resp.status_code == 200, f"GET /company-summary failed with status {get_resp.status_code}"
        
        cached_summary = get_resp.json()
        assert cached_summary["bid_id"] == bid_id
        assert cached_summary["short_summary"] == summary["short_summary"]


@pytest.mark.asyncio
async def test_ai_service_connector_relay_contract():
    """
    Verifies that RealAIClient correctly packages and relays prompt requests to AI_URL/api/inference.
    """
    real_ai = RealAIClient()

    class MockAIResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
            self.text = "OK"

        def json(self):
            return self.json_data

    async def mock_post(url, json=None, **kwargs):
        assert "/api/inference" in url
        assert json["prompt_id"] in ["bidding_company_summary", "bidding_tender_metadata", "bidding_strategy"]
        return MockAIResponse({
            "status": "success",
            "data": {
                "short_summary": "Flughafen Stuttgart GmbH is a key public infrastructure buyer.",
                "long_summary": "Comprehensive public procurement profile for Stuttgart Airport.",
                "bid_manager_summary": "High EVB-IT compliance strictness."
            }
        })

    with patch("core.ai_client._sync_prompt", new=AsyncMock()):
        with patch("core.ai_client._configured_prompt", new=AsyncMock(return_value="Prompt template")):
            with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
                res = await real_ai.extract_tender_metadata({
                    "title": "Green Hydrogen Investments",
                    "company_name": "Flughafen Stuttgart GmbH"
                })
                assert res is not None
