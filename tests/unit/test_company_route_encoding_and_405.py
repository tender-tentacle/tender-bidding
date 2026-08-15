import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.asyncio
async def test_company_routes_accept_ids_without_405():
    """Verify POST and GET routes on company endpoints do not return 405 Method Not Allowed."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # POST /company/TestCompany/jobsuche/scrape
        res_jobsuche = await client.post("/api/v1/company/TestCompany/jobsuche/scrape")
        assert res_jobsuche.status_code != 405, f"Expected non-405, got {res_jobsuche.status_code}"

        # POST /company/Group-0fd3333b-d111-462b-9ae3-d70618bcc746/northdata/scrape
        res_northdata = await client.post("/api/v1/company/Group-0fd3333b-d111-462b-9ae3-d70618bcc746/northdata/scrape", json={"url": "https://www.northdata.de/Test"})
        assert res_northdata.status_code != 405, f"Expected non-405, got {res_northdata.status_code}"

        # GET /company/TestCompany/profile
        res_profile = await client.get("/api/v1/company/TestCompany/profile")
        assert res_profile.status_code != 405, f"Expected non-405, got {res_profile.status_code}"

        # POST /company/TestCompany/servicebund_jobs/scrape
        res_servicebund = await client.post("/api/v1/company/TestCompany/servicebund_jobs/scrape")
        assert res_servicebund.status_code != 405, f"Expected non-405, got {res_servicebund.status_code}"
