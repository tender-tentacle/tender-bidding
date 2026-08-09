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
            "crawled_date": "2023-10-01T00:00:00Z",
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


@pytest.mark.asyncio
async def test_manual_scrape_kununu_skips_when_cache_under_30_days():
    company_id = "Flughafen Stuttgart GmbH"
    mock_kununu_data = {
        "metadata": {"overall_score": 4.1},
        "comments": [
            {
                "comment_hash": "stuttgart_hash_1",
                "title": "Guter Arbeitgeber am Flughafen",
                "content": "Solide Sozialleistungen",
                "rating": 4.0,
                "published_date": "2026-08-01",
            }
        ],
    }

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            pass

    post_call_count = 0

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        nonlocal post_call_count
        url_str = str(url)
        if "scrape/kununu" in url_str:
            post_call_count += 1
            return MockResponse(mock_kununu_data)
        if "taxonomy" in url_str:
            return MockResponse({})
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # First call: populates cache
            resp1 = await ac.post(
                f"/company/{company_id}/mood/scrape",
                json={"url": "https://www.kununu.com/de/flughafen-stuttgart"},
            )
            assert resp1.status_code == 200
            assert post_call_count == 1

            # Second call immediately after (data < 30 days old): should skip scraping to save resources
            resp2 = await ac.post(
                f"/company/{company_id}/mood/scrape",
                json={"url": "https://www.kununu.com/de/flughafen-stuttgart"},
            )
            assert resp2.status_code == 200
            assert post_call_count == 1  # post_call_count MUST REMAIN 1! No new scrape call made.


@pytest.mark.asyncio
async def test_manual_scrape_kununu_forces_rescrape_when_force_true():
    company_id = "Flughafen Stuttgart GmbH Force"
    mock_kununu_data = {
        "metadata": {"overall_score": 4.2},
        "comments": [
            {
                "comment_hash": "stuttgart_hash_force",
                "title": "Toller Betrieb",
                "content": "Sehr gut",
                "rating": 5.0,
                "published_date": "2026-08-05",
            }
        ],
    }

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            pass

    post_call_count = 0
    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        nonlocal post_call_count
        url_str = str(url)
        if "scrape/kununu" in url_str:
            post_call_count += 1
            return MockResponse(mock_kununu_data)
        if "taxonomy" in url_str:
            return MockResponse({})
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # First call: populates cache
            resp1 = await ac.post(
                f"/company/{company_id}/mood/scrape",
                json={"url": "https://www.kununu.com/de/flughafen-stuttgart"},
            )
            assert resp1.status_code == 200
            assert post_call_count == 1

            # Second call with force=True: should bypass 30-day cache check and call scraper again
            resp2 = await ac.post(
                f"/company/{company_id}/mood/scrape",
                json={"url": "https://www.kununu.com/de/flughafen-stuttgart", "force": True},
            )
            assert resp2.status_code == 200
            assert post_call_count == 2



