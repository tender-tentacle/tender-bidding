"""
Unit tests for Company Subsidies & Grants API router
===================================================
"""

from unittest.mock import patch
import pytest
from api.v1.company_subsidies import get_company_subsidies, scrape_company_subsidies
from fastapi import HTTPException

MOCK_SUBSIDY_ITEM = {
    "id": "sub-1",
    "company_name": "Flughafen Stuttgart GmbH",
    "project_title": "Lärmschutz und Dekarbonisierung",
    "funding_program": "Umweltförderung",
    "granting_authority": "BMDV",
    "amount_eur": 450000.0,
    "approval_year": 2025,
    "source_url": "https://govdata.de/subsidies/sub-1",
    "description": "Gefördertes Dekarbonisierungsprojekt"
}

@pytest.mark.asyncio
async def test_get_company_subsidies_endpoint():
    with patch("api.v1.company_subsidies.scrape_company_subsidies_on_the_fly", return_value=[MOCK_SUBSIDY_ITEM]):
        data = await get_company_subsidies(company_name="Flughafen Stuttgart GmbH", force_refresh=True)
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        assert hasattr(first, "project_title") or "project_title" in first

@pytest.mark.asyncio
async def test_scrape_company_subsidies_endpoint():
    with patch("api.v1.company_subsidies.scrape_company_subsidies_on_the_fly", return_value=[MOCK_SUBSIDY_ITEM]):
        data = await scrape_company_subsidies(company_name="Flughafen Stuttgart GmbH")
        assert isinstance(data, list)
        assert len(data) >= 1

@pytest.mark.asyncio
async def test_get_company_subsidies_empty():
    with pytest.raises(HTTPException) as exc_info:
        await get_company_subsidies(company_name="")
    assert exc_info.value.status_code == 400
