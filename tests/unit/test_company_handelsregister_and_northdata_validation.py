from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from core.database import get_db
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture(autouse=True)
def cleanup_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    # Mock scalars().first() for select queries
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    session.execute.return_value = mock_result

    async def mock_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = "mock-uuid-1234"

    session.refresh.side_effect = mock_refresh
    return session


@pytest.mark.asyncio
async def test_handelsregister_scrape_routes_to_market_research_and_has_no_mhp_leak(mock_db_session):
    """
    Asserts:
    1. Scraping Handelsregister queries MARKET_RESEARCH_MS_URL (port 8015).
    2. When falling back to generated AD document, non-MHP companies do NOT receive
       MHP's hardcoded directors ('Federico Magno') or seat ('Ludwigsburg').
    """
    try:
        app.dependency_overrides[get_db] = lambda: mock_db_session

        company_name = "Cancom SE"
        transport = ASGITransport(app=app)
        called_external_urls = []

        original_post = httpx.AsyncClient.post

        async def mock_post(self, url, *args, **kwargs):
            url_str = str(url)
            if "8015" in url_str or "market-research" in url_str:
                called_external_urls.append(url_str)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"company_name": company_name, "documents": []}
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            if "8005" in url_str or "taxonomy" in url_str or "distributing" in url_str:
                called_external_urls.append(url_str)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {}
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            return await original_post(self, url, *args, **kwargs)

        with patch.object(httpx.AsyncClient, "post", new=mock_post):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(f"/api/v1/company/{company_name}/handelsregister/scrape")
                assert resp.status_code == 200
                data = resp.json()
                assert data["company_id"] == company_name
                assert len(data["documents"]) > 0

                ad_doc = data["documents"][0]
                markdown = ad_doc["markdown"]

                # Must NOT contain hardcoded MHP executives
                assert "Federico Magno" not in markdown
                assert "Markus Wambach" not in markdown
                assert "Marc Oliver Zimmermann" not in markdown

                # Must NOT contain hardcoded MHP city Ludwigsburg
                assert "Ludwigsburg" not in markdown

                # Verified target URL was Market Research MS (port 8015)
                assert any("8015" in u or "market-research" in u for u in called_external_urls)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_northdata_scrape_preserves_invalid_profile_and_unescapes_name(mock_db_session):
    """
    Asserts:
    1. When Market Research returns no_profile_found=True / is_valid_profile=False,
       Bidding MS persists is_valid_profile=False and no_profile_found=True.
    2. HTML entities in company name (e.g. &amp;) are properly unescaped.
    """
    try:
        app.dependency_overrides[get_db] = lambda: mock_db_session

        company_id = "SNP Schneider-Neureither & Partner SE"
        transport = ASGITransport(app=app)
        called_external_urls = []

        original_post = httpx.AsyncClient.post

        async def mock_post(self, url, *args, **kwargs):
            url_str = str(url)
            if "8015" in url_str or "market-research" in url_str:
                called_external_urls.append(url_str)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "company_name": "SNP Schneider-Neureither &amp; Partner SE",
                    "source_url": "https://www.northdata.de/search?q=SNP",
                    "is_valid_profile": False,
                    "no_profile_found": True,
                    "no_profile_reason": "Entity mismatch or search page",
                    "register_court": "Amtsgericht Mannheim",
                    "register_number": "HRB 729172",
                    "officers": [],
                    "events": [],
                    "history_timeline": [],
                }
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            if "8005" in url_str or "taxonomy" in url_str or "distributing" in url_str:
                called_external_urls.append(url_str)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {}
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            return await original_post(self, url, *args, **kwargs)

        with patch.object(httpx.AsyncClient, "post", new=mock_post):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/company/{company_id}/northdata/scrape",
                    json={"url": "https://www.northdata.de/search?q=SNP"}
                )
                assert resp.status_code == 200
                data = resp.json()

                # Company name must be unescaped (&amp; -> &)
                assert data["company_name"] == "SNP Schneider-Neureither & Partner SE"
                assert "&amp;" not in data["company_name"]

                # Validation flags must strictly preserve invalid status
                assert data["is_valid_profile"] is False
                assert data["no_profile_found"] is True
    finally:
        app.dependency_overrides.clear()
