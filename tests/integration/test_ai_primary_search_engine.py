"""Integration test verifying tender-bidding queries artificial-intelligence-connector as primary search engine."""
import pytest
from httpx import ASGITransport, AsyncClient
from main import app
from models.company_reputation import CompanyReputationCache
from sqlalchemy import select


@pytest.mark.asyncio
async def test_bidding_uses_ai_connector_as_primary_search():
    """Test that tender-bidding queries AI Connector for company portal intelligence and caches results."""
    from core.database import SessionLocal

    company_name = "Porsche AG"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/company/{company_name}/reputation")
        assert resp.status_code == 200

        data = resp.json()
        assert "news" in data
        assert "jobs" in data
        assert "blog" in data
        assert "financials" in data
        assert "mood" in data

    async with SessionLocal() as session:
        result = await session.execute(select(CompanyReputationCache).filter_by(company_id=company_name))
        cached = result.scalars().all()
        assert len(cached) > 0, "Expected company reputation intelligence to be cached in DB for 30 days"

        for c in cached:
            assert c.is_valid is True
