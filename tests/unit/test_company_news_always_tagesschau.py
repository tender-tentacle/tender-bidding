from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_news import scrape_company_news


@pytest.mark.asyncio
async def test_scrape_company_news_always_merges_tagesschau():
    """Verify scrape_company_news always fetches and merges Tagesschau news items alongside Deep Research."""
    company_id = "MHP Management- und IT-Beratung GmbH"

    fake_deep_res = {
        "press_news": [
            {
                "hash": "deep1",
                "title": "MHP Deep Research Headline",
                "link": "https://mhp.com/news/1",
                "summary": "Deep research summary",
                "content": "Deep research content",
                "published_date": "2026-08-01",
                "sentiment_score": 75,
                "sentiment_label": "Positive",
                "sentiment_rationale": "Growth",
                "key_topics": ["MHP"]
            }
        ],
        "company_blog": []
    }

    mock_tagesschau_resp = MagicMock()
    mock_tagesschau_resp.status_code = 200
    mock_tagesschau_resp.json.return_value = {
        "searchResults": [
            {
                "title": "Tagesschau MHP Presseecho",
                "detailsweb": "https://www.tagesschau.de/mhp-1",
                "teaserText": "Tagesschau teaser",
                "date": "2026-08-10T10:00:00Z"
            }
        ]
    }

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    mock_db.add = MagicMock()

    with patch("api.v1.company_news.run_deep_research_company_news", new_callable=AsyncMock) as mock_dr, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_dr.return_value = fake_deep_res
        mock_get.return_value = mock_tagesschau_resp

        res = await scrape_company_news(company_id, db=mock_db)
        
        # Verify both Deep Research AND Tagesschau articles were returned
        titles = [getattr(item, "title", None) or item.get("title") for item in res]
        assert "MHP Deep Research Headline" in titles
        assert "Tagesschau MHP Presseecho" in titles
