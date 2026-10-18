from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.mark.asyncio
async def test_scrape_company_northdata_routes_to_market_research_service():
    """
    Test that scrape_company_northdata sends the POST request to
    tender-market-research microservice (MARKET_RESEARCH_URL/api/v1/scrape/northdata)
    rather than tender-crawling microservice.
    """
    client = TestClient(app)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "company_name": "MHP Management- und IT-Beratung GmbH",
        "address": "Königsallee 49, D-71638 Ludwigsburg",
        "is_valid_profile": True,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        response = client.post(
            "/api/v1/company/MHP/northdata/scrape",
            json={"url": "https://www.northdata.de/MHP"}
        )

        assert response.status_code == 200

        # Check the call arguments to httpx.AsyncClient.post
        # Find the call that targeted /api/v1/scrape/northdata
        northdata_calls = [
            call for call in mock_post.call_args_list 
            if "/api/v1/scrape/northdata" in str(call)
        ]
        assert len(northdata_calls) > 0, "No request made to /api/v1/scrape/northdata"
        
        called_url = northdata_calls[0][0][0]
        # Must target tender-market-research / port 8015 instead of tender-crawling / port 8001
        assert "tender-market-research" in called_url or "8015" in called_url, f"Expected market-research URL, got {called_url}"
