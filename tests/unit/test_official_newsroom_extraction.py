"""Unit test: Verify official corporate newsroom extraction fallback for MHP Management- und IT-Beratung GmbH."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_news import fetch_official_newsroom_articles, scrape_company_news


@pytest.mark.asyncio
async def test_fetch_official_newsroom_articles_mhp():
    """Verify that official MHP newsroom articles are extracted from mhp.com newsroom URLs."""
    articles = await fetch_official_newsroom_articles("MHP Management- und IT-Beratung GmbH")
    assert isinstance(articles, list)
    assert len(articles) > 0, "Expected official newsroom articles for MHP"

    titles = [a["title"] for a in articles]
    assert any("MHP" in t or "Top 10" in t or "AI" in t or "Transformation" in t for t in titles)
    for art in articles:
        assert art["source_type"] == "company_blog"
        assert "mhp.com" in art["link"]


@pytest.mark.asyncio
async def test_scrape_company_news_uses_official_newsroom_fallback_when_ai_offline():
    """Verify that scrape_company_news falls back to official newsroom extraction when AI Connector & Tagesschau return empty."""
    company_id = "MHP Management- und IT-Beratung GmbH"

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []

    mock_db_res = MagicMock()
    mock_db_res.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_db_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def mock_get(url, *args, **kwargs):
        url_str = str(url)
        resp = MagicMock()
        resp.status_code = 200
        if "tagesschau" in url_str:
            resp.json.return_value = {"searchResults": []}
            resp.text = ""
        elif "mhp.com" in url_str:
            resp.json.return_value = {}
            resp.text = """
            <html>
                <body>
                    <a href="/en/insights/newsroom/news-detail/view/mhp-once-again-among-top-10">MHP once again among the Top 10 Leading IT Service Providers in Germany</a>
                    <a href="/en/insights/blog/post/finops-for-administration">FinOps for Administration</a>
                </body>
            </html>
            """
        else:
            resp.json.return_value = {}
            resp.text = ""
        return resp

    with patch("api.v1.company_news.run_deep_research_company_news", new_callable=AsyncMock) as mock_dr, \
         patch("httpx.AsyncClient.get", side_effect=mock_get):
        mock_dr.return_value = {}

        res = await scrape_company_news(company_id, db=mock_db)
        assert len(res) > 0, "Expected official newsroom fallback to populate company news"
        titles = [getattr(e, "title", None) or e.get("title") for e in res]
        assert any("MHP" in t or "FinOps" in t for t in titles)
