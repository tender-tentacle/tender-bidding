"""
Router tests for Company Subsidies & Grants API routes via FastAPI TestClient
==============================================================================
Tests that /api/v1/companies/{company_name}/subsidies resolves correctly without 404.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.asyncio
async def test_get_company_subsidies_router_path_resolves():
    """Verify GET /api/v1/companies/{company_name}/subsidies returns 200 (not 404)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/companies/Beschaffungsamt%20des%20BMI/subsidies")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_company_subsidies_router_complex_name():
    """Verify company names with commas and spaces resolve without 404."""
    complex_name = "Bundesrepublik Deutschland, vertreten durch das Bundesministerium des Innern, vertreten durch das Beschaffungsamt des BMI"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/companies/{complex_name}/subsidies")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


@pytest.mark.asyncio
async def test_post_company_subsidies_scrape_router():
    """Verify POST /api/v1/companies/{company_name}/subsidies/scrape returns 200 (not 404)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/companies/Beschaffungsamt%20des%20BMI/subsidies/scrape")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
