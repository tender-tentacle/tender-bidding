"""Integration test verifying 20+ company news & blog items with summaries for MHP Management- und IT-Beratung GmbH."""

import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.v1.company_news import get_company_news, scrape_company_news, normalize_news_date
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
async def test_get_20_or_more_news_for_mhp_with_summary(async_session, monkeypatch):
    """Verify that company news scraping extracts 20+ individual press releases and blog posts with summaries for MHP."""
    company_name = "MHP Management- und IT-Beratung GmbH"

    # Mock AI Connector to return 25 distinct structured items with summaries
    mock_press = [
        {
            "title": f"MHP Pressemitteilung {i+1}: Innovation & Strategie 2026",
            "link": f"https://www.presseportal.de/pm/129860/{6329330 + i}",
            "summary": f"Offizielle Pressemitteilung {i+1} von MHP Management- und IT-Beratung GmbH über neueste IT-Lösungen und Cloud Transformation.",
            "published_date": f"2026-08-{(14 - (i % 10)):02d}",
            "sentiment_score": 85 + (i % 10),
            "sentiment_label": "Positiv",
            "sentiment_rationale": "Erfolgreiche Projektreferenz und Unternehmenswachstum.",
            "key_topics": ["IT Consulting", "Automotive", "Cloud"]
        }
        for i in range(15)
    ]
    mock_blog = [
        {
            "title": f"MHP Tech Blog {i+1}: KI & Digitalisierung im Automobilbau",
            "link": f"https://www.mhp.com/de/insights/blog/artikel-{i+1}",
            "summary": f"Technischer Fachbeitrag {i+1} der Porsche-Tochter MHP zu generativer KI, 3D-Simulation und Industrie 4.0.",
            "published_date": f"2026-08-{(12 - (i % 10)):02d}",
            "sentiment_score": 90 + (i % 5),
            "sentiment_label": "Positiv",
            "sentiment_rationale": "Innovationsführerschaft im Automotive IT Markt.",
            "key_topics": ["Künstliche Intelligenz", "Software Engineering"]
        }
        for i in range(10)
    ]

    async def mock_deep_research(comp_name, urls=None):
        return {
            "press_news": mock_press,
            "company_blog": mock_blog
        }

    monkeypatch.setattr("api.v1.company_news.run_deep_research_company_news", mock_deep_research)

    # Trigger news scrape
    results = await scrape_company_news(company_name, async_session)

    assert len(results) >= 25, f"Expected at least 20 news items, got {len(results)}"

    # Verify summary is populated for all items
    for item in results:
        assert item.title is not None and len(item.title) > 0
        assert item.link is not None and len(item.link) > 0
        assert item.summary is not None and len(item.summary) > 0, f"Summary missing for {item.title}"

    print(f"\n=== VERIFIED {len(results)} NEWS ITEMS WITH SUMMARIES ===")
    for idx, item in enumerate(results[:5], 1):
        print(f"[{idx}] {item.title}")
        print(f"    Link: {item.link}")
        print(f"    Summary: {item.summary}")
        print(f"    Category: {item.category} | Source: {item.source_type}")
        print(f"    Date: {item.published_date}\n")
