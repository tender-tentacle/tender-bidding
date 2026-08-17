import pytest
from api.v1.company_summary import score_articles_with_ai


@pytest.mark.asyncio
async def test_mhp_political_news_cleansing():
    """Verify that Turkish political party MHP news are filtered out of company news scan for MHP."""
    raw_articles = [
        {
            "title": "Ein historischer Schritt - und offene Fragen",
            "content": "Der türkische Staat verhandelt mit der PKK. Die rechtsextreme MHP unterstützt den Kurs.",
            "link": "https://www.tagesschau.de/ausland/asien/pkk-gesetz-tuerkei-100.html",
            "published_at": "2026-08-01"
        },
        {
            "title": "Sindelfinger 'Sahel-Verein': Ankaras Lobby-Netzwerk?",
            "content": "Verbindungen zur MHP in der Türkei.",
            "link": "https://www.swr.de/swraktuell/sindelfingen-100.html",
            "published_at": "2026-07-20"
        },
        {
            "title": "MHP erzielt Rekordumsatz als Porsche-Tochter im IT-Sektor",
            "content": "Die IT-Beratung MHP verzeichnet starkes Wachstum im Automobilbereich.",
            "link": "https://www.tagesschau.de/wirtschaft/mhp-porsche-100.html",
            "published_at": "2026-07-15"
        }
    ]

    scored = await score_articles_with_ai(raw_articles, company_name="MHP")
    
    # Filter out non-company news items
    cleansed = [a for a in scored if a.get("is_relevant", True) is not False]
    
    assert len(cleansed) == 1
    assert cleansed[0]["title"] == "MHP erzielt Rekordumsatz als Porsche-Tochter im IT-Sektor"


@pytest.mark.asyncio
async def test_get_company_news_cleanses_political_db_entries():
    """Verify get_company_news filters out political false positive entries when returning from DB cache."""
    from unittest.mock import AsyncMock, MagicMock
    from api.v1.company_news import get_company_news
    from models.bid import CompanyNewsEntry

    company_id = "MHP Management- und IT-Beratung GmbH"

    pol_entry1 = CompanyNewsEntry(
        company_id=company_id,
        hash="pol1",
        title="Ein historischer Schritt - und offene Fragen",
        link="https://www.tagesschau.de/ausland/asien/pkk-gesetz-tuerkei-100.html",
        content="Recherchen zu MHP in der Türkei.",
        summary="Recherchen zu MHP in der Türkei.",
        category="Tagesschau Presseecho",
        source_type="press",
        published_date="2026-08-11",
        crawled_date=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").UTC).replace(tzinfo=None),
        sentiment_score=50,
        sentiment_label="Neutral",
    )

    pol_entry2 = CompanyNewsEntry(
        company_id=company_id,
        hash="pol2",
        title="Sindelfinger \"Sahel-Verein\": Ankaras Lobby-Netzwerk?",
        link="https://www.swr.de/swraktuell/sindelfingen-100.html",
        content="Verbindungen zur MHP in der Türkei.",
        summary="Verbindungen zur MHP in der Türkei.",
        category="Tagesschau Presseecho",
        source_type="press",
        published_date="2026-07-29",
        crawled_date=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").UTC).replace(tzinfo=None),
        sentiment_score=50,
        sentiment_label="Neutral",
    )

    good_entry = CompanyNewsEntry(
        company_id=company_id,
        hash="good1",
        title="MHP und Porsche vertiefen IT-Kooperation",
        link="https://www.tagesschau.de/wirtschaft/mhp-porsche-100.html",
        content="MHP erweitert IT-Beratungsgeschäft.",
        summary="MHP erweitert IT-Beratungsgeschäft.",
        category="Tagesschau Presseecho",
        source_type="press",
        published_date="2026-08-12",
        crawled_date=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").UTC).replace(tzinfo=None),
        sentiment_score=85,
        sentiment_label="Positive",
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [pol_entry1, pol_entry2, good_entry]

    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_db_result

    res = await get_company_news(company_id, db=mock_db)

    titles = [getattr(e, "title", None) or e.get("title") for e in res]
    assert "Ein historischer Schritt - und offene Fragen" not in titles
    assert "Sindelfinger \"Sahel-Verein\": Ankaras Lobby-Netzwerk?" not in titles
    assert "MHP und Porsche vertiefen IT-Kooperation" in titles
    assert len(res) == 1
