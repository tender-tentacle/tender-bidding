"""Unit test for Tagesschau news scan & company name resolution for Umweltbundesamt."""

import pytest
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_tagesschau_news_umweltbundesamt_extraction():
    """Verify that company summary extraction for Umweltbundesamt populates Tagesschau news scan with real articles."""
    async with api_client() as client:
        bid_id = "bid-umweltbundesamt-001"
        company_name = "Umweltbundesamt"

        res = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": company_name}
        )
        assert res.status_code == 200
        data = res.json()

        assert data["company_name"] == company_name
        news_scan = data.get("tagesschau_news_scan", {})
        assert news_scan.get("articles_found", 0) > 0
        headlines = news_scan.get("recent_headlines", [])
        assert len(headlines) > 0
        assert not any("Ziel-Auftraggeber" in h for h in headlines)

        # Verify articles array is populated with links
        articles = news_scan.get("articles", [])
        assert len(articles) > 0
        assert "title" in articles[0]
        assert "link" in articles[0]

        # GET request must return cached summary with valid company_name and news scan
        res_get = await client.get(f"/bids/{bid_id}/company-summary")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["company_name"] == company_name
        assert data_get["tagesschau_news_scan"]["articles_found"] > 0
        assert len(data_get["tagesschau_news_scan"].get("articles", [])) > 0


@pytest.mark.asyncio
async def test_company_summary_updates_customer_if_target_passed():
    """Verify that passing an explicit company_name updates a bid previously cached with 'Ziel-Auftraggeber'."""
    async with api_client() as client:
        bid_id = "bid-reextract-002"

        # Initial extraction with default/empty body
        res1 = await client.post(f"/bids/{bid_id}/company-summary/extract")
        assert res1.status_code == 200

        # Re-extraction with explicit company name 'Umweltbundesamt'
        res2 = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": "Umweltbundesamt"}
        )
        assert res2.status_code == 200
        data2 = res2.json()

        assert data2["company_name"] == "Umweltbundesamt"
        assert data2["tagesschau_news_scan"]["articles_found"] > 0
        assert not any("Ziel-Auftraggeber" in h for h in data2["tagesschau_news_scan"].get("recent_headlines", []))
