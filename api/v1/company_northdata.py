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
    balance_sheet: dict | None = None
    financials: list | dict | None = None
    ownership: list | dict | None = None
    source_url: str | None = None
    crawled_date: datetime

    class Config:
        from_attributes = True


class ScrapeNorthDataRequest(BaseModel):
    url: str


@router.get("/company/{company_id:path}/northdata", response_model=CompanyNorthDataSchema | None)
async def get_company_northdata(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get stored North Data company master data for a specific company.
    """
    stmt = select(CompanyNorthData).where(func.lower(CompanyNorthData.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()
    return entry


@router.post("/company/{company_id:path}/northdata/scrape", response_model=CompanyNorthDataSchema)
async def scrape_company_northdata(company_id: str, request: ScrapeNorthDataRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually scrape North Data using a specific URL.
    Saves link to distributing MS and stores master data in Bidding MS.
    """
    from urllib.parse import quote

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
            balance_sheet=scraped_data.get("balance_sheet") or scraped_data.get("balance_sheet_2024"),
            financials=scraped_data.get("financials"),
            ownership=scraped_data.get("ownership"),
            source_url=request.url,
            crawled_date=datetime.now(UTC),
        )
        db.add(entry)
    else:
        entry.company_name = scraped_data.get("company_name") or entry.company_name
        entry.address = scraped_data.get("address") or entry.address
        entry.founding_date = scraped_data.get("founding_date") or entry.founding_date
        entry.register_court = scraped_data.get("register_court") or entry.register_court
        entry.register_number = scraped_data.get("register_number") or entry.register_number
        entry.euid = scraped_data.get("euid") or entry.euid
        entry.lei_code = scraped_data.get("lei_code") or entry.lei_code
        entry.business_purpose = scraped_data.get("business_purpose") or entry.business_purpose
        entry.former_names = scraped_data.get("former_names") or entry.former_names
        entry.other_registers = scraped_data.get("other_registers") or entry.other_registers
        entry.officers = scraped_data.get("officers") or entry.officers
        entry.events = scraped_data.get("events") or entry.events
        entry.balance_sheet = scraped_data.get("balance_sheet") or scraped_data.get("balance_sheet_2024") or entry.balance_sheet
        entry.financials = scraped_data.get("financials") or entry.financials
        entry.ownership = scraped_data.get("ownership") or entry.ownership
        entry.source_url = request.url
        entry.crawled_date = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except Exception as e:
        logger.error(f"Error saving North Data for {company_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving North Data")
