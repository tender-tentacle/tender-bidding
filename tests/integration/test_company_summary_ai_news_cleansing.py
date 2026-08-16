"""Integration test verifying that bidding MS queries AI Connector to cleanse non-company news articles."""

from unittest.mock import MagicMock, patch

import pytest
from api.v1.company_summary import run_stage2_market_and_news


@pytest.mark.asyncio
async def test_bidding_summary_uses_ai_connector_news_cleansing():
    """Verify that bidding MS uses AI connector to filter out political party false positive articles for MHP."""
    company_name = "MHP"

    mock_tagesschau_raw = {
        "searchResults": [
            {
                "title": "Ein historischer Schritt - und offene Fragen",
                "firstSentence": "Der türkische Staat verhandelt mit der PKK. Die rechtsextreme MHP unterstützt den Kurs.",
                "detailsweb": "https://www.tagesschau.de/ausland/asien/pkk-gesetz-tuerkei-100.html",
                "date": "2026-08-01"
            },
            {
                "title": "Sindelfinger 'Sahel-Verein': Ankaras Lobby-Netzwerk?",
                "firstSentence": "Die Verbindungen der rechtsextremen MHP in der Türkei...",
                "detailsweb": "https://www.swr.de/swraktuell/sindelfingen-100.html",
                "date": "2026-07-20"
            },
            {
                "title": "MHP erzielt Rekordumsatz als Porsche-Tochter im IT-Sektor",
                "firstSentence": "Die IT- und Managementberatung MHP mit Sitz in Ludwigsburg verzeichnet Plus.",
                "detailsweb": "https://www.tagesschau.de/wirtschaft/mhp-porsche-100.html",
                "date": "2026-07-15"
            }
        ]
    }

    mock_ai_resp = {
        "scored_articles": [
            {
                "id": "art-0",
                "sentiment_score": 50,
                "sentiment_label": "Neutral",
                "rationale": "Politische Partei MHP in der Türkei",
                "is_relevant": False
            },
            {
                "id": "art-1",
                "sentiment_score": 50,
                "sentiment_label": "Neutral",
                "rationale": "Politische Partei MHP in der Türkei",
                "is_relevant": False
            },
            {
                "id": "art-2",
                "sentiment_score": 88,
                "sentiment_label": "Positive",
                "rationale": "Unternehmensmeldung über MHP Porsche-Tochter",
                "is_relevant": True
            }
        ]
    }

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "tagesschau" in str(url):
            resp.json.return_value = mock_tagesschau_raw
        else:
            resp.json.return_value = {}
        return resp

    async def mock_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_ai_resp
        return resp

    with (
        patch("httpx.AsyncClient.get", side_effect=mock_get),
        patch("httpx.AsyncClient.post", side_effect=mock_post),
    ):
        data = await run_stage2_market_and_news(company_name)

        ts_scan = data.get("tagesschau_news_scan", {})
        articles = ts_scan.get("articles", [])

        # Assert that political party articles were filtered out by AI connector cleansing
        for art in articles:
            title = art.get("title", "")
            assert "PKK" not in title and "Sahel-Verein" not in title
        
        assert len(articles) == 1
        assert articles[0]["title"] == "MHP erzielt Rekordumsatz als Porsche-Tochter im IT-Sektor"
