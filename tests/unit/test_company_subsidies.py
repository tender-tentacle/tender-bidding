"""
Unit tests for Company Subsidies & Grants API router
===================================================
"""

import pytest
from fastapi import HTTPException
from api.v1.company_subsidies import get_company_subsidies, scrape_company_subsidies


@pytest.mark.asyncio
async def test_get_company_subsidies_endpoint():
    data = await get_company_subsidies(company_name="Flughafen Stuttgart GmbH")
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert hasattr(first, "project_title") or "project_title" in first
    assert hasattr(first, "funding_program") or "funding_program" in first
    assert hasattr(first, "granting_authority") or "granting_authority" in first
    assert hasattr(first, "amount_eur") or "amount_eur" in first
    assert hasattr(first, "approval_year") or "approval_year" in first


@pytest.mark.asyncio
async def test_scrape_company_subsidies_endpoint():
    data = await scrape_company_subsidies(company_name="Flughafen Stuttgart GmbH")
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_company_subsidies_empty():
    with pytest.raises(HTTPException) as exc_info:
        await get_company_subsidies(company_name="")
    assert exc_info.value.status_code == 400
