import logging
from datetime import UTC, datetime

import httpx
from core.config import CRAWLING_MS_URL, DISTRIBUTION_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.bid import CompanyNorthData
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-northdata"])
logger = logging.getLogger("company-northdata")


class CompanyNorthDataSchema(BaseModel):
    id: str
    company_id: str
    company_name: str | None = None
    address: str | None = None
    founding_date: str | None = None
    register_court: str | None = None
    register_number: str | None = None
    euid: str | None = None
    lei_code: str | None = None
    business_purpose: str | None = None
    former_names: list | dict | None = None
    other_registers: list | dict | None = None
    officers: list | dict | None = None
    events: list | dict | None = None
    history_timeline: list | dict | None = None
    persons_timeline: list | dict | None = None
    marketing_tech: list | dict | None = None
    tab_metrics: dict | list | None = None
    network_links: list | dict | None = None
    balance_sheet: dict | None = None
    financials: list | dict | None = None
    ownership: list | dict | None = None
    svg_diagrams: list | dict | None = None
    source_url: str | None = None
    is_valid_profile: bool | None = True
    no_profile_found: bool | None = False
    no_profile_reason: str | None = None
    crawled_date: datetime

    class Config:
        from_attributes = True


class ScrapeNorthDataRequest(BaseModel):
    url: str


@router.get("/company/{company_id}/northdata", response_model=CompanyNorthDataSchema | None)
async def get_company_northdata(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get stored North Data company master data for a specific company.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    stmt = select(CompanyNorthData).where(func.lower(CompanyNorthData.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()
    return entry


@router.post("/company/{company_id}/northdata/scrape", response_model=CompanyNorthDataSchema)
async def scrape_company_northdata(company_id: str, request: ScrapeNorthDataRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually scrape North Data using a specific URL.
    Saves link to distributing MS and stores master data in Bidding MS.
    """
    from urllib.parse import quote, unquote
    company_id = unquote(company_id)

    target_url = (
        request.url.strip()
        if request.url and ("northdata.de" in request.url or "northdata.com" in request.url or "northdata." in request.url)
        else f"https://www.northdata.de/{quote(company_id)}"
    )
    logger.info(f"Manual North Data scrape requested for {company_id} with URL {target_url} (raw: {request.url})")


    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Save link to Distributing MS
        try:
            await client.post(
                f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links?link_type=NORTHDATA",
                json={"url": target_url, "link_type": "NORTHDATA"},
            )
            logger.info("Successfully saved North Data URL to distributing MS.")
        except Exception as e:
            logger.error(f"Could not save North Data URL to distributing MS: {e}")

        # 2. Trigger scraper in Crawling MS
        scraped_data = {}
        try:
            resp = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/northdata",
                json={"query": company_id, "url": target_url},
            )
            resp.raise_for_status()
            scraped_data = resp.json()
        except Exception as e:
            logger.error(f"Scraping North Data failed for {company_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Scraping North Data failed: {e}")

    # 3. Save / Update in DB
    stmt = select(CompanyNorthData).where(func.lower(CompanyNorthData.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()

    if not entry:
        entry = CompanyNorthData(
            company_id=company_id,
            company_name=scraped_data.get("company_name"),
            address=scraped_data.get("address"),
            founding_date=scraped_data.get("founding_date"),
            register_court=scraped_data.get("register_court"),
            register_number=scraped_data.get("register_number"),
            euid=scraped_data.get("euid"),
            lei_code=scraped_data.get("lei_code"),
            business_purpose=scraped_data.get("business_purpose"),
            former_names=scraped_data.get("former_names"),
            other_registers=scraped_data.get("other_registers"),
            officers=scraped_data.get("officers"),
            events=scraped_data.get("events"),
            history_timeline=scraped_data.get("history_timeline"),
            persons_timeline=scraped_data.get("persons_timeline"),
            marketing_tech=scraped_data.get("marketing_tech"),
            tab_metrics=scraped_data.get("tab_metrics"),
            network_links=scraped_data.get("network_links"),
            balance_sheet=scraped_data.get("balance_sheet") or scraped_data.get("balance_sheet_2024"),
            financials=scraped_data.get("financials"),
            ownership=scraped_data.get("ownership"),
            svg_diagrams=scraped_data.get("svg_diagrams"),
            source_url=request.url,
            is_valid_profile=scraped_data.get("is_valid_profile", True),
            no_profile_found=scraped_data.get("no_profile_found", False),
            no_profile_reason=scraped_data.get("no_profile_reason"),
            crawled_date=datetime.now(UTC),
        )
        db.add(entry)
    else:
        entry.company_name = scraped_data.get("company_name") if scraped_data.get("company_name") is not None else entry.company_name
        entry.address = scraped_data.get("address") or entry.address
        entry.founding_date = scraped_data.get("founding_date") or entry.founding_date
        entry.register_court = scraped_data.get("register_court")
        entry.register_number = scraped_data.get("register_number")
        entry.euid = scraped_data.get("euid")
        entry.lei_code = scraped_data.get("lei_code") or entry.lei_code
        entry.business_purpose = scraped_data.get("business_purpose") or entry.business_purpose
        entry.former_names = scraped_data.get("former_names") or entry.former_names
        entry.other_registers = scraped_data.get("other_registers") or entry.other_registers
        entry.officers = scraped_data.get("officers") or entry.officers
        entry.events = scraped_data.get("events") or entry.events
        if "history_timeline" in scraped_data and scraped_data["history_timeline"] is not None:
            entry.history_timeline = scraped_data["history_timeline"]
        if "persons_timeline" in scraped_data and scraped_data["persons_timeline"] is not None:
            entry.persons_timeline = scraped_data["persons_timeline"]
        if "marketing_tech" in scraped_data and scraped_data["marketing_tech"] is not None:
            entry.marketing_tech = scraped_data["marketing_tech"]
        if "tab_metrics" in scraped_data and scraped_data["tab_metrics"] is not None:
            entry.tab_metrics = scraped_data["tab_metrics"]
        if "network_links" in scraped_data and scraped_data["network_links"] is not None:
            entry.network_links = scraped_data["network_links"]
        entry.balance_sheet = scraped_data.get("balance_sheet") or scraped_data.get("balance_sheet_2024") or entry.balance_sheet
        entry.financials = scraped_data.get("financials") or entry.financials
        entry.ownership = scraped_data.get("ownership") or entry.ownership
        entry.svg_diagrams = scraped_data.get("svg_diagrams") or entry.svg_diagrams
        entry.source_url = request.url
        entry.is_valid_profile = scraped_data.get("is_valid_profile", True)
        entry.no_profile_found = scraped_data.get("no_profile_found", False)
        entry.no_profile_reason = scraped_data.get("no_profile_reason")
        entry.crawled_date = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except Exception as e:
        logger.error(f"Error saving North Data for {company_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving North Data")
