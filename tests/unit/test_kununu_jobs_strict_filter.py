import pytest
from datetime import UTC, datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker
from models.bid import CompanyJobEntry
from main import app
from core.database import engine

@pytest.mark.asyncio
async def test_get_company_jobs_strict_kununu_filtering():
    """
    Reproduction test for bug: 'Kununu jobs are not kununu jobs!'
    GET /company/{company_id}/jobs must ONLY return entries where source_url/url contains 'kununu'.
    Non-Kununu jobs (e.g. Arbeitsagentur or state procurement portal jobs with custom domains like hessen.de) must NOT be returned.
    """
    company_id = "Test Company BVL"
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as db:
        # 1. Add non-Kununu job entry with non-standard domain (e.g. state portal, regional authority)
        regional_portal_job = CompanyJobEntry(
            company_id=company_id,
            hash="hash-regional-456",
            title="Hessen IT Spezialist CSIRT",
            location="Wiesbaden",
            source_url="https://jobs.hzd.hessen.de/S2-20264502",
            url="https://jobs.hzd.hessen.de/S2-20264502",
            crawled_date=datetime.now(UTC)
        )
        
        # 2. Add genuine Kununu job entry
        kununu_job = CompanyJobEntry(
            company_id=company_id,
            hash="hash-kununu-789",
            title="Genuine Kununu Software Developer",
            location="Stuttgart",
            source_url="https://www.kununu.com/de/test-company/jobs/789",
            url="https://www.kununu.com/de/test-company/jobs/789",
            crawled_date=datetime.now(UTC)
        )
        
        db.add_all([regional_portal_job, kununu_job])
        await db.commit()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/company/{company_id}/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        
        # Must ONLY return the 1 genuine Kununu job, excluding regional/state portal jobs
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Genuine Kununu Software Developer"
        assert "kununu" in jobs[0]["source_url"].lower()
