import logging
import re
from datetime import UTC, datetime, timedelta

import httpx
from core.config import CRAWLING_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.bid import CompanyJobEntry
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-jobs"])
logger = logging.getLogger("company-jobs")


class CompanyJobSchema(BaseModel):
    id: str
    company_id: str
    hash: str
    title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    published_date: str | None = None
    description: str | None = None
    url: str | None = None
    crawled_date: datetime
    source_url: str | None = None

    class Config:
        from_attributes = True


@router.get("/company/{company_id}/jobsuche", response_model=list[CompanyJobSchema])
async def get_company_arbeitsagentur_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get Arbeitsagentur open job positions for a specific company.
    If no recent data is found (last 30 days), auto-triggers the Arbeitsagentur scraper.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    stmt = select(CompanyJobEntry).where(
        (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
        (func.lower(CompanyJobEntry.company_id).contains(company_id.lower())),
        (CompanyJobEntry.crawled_date >= thirty_days_ago) | (CompanyJobEntry.crawled_date.is_(None))
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    ba_entries = [
        e for e in entries
        if e.source_url and ("arbeitsagentur" in e.source_url.lower() or "jobboerse" in e.source_url.lower())
    ]

    if ba_entries:
        return ba_entries

    logger.info(f"No recent Arbeitsagentur data for '{company_id}'. Auto-triggering scraper...")
    return await scrape_company_arbeitsagentur_jobs(company_id=company_id, db=db)


@router.post("/company/{company_id}/jobsuche/scrape", response_model=list[CompanyJobSchema])
async def scrape_company_arbeitsagentur_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Manually scrape Arbeitsagentur Jobsuche API on-the-fly for a specific company and save results to Bidding MS.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    search_query = re.sub(r"\(.*?\)", "", company_id)
    search_query = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", search_query, flags=re.IGNORECASE)
    search_query = " ".join(search_query.split())

    logger.info(f"Triggering manual BA Jobsuche scrape for company '{company_id}' using query '{search_query}'")

    scraped_entries = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/jobsuche",
                json={"query": search_query}
            )
            if crawling_response.status_code == 200:
                scraped_entries = crawling_response.json() or []
        except Exception as e:
            logger.warning(f"Crawling MS unavailable, using direct JobsucheScraper fallback: {e}")
            try:
                import importlib.util
                import os

                crawling_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tender-crawling/core/scrapers/jobsuche/on_the_fly_scraper.py"))
                if os.path.exists(crawling_path):
                    spec = importlib.util.spec_from_file_location("on_the_fly_scraper", crawling_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    scraper = mod.JobsucheScraper(query=company_id)
                    scraped_entries = scraper.fetch_jobs()
            except Exception as inner_e:
                logger.error(f"Fallback scraper error: {inner_e}")
                scraped_entries = []

    new_entries = []
    has_updates = False
    for entry in scraped_entries:
        entry_hash = entry.get("hash")
        if not entry_hash:
            continue
        stmt_check = select(CompanyJobEntry).where(
            (CompanyJobEntry.hash == entry_hash) |
            ((func.lower(CompanyJobEntry.company_id) == company_id.lower()) & (CompanyJobEntry.title == entry.get("title")))
        )
        res = await db.execute(stmt_check)
        existing = res.scalars().first()

        detail_url = entry.get("source_url") or entry.get("url") or "https://www.arbeitsagentur.de/jobsuche"
        desc = entry.get("description")

        if existing:
            if detail_url and "jobdetail" in detail_url and existing.source_url != detail_url:
                existing.url = detail_url
                existing.source_url = detail_url
                has_updates = True
            if desc and existing.description != desc:
                existing.description = desc
                has_updates = True
            if entry.get("location") and existing.location != entry.get("location"):
                existing.location = entry.get("location")
                has_updates = True
            continue

        new_entry = CompanyJobEntry(
            company_id=company_id,
            hash=entry_hash,
            title=entry.get("title"),
            location=entry.get("location"),
            employment_type=entry.get("employment_type"),
            published_date=entry.get("published_at"),
            description=desc,
            url=detail_url,
            source_url=detail_url,
        )
        db.add(new_entry)
        new_entries.append(new_entry)

    if new_entries or has_updates:
        try:
            await db.commit()
        except Exception as e:
            logger.error(f"Error saving Arbeitsagentur Jobsuche entries: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Database error while saving Arbeitsagentur jobs")

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    stmt = select(CompanyJobEntry).where(
        (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
        (func.lower(CompanyJobEntry.company_id).contains(company_id.lower())),
        (CompanyJobEntry.crawled_date >= thirty_days_ago) | (CompanyJobEntry.crawled_date.is_(None))
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return [
        e for e in entries
        if e.source_url and ("arbeitsagentur" in e.source_url.lower() or "jobboerse" in e.source_url.lower())
    ]


@router.get("/company/{company_id}/servicebund_jobs", response_model=list[CompanyJobSchema])
async def get_company_servicebund_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get Bund.de (service.bund.de) open job positions for a specific company.
    If no recent data is found (last 30 days), auto-triggers the service.bund.de scraper.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    stmt = select(CompanyJobEntry).where(
        (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
        (func.lower(CompanyJobEntry.company_id).contains(company_id.lower())),
        (CompanyJobEntry.crawled_date >= thirty_days_ago) | (CompanyJobEntry.crawled_date.is_(None))
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    sb_entries = [
        e for e in entries
        if e.source_url and ("service.bund.de" in e.source_url.lower() or "bund.de" in e.source_url.lower())
    ]

    if sb_entries:
        return sb_entries

    logger.info(f"No recent Bund.de data for '{company_id}'. Auto-triggering scraper...")
    return await scrape_company_servicebund_jobs(company_id=company_id, db=db)


@router.post("/company/{company_id}/servicebund_jobs/scrape", response_model=list[CompanyJobSchema])
async def scrape_company_servicebund_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Manually scrape service.bund.de Stellenangebote on-the-fly for a specific company and save results to Bidding MS.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    search_query = re.sub(r"\(.*?\)", "", company_id)
    search_query = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", search_query, flags=re.IGNORECASE)
    search_query = " ".join(search_query.split())

    logger.info(f"Triggering manual Bund.de scrape for company '{company_id}' using query '{search_query}'")

    scraped_entries = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/servicebund_jobs",
                json={"query": search_query or company_id}
            )
            if crawling_response.status_code == 200:
                scraped_entries = crawling_response.json() or []
        except Exception as e:
            logger.warning(f"Crawling MS unavailable, using direct ServiceBundJobsScraper fallback: {e}")
            try:
                import importlib.util
                import os

                crawling_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tender-crawling/core/scrapers/jobs/servicebund/on_the_fly_scraper.py"))
                if os.path.exists(crawling_path):
                    spec = importlib.util.spec_from_file_location("sb_on_the_fly_scraper", crawling_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    scraper = mod.ServiceBundJobsScraper(query=search_query or company_id)
                    scraped_entries = scraper.fetch_jobs(fetch_details=True)
            except Exception as inner_e:
                logger.error(f"Fallback scraper error: {inner_e}")
                scraped_entries = []

    new_entries = []
    has_updates = False
    for entry in scraped_entries:
        entry_hash = entry.get("hash")
        if not entry_hash:
            continue
        stmt_check = select(CompanyJobEntry).where(
            (CompanyJobEntry.hash == entry_hash) |
            ((func.lower(CompanyJobEntry.company_id) == company_id.lower()) & (CompanyJobEntry.title == entry.get("title")))
        )
        res = await db.execute(stmt_check)
        existing = res.scalars().first()
        detail_url = entry.get("source_url") or entry.get("url") or "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
        desc = entry.get("description") or entry.get("field_of_activity") or entry.get("reference_number")
        if existing:
            if detail_url and existing.source_url != detail_url:
                existing.url = detail_url
                existing.source_url = detail_url
                has_updates = True
            if entry.get("location") and existing.location != entry.get("location"):
                existing.location = entry.get("location")
                has_updates = True
            if desc and existing.description != desc:
                existing.description = desc
                has_updates = True
            continue

        new_entry = CompanyJobEntry(
            company_id=company_id,
            hash=entry_hash,
            title=entry.get("title"),
            location=entry.get("location"),
            employment_type=entry.get("employment_type") or entry.get("field_of_activity"),
            published_date=entry.get("published_at") or entry.get("published_date") or entry.get("application_deadline"),
            description=desc,
            url=detail_url,
            source_url=detail_url,
        )
        db.add(new_entry)
        new_entries.append(new_entry)

    if new_entries or has_updates:
        try:
            await db.commit()
        except Exception as e:
            logger.error(f"Error saving Bund.de job entries: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Database error while saving Bund.de jobs")

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    stmt = select(CompanyJobEntry).where(
        (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
        (func.lower(CompanyJobEntry.company_id).contains(company_id.lower())),
        (CompanyJobEntry.crawled_date >= thirty_days_ago) | (CompanyJobEntry.crawled_date.is_(None))
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return [
        e for e in entries
        if e.source_url and ("service.bund.de" in e.source_url.lower() or "bund.de" in e.source_url.lower())
    ]


@router.get("/company/{company_id}/jobs", response_model=list[CompanyJobSchema])
async def get_company_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get Kununu open job positions for a specific company.
    If no recent data is found (last 30 days), it will trigger the Kununu scraper.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    stmt = select(CompanyJobEntry).where(
        (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
        (func.lower(CompanyJobEntry.company_id).contains(company_id.lower())),
        (CompanyJobEntry.crawled_date >= thirty_days_ago) | (CompanyJobEntry.crawled_date.is_(None))
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    kununu_entries = [
        e for e in entries
        if (e.source_url and "kununu" in e.source_url.lower()) or (e.url and "kununu" in e.url.lower())
    ]

    if kununu_entries:
        logger.info(f"Returning {len(kununu_entries)} cached Kununu job entries for company {company_id}")
        return kununu_entries

    logger.info(f"No recent Kununu job data for {company_id}. Triggering scraper in crawling ms...")

    scraped_entries = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            kununu_jobs_resp = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/kununu/jobs", json={"query": company_id}, timeout=15.0
            )
            if kununu_jobs_resp.status_code == 200:
                k_jobs = kununu_jobs_resp.json()
                for kj in k_jobs:
                    job_url = kj.get("url") or f"https://www.kununu.com/de/{company_id}/jobs"
                    scraped_entries.append(
                        {
                            "hash": kj.get("hash"),
                            "title": kj.get("title"),
                            "location": kj.get("location"),
                            "employment_type": kj.get("employment_type"),
                            "published_at": kj.get("published_at"),
                            "source_url": job_url,
                            "url": job_url,
                        }
                    )
        except Exception as e:
            logger.warning(f"Kununu jobs scraping error: {e}")

        if not scraped_entries:
            logger.info(f"No live Kununu job data found for {company_id}. Returning empty list.")
            return []

    new_entries = []
    for entry in scraped_entries:
        entry_hash = entry.get("hash")
        if not entry_hash:
            continue
        stmt_check = select(CompanyJobEntry).where(CompanyJobEntry.hash == entry_hash)
        res = await db.execute(stmt_check)
        if res.scalars().first():
            continue

        new_entry = CompanyJobEntry(
            company_id=company_id,
            hash=entry_hash,
            title=entry.get("title"),
            location=entry.get("location"),
            employment_type=entry.get("employment_type"),
            published_date=entry.get("published_at"),
            source_url=entry.get("source_url"),
            url=entry.get("url") or entry.get("source_url"),
        )
        db.add(new_entry)
        new_entries.append(new_entry)

    try:
        if new_entries:
            await db.commit()
    except Exception as e:
        logger.error(f"Error saving Kununu job entries: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving jobs")

    result = await db.execute(
        select(CompanyJobEntry).where(
            (func.lower(CompanyJobEntry.company_id) == company_id.lower()) |
            (func.lower(CompanyJobEntry.company_id).contains(company_id.lower()))
        )
    )
    entries = result.scalars().all()
    return [
        e for e in entries
        if not (e.source_url and ("arbeitsagentur" in e.source_url.lower() or "jobboerse" in e.source_url.lower() or "bund.de" in e.source_url.lower() or "service.bund.de" in e.source_url.lower()))
        and not (e.url and ("arbeitsagentur" in e.url.lower() or "jobboerse" in e.url.lower() or "bund.de" in e.url.lower() or "service.bund.de" in e.url.lower()))
    ]

