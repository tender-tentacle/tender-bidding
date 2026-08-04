from unittest.mock import AsyncMock, patch

import httpx
import pytest
from tests.helpers import api_client


# Basic dummy test to simulate cross ms interaction
@pytest.mark.asyncio
async def test_get_company_mood_calls_crawling_ms_and_caches():
    # Setup test data
    company_id = "test-company"
    mock_kununu_data = [
        {
            "comment_hash": "hash123",
            "title": "Great place",
            "content": "I love working here",
            "rating": 5.0,
            "published_date": "2023-01-01",
            "crawled_date": "2023-10-01T00:00:00Z"
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("Error", request=None, response=self)

    async def mock_post(*args, **kwargs):
        return MockResponse(mock_kununu_data)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
        async with api_client() as ac:
            response = await ac.get(f"/company/{company_id}/mood")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["title"] == "Great place"

@pytest.mark.asyncio
async def test_get_company_mood_handles_crawling_ms_failure():
    company_id = "blocked-company"
    
    async def mock_post_fail(*args, **kwargs):
        class FailedResp:
            status_code = 403
            def raise_for_status(self):
                raise httpx.HTTPStatusError("Blocked by WAF", request=AsyncMock(), response=self)
        return FailedResp()

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post_fail)):
        async with api_client() as ac:
            response = await ac.get(f"/company/{company_id}/mood")
            
            # Should not crash, should return 200 with empty list (or cached data if any)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

