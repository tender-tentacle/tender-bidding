"""
Router tests for Company Subsidies & Grants API routes via FastAPI TestClient
==============================================================================
Tests that /api/v1/companies/{company_name}/subsidies resolves correctly without 404.
"""

from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient
from main import app

MOCK_SUBSIDY_ITEM = {
    "id": "sub-1",
    "company_name": "Beschaffungsamt des BMI",
    "project_title": "Lärmschutz und Dekarbonisierung",
    "funding_program": "Umweltförderung",
    "granting_authority": "BMDV",
    "amount_eur": 450000.0,
    "approval_year": 2025,
    "source_url": "https://govdata.de/subsidies/sub-1",
    "description": "Gefördertes Dekarbonisierungsprojekt"
}

@pytest.mark.asyncio
async def test_get_company_subsidies_router_path_resolves():
    """Verify GET /api/v1/companies/{company_name}/subsidies returns 200 (not 404)."""
    with patch("api.v1.company_subsidies.scrape_company_subsidies_on_the_fly", return_value=[MOCK_SUBSIDY_ITEM]):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/companies/Beschaffungsamt%20des%20BMI/subsidies?force_refresh=true")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_company_subsidies_router_complex_name():
    """Verify company names with commas and spaces resolve without 404."""
    complex_name = "Bundesrepublik Deutschland, vertreten durch das Bundesministerium des Innern, vertreten durch das Beschaffungsamt des BMI"
    with patch("api.v1.company_subsidies.scrape_company_subsidies_on_the_fly", return_value=[MOCK_SUBSIDY_ITEM]):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/companies/{complex_name}/subsidies?force_refresh=true")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1


@pytest.mark.asyncio
async def test_post_company_subsidies_scrape_router():
    """Verify POST /api/v1/companies/{company_name}/subsidies/scrape returns 200 (not 404)."""
    with patch("api.v1.company_subsidies.scrape_company_subsidies_on_the_fly", return_value=[MOCK_SUBSIDY_ITEM]):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/companies/Beschaffungsamt%20des%20BMI/subsidies/scrape")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert isinstance(data, list)
