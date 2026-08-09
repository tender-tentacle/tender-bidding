"""Consumer contract: user-dashboard → bidding (Company Data Summary).

Validates API contracts for:
- GET /bids/{bid_id}/company-summary
- POST /bids/{bid_id}/company-summary/extract
- GET /config/prompts/company-summary
- PUT /config/prompts/company-summary
"""

import pytest
from tests.helpers import api_client

COMPANY_SUMMARY_FIELDS = {
    "bid_id",
    "short_summary",
    "long_summary",
    "bid_manager_summary",
    "financial_solvency_badges",
    "kununu_sentiment",
    "active_hiring_radar",
    "historic_tender_footprint",
    "bidding_company_potential",
    "red_flag_banners",
    "extracted_at"
}


@pytest.mark.asyncio
async def test_company_summary_contract(mocker):
    async with api_client() as client:
        # 1. Test fetch prompt config
        r = await client.get("/config/prompts/company-summary")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "system_prompt" in body
        assert "user_prompt_template" in body

        # 2. Test update prompt config
        new_prompt = {"system_prompt": "Custom system prompt for testing", "user_prompt_template": "Custom user prompt"}
        r_put = await client.put("/config/prompts/company-summary", json=new_prompt)
        assert r_put.status_code == 200

        # 3. Create a bid and test GET/POST company-summary
        bid_id = "test-bid-summary-123"
        r_get = await client.get(f"/bids/{bid_id}/company-summary")
        # Initially empty or default structure
        assert r_get.status_code in (200, 404)

        # Trigger extraction
        r_extract = await client.post(f"/bids/{bid_id}/company-summary/extract", json={"company_name": "BVL"})
        assert r_extract.status_code == 200
        data = r_extract.json()
        assert set(data.keys()) >= COMPANY_SUMMARY_FIELDS
