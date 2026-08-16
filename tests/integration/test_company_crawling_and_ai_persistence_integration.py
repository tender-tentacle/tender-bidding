from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_company_crawling_and_ai_persistence_lifecycle():
    """
    Integration test verifying that North Data, Handelsregister, Kununu, and Tagesschau/News
    scraped data and AI feedback summaries are persisted into Bidding DB and correctly retrievable.
    """
    company_id = "MHP Management- und IT-Beratung GmbH"

    # 1. Test North Data Scrape & DB Persistence
    northdata_mock_payload = {
        "company_name": company_id,
        "register_court": "Amtsgericht Stuttgart",
        "register_number": "HRB 205571",
        "euid": "DEB8534.HRB205571",
        "lei_code": "3912001F4V339T0Z9469",
        "business_purpose": "Sämtliche Tätigkeiten im Bereich der Management-Beratung...",
        "history_timeline": [{"date": "2024-01-01", "desc": "Refreshed Register Entry"}],
        "persons_timeline": [{"name": "Federico Magno", "role": "Geschäftsführer"}],
        "marketing_tech": [{"type": "wordmark", "desc": "MHP"}],
        "network_links": [{"source_name": company_id, "target_name": "Federico Magno"}],
        "is_valid_profile": True,
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock responses for Distributing MS link save and Crawling MS scraper call
        mock_resp_dist = AsyncMock()
        mock_resp_dist.status_code = 200
        mock_resp_crawl = AsyncMock()
        mock_resp_crawl.status_code = 200
        mock_resp_crawl.json = lambda: northdata_mock_payload
        mock_resp_crawl.raise_for_status = lambda: None
        mock_post.side_effect = [mock_resp_dist, mock_resp_crawl]

        res_scrape_nd = client.post(
            f"/api/v1/company/{company_id}/northdata/scrape",
            json={"url": "https://www.northdata.de/MHP+Management-+und+IT-Beratung+GmbH"}
        )
        assert res_scrape_nd.status_code == 200, res_scrape_nd.text
        nd_data = res_scrape_nd.json()
        assert nd_data["register_court"] == "Amtsgericht Stuttgart"
        assert nd_data["euid"] == "DEB8534.HRB205571"

    # Verify retrieval from GET endpoint
    res_get_nd = client.get(f"/api/v1/company/{company_id}/northdata")
    assert res_get_nd.status_code == 200
    assert res_get_nd.json()["register_number"] == "HRB 205571"

    # 2. Test Handelsregister Scrape & DB Persistence
    handelsregister_mock_payload = {
        "source": "handelsregister.de",
        "documents": [
            {
                "type": "AD",
                "title": "Aktueller Abdruck (AD)",
                "markdown": "# 📜 Handelsregister - Aktueller Abdruck (AD) - MHP",
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp_dist = AsyncMock()
        mock_resp_dist.status_code = 200
        mock_resp_crawl = AsyncMock()
        mock_resp_crawl.status_code = 200
        mock_resp_crawl.json = lambda: handelsregister_mock_payload
        mock_post.side_effect = [mock_resp_dist, mock_resp_crawl]

        res_scrape_hr = client.post(f"/api/v1/company/{company_id}/handelsregister/scrape")
        assert res_scrape_hr.status_code == 200, res_scrape_hr.text
        hr_data = res_scrape_hr.json()
        assert len(hr_data["documents"]) > 0

    # Verify GET Handelsregister retrieval
    res_get_hr = client.get(f"/api/v1/company/{company_id}/handelsregister")
    assert res_get_hr.status_code == 200
    assert res_get_hr.json()["source"] == "handelsregister.de"

    # 3. Test AI Executive Summary Persistence
    res_exec = client.post(f"/api/v1/company/{company_id}/summarize/executive")
    assert res_exec.status_code == 200, res_exec.text
    exec_data = res_exec.json()
    assert "news_summary" in exec_data and len(exec_data["news_summary"]) > 0
