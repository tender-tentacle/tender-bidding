"""Integration test for AI Connector Deep Research (model_tier='deep-research') and news synthesis for 'MHP Management- und IT-Beratung GmbH'.

Validates:
1. Deep Research execution for 'MHP Management- und IT-Beratung GmbH'.
2. Parsing dual-section output structure (press_news and company_blog).
3. Bidding MS news scraping endpoint persistence in DB as CompanyNewsEntry models.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.v1.company_news import run_deep_research_company_news, scrape_company_news
from core.database import SessionLocal, init_db
from models.bid import CompanyNewsEntry
from sqlalchemy import select


@pytest.mark.asyncio
async def test_mhp_deep_research_news_integration():
    """Verify Deep Research and news persistence lifecycle for MHP Management- und IT-Beratung GmbH."""
    await init_db()
    company_id = "MHP Management- und IT-Beratung GmbH"

    # Mock response from AI Connector deep-research prompt
    mock_ai_response = {
        "status": "success",
        "data": {
            "press_news": [
                {
                    "title": "MHP erzielt Rekordumsatz im Automotive-IT Sektor",
                    "link": "https://www.tagesschau.de/wirtschaft/mhp-porsche-100.html",
                    "summary": "MHP Management- und IT-Beratung GmbH berichtet über starkes zweistelliges Wachstum im ersten Halbjahr.",
                    "published_date": "2026-08-10",
                    "sentiment_score": 88,
                    "sentiment_label": "Positive",
                    "sentiment_rationale": "Starke Umsatzzahlen und hohes Kundenwachstum.",
                    "key_topics": ["Automotive", "IT Consulting", "Wachstum"]
                }
            ],
            "company_blog": [
                {
                    "title": "KI-Strategie 2026 & Digitalisierung bei MHP",
                    "link": "https://www.mhp.com/de/newsroom/artikel/ki-strategie-2026",
                    "summary": "Offizieller Blogbeitrag von MHP zur KI-gestützten Transformationsberatung.",
                    "published_date": "2026-08-14",
                    "sentiment_score": 92,
                    "sentiment_label": "Positive",
                    "sentiment_rationale": "Innovation und Technologieführerschaft.",
                    "key_topics": ["Künstliche Intelligenz", "Transformationsberatung"]
                }
            ]
        }
    }

    async def mock_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        url_str = str(url)
        if "inference" in url_str or "ai" in url_str:
            resp.json.return_value = mock_ai_response
        elif "tagesschau" in url_str:
            resp.json.return_value = []
        else:
            resp.json.return_value = []
        return resp

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"target_companies": []}
        return resp

    with (
        patch("httpx.AsyncClient.post", side_effect=mock_post),
        patch("httpx.AsyncClient.get", side_effect=mock_get),
    ):
        # 1. Test Deep Research synthesis helper
        deep_res = await run_deep_research_company_news(company_id)
        assert isinstance(deep_res, dict)
        assert "press_news" in deep_res
        assert "company_blog" in deep_res
        assert len(deep_res["press_news"]) == 1
        assert len(deep_res["company_blog"]) == 1

        # 2. Test Bidding MS news scrape & DB persistence
        async with SessionLocal() as session:
            saved_entries = await scrape_company_news(company_id=company_id, db=session)
            assert isinstance(saved_entries, list)
            assert len(saved_entries) == 2

            # Verify persisted DB records
            result = await session.execute(
                select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id)
            )
            entries_in_db = result.scalars().all()
            assert len(entries_in_db) == 2

            titles = [e.title for e in entries_in_db]
            assert "MHP erzielt Rekordumsatz im Automotive-IT Sektor" in titles
            assert "KI-Strategie 2026 & Digitalisierung bei MHP" in titles

            press_entry = next(e for e in entries_in_db if "Rekordumsatz" in e.title)
            assert press_entry.source_type == "press"
            assert press_entry.sentiment_score == 88
            assert press_entry.published_date == "2026-08-10"

            blog_entry = next(e for e in entries_in_db if "KI-Strategie" in e.title)
            assert blog_entry.source_type == "company_blog"
            assert blog_entry.sentiment_score == 92
            assert blog_entry.published_date == "2026-08-14"
