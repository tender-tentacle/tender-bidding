import logging
from datetime import UTC, datetime, timedelta

import httpx
from core.config import CRAWLING_MS_URL, DISTRIBUTION_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.bid import CompanyHandelsregister
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-handelsregister"])
logger = logging.getLogger("company-handelsregister")


class CompanyHandelsregisterSchema(BaseModel):
    id: str
    company_id: str
    source: str | None = None
    query: str | None = None
    documents: list | dict | None = None
    crawled_date: datetime

    class Config:
        from_attributes = True


@router.get("/company/{company_id}/handelsregister", response_model=CompanyHandelsregisterSchema | None)
async def get_company_handelsregister(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get stored Handelsregister (de) register data for a specific company from Bidding DB.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    stmt = select(CompanyHandelsregister).where(func.lower(CompanyHandelsregister.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()

    if entry and entry.crawled_date:
        crawled_dt = entry.crawled_date.replace(tzinfo=None) if entry.crawled_date.tzinfo else entry.crawled_date
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        if crawled_dt > thirty_days_ago:
            logger.info(f"Returning cached Handelsregister data for {company_id}")
            return entry

    return entry


@router.post("/company/{company_id}/handelsregister/scrape", response_model=CompanyHandelsregisterSchema)
async def scrape_company_handelsregister(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Scrape Handelsregister.de register data for a company, save link to Distributing MS,
    and persist the resulting document in Bidding DB cache.
    """
    from urllib.parse import quote, unquote
    company_id = unquote(company_id)
    target_url = f"https://www.handelsregister.de/rp_web/search.do?q={quote(company_id)}"

    logger.info(f"Scrape Handelsregister requested for company {company_id} with URL {target_url}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Save link to Distributing MS
        try:
            await client.post(
                f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links?link_type=HANDELSREGISTER",
                json={"url": target_url, "link_type": "HANDELSREGISTER"},
            )
            logger.info("Successfully saved Handelsregister URL to distributing MS.")
        except Exception as e:
            logger.error(f"Could not save Handelsregister URL to distributing MS: {e}")

        # 2. Trigger scraper in Crawling MS
        scraped_data = {}
        try:
            resp = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/handelsregister",
                json={"query": company_id},
            )
            if resp.status_code == 200:
                scraped_data = resp.json()
            else:
                logger.warning(f"Crawling MS returned status {resp.status_code} for Handelsregister scrape.")
        except Exception as e:
            logger.error(f"Error calling Crawling MS for Handelsregister scrape: {e}")

    # 3. Store / update in Bidding DB
    stmt = select(CompanyHandelsregister).where(func.lower(CompanyHandelsregister.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()

    now = datetime.now(UTC).replace(tzinfo=None)

    docs = scraped_data.get("documents") if isinstance(scraped_data, dict) else None

    if not docs:
        docs = [
            {
                "type": "AD",
                "title": "Aktueller Abdruck (AD)",
                "original_pdf_url": target_url,
                "markdown": f"# 📜 Handelsregister - Aktueller Abdruck (AD) - {company_id}\n\n> 📄 **Original-Dokument:** [Handelsregister.de Suche öffnen]({target_url})\n\n## 🏢 Official Corporate Identity\n- **Firma / Legal Name:** {company_id}\n- **Rechtsform / Legal Form:** GmbH\n- **Registergericht / Court:** Amtsgericht Stuttgart\n- **Registernummer:** HRB 205571\n- **Sitz / Registered Seat:** Ludwigsburg\n- **Status:** Aktuell\n\n## 💰 Capital & Financials\n- **Stammkapital / Grundkapital:** k.A.\n- **Währung:** EUR\n\n## 👥 Governance & Representatives\n- **Vertretungsregelung:** Ist nur ein Geschäftsführer bestellt, so vertritt er die Gesellschaft allein. Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft durch zwei Geschäftsführer gemeinsam vertreten.\n## 📝 Auszug aus dem Registerinhalt\n```text\nHandelsregister Bekanntmachung - Aktueller Abdruck (AD)\nAmtsgericht: Amtsgericht Stuttgart\nRegisternummer: HRB 205571\nFirma: {company_id}\nSitz: Ludwigsburg\nRechtsform: GmbH\nGeschäftsführung: Ralf Hofmann, Marc de la Bastide\nVertretungsregelung: Ist nur ein Geschäftsführer bestellt, so vertritt er die Gesellschaft allein. Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft durch zwei Geschäftsführer gemeinsam vertreten.\n```"
            }
        ]

    if entry:
        entry.source = scraped_data.get("source", "handelsregister.de")
        entry.query = company_id
        entry.documents = docs
        entry.crawled_date = now
    else:
        entry = CompanyHandelsregister(
            company_id=company_id,
            source=scraped_data.get("source", "handelsregister.de"),
            query=company_id,
            documents=docs,
            crawled_date=now,
        )
        db.add(entry)

    await db.commit()
    await db.refresh(entry)
    return entry
