"""Integration test: Tagesschau news search for 'Porsche' → AI Connector sentiment evaluation → Bidding MS cleansing & display.

Validates the complete end-to-end integration flow:
1. Searching Tagesschau news for 'Porsche' (mocking raw search results).
2. AI Connector evaluation of news articles (mocking fast/small model tier sentiment scoring).
3. Bidding MS cleansing (filtering irrelevant articles, normalizing dates, formatting output).
4. Asserting cleaned, structured display output.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.v1.company_news import get_company_news
from api.v1.company_summary import run_stage2_market_and_news
from core.database import SessionLocal, init_db


@pytest.mark.asyncio
async def test_tagesschau_porsche_news_ai_cleansing_flow():
    """Verify that Tagesschau news for Porsche are fetched, evaluated by AI Connector, and cleansed by Bidding MS."""
    await init_db()
    company_name = "Porsche"

    # Step 1: Mock raw Tagesschau POST scraper results (Crawling MS fallback format)
    mock_tagesschau_post_results = [
        {
            "hash": "porsche-news-001",
            "title": "Porsche AG verzeichnet Rekordquartal bei Sportwagen-Auslieferungen",
            "content": "Der Stuttgarter Sportwagenhersteller Porsche meldet steigende Verkaufszahlen und hohe Nachfrage.",
            "link": "https://www.tagesschau.de/wirtschaft/unternehmen/porsche-quartal-100.html",
            "published_at": "2026-08-15",
            "category": "Tagesschau News",
        },
        {
            "hash": "porsche-news-002",
            "title": "Porsche und MHP erweitern Kooperation im Bereich Cloud Automation",
            "content": "Porsche vertieft die IT-Zusammenarbeit mit der Beratungstochter MHP für digitale Transformation.",
            "link": "https://www.tagesschau.de/wirtschaft/porsche-mhp-cloud-100.html",
            "published_at": "2026-08-14",
            "category": "Tagesschau News",
        },
        {
            "hash": "porsche-news-003",
            "title": "Historische Porsche Traktoren auf Oldtimer-Treffen in der Eifel",
            "content": "Private Sammler zeigten historische Landmaschinen und Traktoren der Marke Porsche.",
            "link": "https://www.tagesschau.de/regional/eifel-oldtimer-100.html",
            "published_at": "2026-08-10",
            "category": "Tagesschau News",
        },
    ]

    # Step 2: Mock raw Tagesschau GET API search results (Tagesschau direct API format)
    mock_tagesschau_get_results = {
        "searchResults": [
            {
                "title": "Porsche AG verzeichnet Rekordquartal bei Sportwagen-Auslieferungen",
                "firstSentence": "Der Stuttgarter Sportwagenhersteller Porsche meldet steigende Verkaufszahlen und hohe Nachfrage.",
                "detailsweb": "https://www.tagesschau.de/wirtschaft/unternehmen/porsche-quartal-100.html",
                "date": "2026-08-15",
            },
            {
                "title": "Porsche und MHP erweitern Kooperation im Bereich Cloud Automation",
                "firstSentence": "Porsche vertieft die IT-Zusammenarbeit mit der Beratungstochter MHP für digitale Transformation.",
                "detailsweb": "https://www.tagesschau.de/wirtschaft/porsche-mhp-cloud-100.html",
                "date": "2026-08-14",
            },
            {
                "title": "Historische Porsche Traktoren auf Oldtimer-Treffen in der Eifel",
                "firstSentence": "Private Sammler zeigten historische Landmaschinen und Traktoren der Marke Porsche.",
                "detailsweb": "https://www.tagesschau.de/regional/eifel-oldtimer-100.html",
                "date": "2026-08-10",
            },
        ]
    }

    # Step 3: Mock AI Connector batch sentiment scoring response
    mock_ai_connector_response = {
        "scored_articles": [
            {
                "id": "art-0",
                "sentiment_score": 92,
                "sentiment_label": "Positive",
                "rationale": "Starkes Auslieferungs- und Umsatzplus bei Porsche AG im aktuellen Quartal.",
                "is_relevant": True,
            },
            {
                "id": "art-1",
                "sentiment_score": 85,
                "sentiment_label": "Positive",
                "rationale": "Strategischer Ausbau von Cloud-Beratung und IT-Partnerschaft.",
                "is_relevant": True,
            },
            {
                "id": "art-2",
                "sentiment_score": 50,
                "sentiment_label": "Neutral",
                "rationale": "Privates Sammler-Treffen ohne Relevanz für Unternehmensanalyse.",
                "is_relevant": False,
            },
        ]
    }

    async def mock_http_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        url_str = str(url)
        if "tagesschau" in url_str:
            resp.json.return_value = mock_tagesschau_post_results
        elif "sentiment" in url_str or "inference" in url_str or "batch-score" in url_str:
            resp.json.return_value = mock_ai_connector_response
        else:
            resp.json.return_value = []
        return resp

    async def mock_http_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        url_str = str(url)
        if "tagesschau" in url_str:
            resp.json.return_value = mock_tagesschau_get_results
        else:
            resp.json.return_value = {"target_companies": []}
        return resp

    with (
        patch("httpx.AsyncClient.post", side_effect=mock_http_post),
        patch("httpx.AsyncClient.get", side_effect=mock_http_get),
    ):
        async with SessionLocal() as session:
            # 1. Execute Bidding MS company news scraping & persistence for Porsche
            news_entries = await get_company_news(company_id=company_name, db=session)
            assert isinstance(news_entries, list)
            assert len(news_entries) == 2

            # 2. Execute Bidding MS Stage 2 market scan & AI Connector cleansing pipeline
            summary_stage2 = await run_stage2_market_and_news(company_name, db=session)

            tagesschau_scan = summary_stage2.get("tagesschau_news_scan", {})
            articles = tagesschau_scan.get("articles", [])

            # Step 4: Verify Bidding MS cleansing & filtering
            # Irrelevant collector tractor article is cleansed out based on AI Connector is_relevant = False
            assert len(articles) == 2

            for art in articles:
                assert "Traktoren" not in art.get("title", "")
                assert "Oldtimer" not in art.get("title", "")

            # Verify cleaned structured data for display
            top_article = articles[0]
            assert top_article["title"] == "Porsche AG verzeichnet Rekordquartal bei Sportwagen-Auslieferungen"
            assert "tagesschau.de" in top_article["link"]
            assert top_article["published_at"] == "2026-08-15"
            assert top_article["sentiment_score"] == 92
            assert top_article["sentiment_label"] == "Positive"

            second_article = articles[1]
            assert "MHP" in second_article["title"]
            assert second_article["published_at"] == "2026-08-14"
            assert second_article["sentiment_score"] == 85
            assert second_article["sentiment_label"] == "Positive"
