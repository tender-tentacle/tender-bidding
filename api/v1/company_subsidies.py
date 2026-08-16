"""
Company Subsidies & Grants API (v1)
==================================
Provides endpoints to fetch and scrape open government grants & subsidies
awarded to companies from state/federal registries (GovData, ZIM, EFRE).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from core.scrapers.subsidies.govdata_subsidies.on_the_fly_scraper import (
        scrape_company_subsidies_on_the_fly,
    )
except ImportError:
    def scrape_company_subsidies_on_the_fly(company_name: str) -> list[dict[str, Any]]:
        return []

logger = logging.getLogger(__name__)

router = APIRouter(tags=["company-subsidies"])

# In-memory cache for company subsidy records
_SUBSIDY_CACHE: dict[str, list[dict[str, Any]]] = {}


class SubsidyGrantItem(BaseModel):
    id: str
    company_name: str
    project_title: str
    funding_program: str
    granting_authority: str
    amount_eur: float
    approval_year: int
    source_url: str
    description: str = ""


@router.get("/companies/{company_name}/subsidies", response_model=list[SubsidyGrantItem])
async def get_company_subsidies(
    company_name: str,
    force_refresh: bool = Query(False, description="Force on-the-fly re-scrape"),
):
    """Retrieve government grants and subsidies awarded to a company."""
    from urllib.parse import unquote
    company_name = unquote(company_name)
    if not company_name or not company_name.strip():
        raise HTTPException(status_code=400, detail="Company name is required")

    cache_key = company_name.strip().lower()
    if not force_refresh and cache_key in _SUBSIDY_CACHE:
        return _SUBSIDY_CACHE[cache_key]

    try:
        records = scrape_company_subsidies_on_the_fly(company_name.strip())
        _SUBSIDY_CACHE[cache_key] = records
        return records
    except Exception as exc:
        logger.error("Failed to fetch subsidies for %s: %s", company_name, exc)
        return _SUBSIDY_CACHE.get(cache_key, [])


@router.post("/companies/{company_name}/subsidies/scrape", response_model=list[SubsidyGrantItem])
async def scrape_company_subsidies(company_name: str):
    """Trigger on-the-fly scrape of government grant registries for a company."""
    from urllib.parse import unquote
    company_name = unquote(company_name)
    return await get_company_subsidies(company_name=company_name, force_refresh=True)

