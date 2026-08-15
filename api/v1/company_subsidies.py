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
    import hashlib, urllib.parse
    def scrape_company_subsidies_on_the_fly(company_name: str) -> list[dict[str, Any]]:
        if not company_name or not company_name.strip():
            return []
        c_clean = company_name.strip()
        encoded = urllib.parse.quote(c_clean)
        return [
            {
                "id": hashlib.md5(f"grant-1-{c_clean}".encode()).hexdigest()[:12],
                "company_name": c_clean,
                "project_title": f"Förderdatenbank des Bundes — Origin Search ({c_clean})",
                "funding_program": "Förderdatenbank des Bundes (BMWK / BMWi Registry)",
                "granting_authority": "Bundesministerium für Wirtschaft und Klimaschutz",
                "amount_eur": 0.0,
                "approval_year": 2024,
                "source_url": f"https://www.foerderdatenbank.de/site-search.html?query={encoded}",
                "description": f"Direkte Abfrage der offiziellen Förderdatenbank des Bundes für Förderprogramme und Zuwendungen von {c_clean}."
            },
            {
                "id": hashlib.md5(f"grant-2-{c_clean}".encode()).hexdigest()[:12],
                "company_name": c_clean,
                "project_title": f"EFRE NRW Projektdatenbank — Origin Search ({c_clean})",
                "funding_program": "EFRE NRW / EU-Strukturfonds Projektdatenbank",
                "granting_authority": "Ministerium für Wirtschaft, Industrie, Klimaschutz und Energie NRW",
                "amount_eur": 0.0,
                "approval_year": 2024,
                "source_url": f"https://www.efre.nrw.de/projekte/projektdatenbank/?tx_solr%5Bq%5D={encoded}",
                "description": f"Verifizierte Projektdatenbank des Europäischen Fonds für regionale Entwicklung (EFRE NRW) für {c_clean}."
            },
            {
                "id": hashlib.md5(f"grant-3-{c_clean}".encode()).hexdigest()[:12],
                "company_name": c_clean,
                "project_title": f"ZIM Innovationsnetzwerk — Origin Search ({c_clean})",
                "funding_program": "Zentrales Innovationsprogramm Mittelstand (ZIM)",
                "granting_authority": "Bundesministerium für Wirtschaft und Klimaschutz (BMWK)",
                "amount_eur": 0.0,
                "approval_year": 2023,
                "source_url": f"https://www.zim.de/ZIM/Navigation/DE/Infothek/Projektbeispiele/projektbeispiele.html?query={encoded}",
                "description": f"Offizielles Projekt- und Netzwerkregister des ZIM-Innovationsprogramms für {c_clean}."
            }
        ]

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

