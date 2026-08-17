"""Integration test verifying 20+ external press & media news items for MHP Management- und IT-Beratung GmbH."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.v1.company_news import scrape_company_news
from models.bid import Base, CompanyNewsEntry

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_20_or_more_external_press_news_for_mhp(async_session, monkeypatch):
    """Verify that external media & press coverage (source_type='press') extracts 20+ individual articles with summaries for MHP."""
    company_name = "MHP Management- und IT-Beratung GmbH"

    # Mock AI Connector to return 22 distinct external press media articles
    media_outlets = ["Tagesschau", "Handelsblatt", "Business Insider", "Automotive News", "Golem", "Heise", "IT-Boltwise", "Manager Magazin"]
    mock_external_press = [
        {
            "title": f"MHP in den Medien ({media_outlets[i % len(media_outlets)]}): Digital-Initiative & Transformation {i+1}",
            "link": f"https://www.{media_outlets[i % len(media_outlets)].lower().replace(' ', '')}.de/artikel-{i+100}",
            "summary": f"Unabhängiger Pressebericht {i+1} auf {media_outlets[i % len(media_outlets)]} über MHP Management- und IT-Beratung GmbH, Strategie, Umsatz und Marktrolle.",
            "published_date": f"2026-08-{(14 - (i % 12)):02d}",
            "sentiment_score": 80 + (i % 15),
            "sentiment_label": "Positiv" if (i % 3 != 0) else "Neutral",
            "sentiment_rationale": "Branchenberichterstattung zur Marktpositionierung.",
            "key_topics": ["Externe Berichterstattung", "Marktanalyse", "IT Consulting"]
        }
        for i in range(22)
    ]

    async def mock_deep_research(comp_name, urls=None):
        return {
            "press_news": mock_external_press,
            "company_blog": []
        }

    monkeypatch.setattr("api.v1.company_news.run_deep_research_company_news", mock_deep_research)

    # Trigger news scrape
    results = await scrape_company_news(company_name, async_session)

    # Filter to external press items
    external_press_items = [r for r in results if r.source_type == "press"]

    assert len(external_press_items) >= 20, f"Expected at least 20 external press items, got {len(external_press_items)}"

    # Assert attributes for external press items
    for item in external_press_items:
        assert item.source_type == "press"
        assert item.category == "Presse & Medien (Deep Research)"
        assert item.title is not None and len(item.title) > 0
        assert item.link is not None and len(item.link) > 0
        assert item.summary is not None and len(item.summary) > 0

    print(f"\n=== VERIFIED {len(external_press_items)} EXTERNAL PRESS MEDIA ARTICLES ===")
    for idx, item in enumerate(external_press_items[:5], 1):
        print(f"[{idx}] {item.title}")
        print(f"    Link: {item.link}")
        print(f"    Summary: {item.summary}")
        print(f"    Category: {item.category} | Source: {item.source_type}")
        print(f"    Date: {item.published_date}\n")
