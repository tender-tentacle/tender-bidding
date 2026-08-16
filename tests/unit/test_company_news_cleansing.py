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
