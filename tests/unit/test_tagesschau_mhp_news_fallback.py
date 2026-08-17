"""Unit test: Verify Tagesschau news scan fallback for MHP Management- und IT-Beratung GmbH when direct API returns 0 items or political false positives."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_summary import run_stage2_market_and_news
from models.bid import CompanyNewsEntry


@pytest.mark.asyncio
async def test_mhp_company_summary_tagesschau_news_fallback_to_db_or_news_scraper():
    """
    Verify that when direct Tagesschau search API returns 0 items or political false positives
    for 'MHP Management- und IT-Beratung GmbH', run_stage2_market_and_news falls back to
    persisted CompanyNewsEntry records in DB or calls scrape_company_news.
    """
    company_name = "MHP Management- und IT-Beratung GmbH"

    # Mock direct Tagesschau API response returning political false positives for "MHP"
    mock_tagesschau_resp = MagicMock()
    mock_tagesschau_resp.status_code = 200
    mock_tagesschau_resp.json.return_value = {
        "searchResults": [
            {
                "title": "Sindelfinger Sahel-Verein: Ankaras Lobby-Netzwerk?",
                "firstSentence": "Recherchen zu MHP in der Türkei.",
                "detailsweb": "https://www.tagesschau.de/pkk-100.html",
                "date": "2026-08-01",
            }
        ]
    }

    # Mock DB returning cached CompanyNewsEntry for MHP
    mock_entry = CompanyNewsEntry(
        company_id=company_name,
        hash="mhp-press-001",
        title="MHP und Porsche vertiefen IT-Kooperation",
        link="https://www.tagesschau.de/wirtschaft/mhp-porsche-100.html",
        content="MHP Management- und IT-Beratung baut Beratung im Bereich Cloud and AI aus.",
        summary="MHP erweitert IT-Beratungsgeschäft.",
        category="Tagesschau Presseecho",
        source_type="press",
        published_date="2026-08-12",
        sentiment_score=85,
        sentiment_label="Positive",
        sentiment_rationale="Wachstum im Beratungsumfeld",
        key_topics=["MHP", "Porsche"],
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_entry]

    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_db_result

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_tagesschau_resp

        res = await run_stage2_market_and_news(company_name, db=mock_db)

        news_scan = res.get("tagesschau_news_scan", {})
        assert news_scan.get("articles_found", 0) > 0, "Expected Tagesschau news scan to fallback to DB entries"
        articles = news_scan.get("articles", [])
        assert len(articles) == 1
        assert articles[0]["title"] == "MHP und Porsche vertiefen IT-Kooperation"
