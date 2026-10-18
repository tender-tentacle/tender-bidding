import logging
from datetime import UTC, datetime, timedelta

import httpx
from core.config import DISTRIBUTION_MS_URL, MARKET_RESEARCH_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends
from models.bid import CompanyHandelsregister, CompanyNorthData
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

        # 2. Trigger scraper in Market Research MS
        scraped_data = {}
        try:
            resp = await client.post(
                f"{MARKET_RESEARCH_MS_URL}/api/v1/scrape/handelsregister",
                json={"query": company_id},
            )
            if resp.status_code == 200:
                scraped_data = resp.json()
            else:
                logger.warning(f"Market Research MS returned status {resp.status_code} for Handelsregister scrape.")
        except Exception as e:
            logger.error(f"Error calling Market Research MS for Handelsregister scrape: {e}")

    # 3. Store / update in Bidding DB
    stmt = select(CompanyHandelsregister).where(func.lower(CompanyHandelsregister.company_id) == company_id.lower())
    res = await db.execute(stmt)
    entry = res.scalars().first()

    now = datetime.now(UTC).replace(tzinfo=None)

    docs = scraped_data.get("documents") if isinstance(scraped_data, dict) else None

    # Check if North Data is available to enrich Register Court & Number
    res_nd = await db.execute(select(CompanyNorthData).where(func.lower(CompanyNorthData.company_id) == company_id.lower()))
    nd_entry = res_nd.scalars().first()

    court = nd_entry.register_court if nd_entry and nd_entry.register_court else "Amtsgericht"
    reg_num = nd_entry.register_number if nd_entry and nd_entry.register_number else "k.A."
    capital = nd_entry.balance_sheet.get("stammkapital", "k.A.") if nd_entry and isinstance(nd_entry.balance_sheet, dict) else "k.A."
    seat = getattr(nd_entry, "city", None) or "Deutschland"
    legal_form = getattr(nd_entry, "legal_form", None) or "k.A."
    officers_list = [o.get("name", "") for o in (nd_entry.officers or []) if isinstance(o, dict) and o.get("name")] if nd_entry else []
    management = ", ".join(officers_list) if officers_list else "k.A."

    if not docs:
        docs = [
            {
                "type": "AD",
                "title": "Aktueller Abdruck (AD)",
                "original_pdf_url": target_url,
                "markdown": (
                    f"# 📜 Handelsregister - Aktueller Abdruck (AD) - {company_id}\n\n"
                    f"> 📄 **Original-Dokument:** [Handelsregister.de Suche öffnen]({target_url})\n\n"
                    f"## 🏢 Official Corporate Identity\n"
                    f"- **Firma / Legal Name:** {company_id}\n"
                    f"- **Rechtsform / Legal Form:** {legal_form}\n"
                    f"- **Registergericht / Court:** {court}\n"
                    f"- **Registernummer:** {reg_num}\n"
                    f"- **Sitz / Registered Seat:** {seat}\n"
                    f"- **Status:** Aktuell\n\n"
                    f"## 💰 Capital & Financials\n"
                    f"- **Stammkapital / Grundkapital:** {capital}\n"
                    f"- **Währung:** EUR\n\n"
                    f"## 👥 Governance & Representatives\n"
                    f"- **Vertretungsregelung:** Gesetzliche Vertretungsregelung gemäß Handelsregister.\n\n"
                    f"## 📝 Auszug aus dem Registerinhalt\n"
                    f"Handelsregister Bekanntmachung - Aktueller Abdruck (AD)\n"
                    f"Amtsgericht: {court}\n"
                    f"Registernummer: {reg_num}\n"
                    f"Firma: {company_id}\n"
                    f"Sitz: {seat}\n"
                    f"Rechtsform: {legal_form}\n"
                    f"Geschäftsführung / Vorstand: {management}\n"
                    f"Vertretungsregelung: Gesetzliche Vertretungsregelung gemäß Registerinhalt."
                )
            }
        ]
    elif docs and isinstance(docs, list) and nd_entry:
        for d in docs:
            if isinstance(d, dict) and "markdown" in d:
                md = d["markdown"]
                if "Registernummer: k.A." in md and reg_num != "k.A.":
                    md = md.replace("Registernummer: k.A.", f"Registernummer: {reg_num}")
                if "Registergericht / Court: Amtsgericht" in md and court != "Amtsgericht":
                    md = md.replace("Registergericht / Court: Amtsgericht", f"Registergericht / Court: {court}")
                if "Amtsgericht: Amtsgericht" in md and court != "Amtsgericht":
                    md = md.replace("Amtsgericht: Amtsgericht", f"Amtsgericht: {court}")
                if "Geschäftsführung / Vorstand: k.A." in md and management != "k.A.":
                    md = md.replace("Geschäftsführung / Vorstand: k.A.", f"Geschäftsführung / Vorstand: {management}")
                d["markdown"] = md

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
