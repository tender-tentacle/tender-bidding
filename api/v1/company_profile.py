import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from core.database import Base, get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()

# ── DATABASE MODEL ───────────────────────────────────────────────


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    company_id = Column(String(255), primary_key=True)
    description = Column(String(4000), nullable=True)
    full_text = Column(Text, nullable=True)
    logo_url = Column(String(1000), nullable=True)
    wikipedia_url = Column(String(1000), nullable=True)
    crawled_date = Column(DateTime(timezone=True), nullable=False)

    financial_summary = Column(String(4000), nullable=True)
    financial_summary_date = Column(DateTime(timezone=True), nullable=True)

    hiring_summary = Column(String(4000), nullable=True)
    hiring_summary_date = Column(DateTime(timezone=True), nullable=True)

    buyer_reputation_summary = Column(String(4000), nullable=True)
    buyer_reputation_summary_date = Column(DateTime(timezone=True), nullable=True)

    news_summary = Column(String(4000), nullable=True)
    news_summary_date = Column(DateTime(timezone=True), nullable=True)

    mhp_reputation_summary = Column(String(4000), nullable=True)
    mhp_reputation_summary_date = Column(DateTime(timezone=True), nullable=True)

    company_description = Column(String(4000), nullable=True)
    incumbent_advantage_summary = Column(String(4000), nullable=True)
    competitor_density_summary = Column(String(4000), nullable=True)

    # Service.bund.de Authority Metadata
    servicebund_url = Column(String(1000), nullable=True)
    servicebund_description = Column(String(4000), nullable=True)
    servicebund_main_address = Column(String(1000), nullable=True)
    servicebund_secondary_address = Column(String(1000), nullable=True)
    servicebund_phone = Column(String(100), nullable=True)
    servicebund_fax = Column(String(100), nullable=True)
    servicebund_email = Column(String(255), nullable=True)
    servicebund_website = Column(String(1000), nullable=True)


# ── SCHEMAS ──────────────────────────────────────────────────────


class CompanyProfileSchema(BaseModel):
    company_id: str
    description: str | None
    full_text: str | None = None
    logo_url: str | None
    wikipedia_url: str | None = None
    crawled_date: datetime

    financial_summary: str | None = None
    financial_summary_date: datetime | None = None

    hiring_summary: str | None = None
    hiring_summary_date: datetime | None = None

    buyer_reputation_summary: str | None = None
    buyer_reputation_summary_date: datetime | None = None

    news_summary: str | None = None
    news_summary_date: datetime | None = None

    mhp_reputation_summary: str | None = None
    mhp_reputation_summary_date: datetime | None = None

    company_description: str | None = None
    incumbent_advantage_summary: str | None = None
    competitor_density_summary: str | None = None

    servicebund_url: str | None = None
    servicebund_description: str | None = None
    servicebund_main_address: str | None = None
    servicebund_secondary_address: str | None = None
    servicebund_phone: str | None = None
    servicebund_fax: str | None = None
    servicebund_email: str | None = None
    servicebund_website: str | None = None

    class Config:
        from_attributes = True


# ── ENDPOINTS ────────────────────────────────────────────────────


@router.get("/company/{company_id}/profile", response_model=CompanyProfileSchema)
async def get_company_profile(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company profile from Wikipedia & Service.bund.de.
    If no recent data is found (younger than 30 days), trigger the scrapers.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    # DB stores naive UTC datetimes — compare naive UTC on both sides
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Check cache
    result = await db.execute(select(CompanyProfile).where(CompanyProfile.company_id == company_id))
    profile = result.scalars().first()

    if profile and profile.crawled_date:
        crawled_dt = profile.crawled_date.replace(tzinfo=None) if profile.crawled_date.tzinfo else profile.crawled_date
        if crawled_dt > thirty_days_ago and profile.description:
            logger.info(f"Returning cached profile for {company_id}")
            return profile

    # Needs fetching from crawling service
    logger.info(f"Triggering Wikipedia & Service.bund.de scrapers for {company_id}")
    crawling_url = os.getenv("CRAWLING_URL", "http://tender-crawling:8001")

    try:
        async with httpx.AsyncClient() as client:
            wiki_res = await client.post(
                f"{crawling_url}/api/v1/scrape/wikipedia", json={"query": company_id}, timeout=15
            )
            sb_res = await client.post(
                f"{crawling_url}/api/v1/scrape/servicebund_authority", json={"query": company_id}, timeout=15
            )

        wiki_data = wiki_res.json() if wiki_res.status_code == 200 else {}
        sb_data = sb_res.json() if sb_res.status_code == 200 else {}

        sb_main_addr = None
        if sb_data.get("main_address"):
            m = sb_data["main_address"]
            parts = [
                p
                for p in [
                    m.get("street"),
                    f"{m.get('zipcode', '')} {m.get('city', '')}".strip(),
                    m.get("state"),
                    m.get("country"),
                ]
                if p
            ]
            if parts:
                sb_main_addr = ", ".join(parts)

        sb_sec_addr = None
        if sb_data.get("secondary_address"):
            m = sb_data["secondary_address"]
            parts = [
                p
                for p in [
                    m.get("street"),
                    f"{m.get('zipcode', '')} {m.get('city', '')}".strip(),
                    m.get("state"),
                    m.get("country"),
                ]
                if p
            ]
            if parts:
                sb_sec_addr = ", ".join(parts)

        if profile:
            profile.description = wiki_data.get("description") or profile.description
            profile.full_text = wiki_data.get("full_text") or wiki_data.get("description") or profile.full_text
            profile.logo_url = wiki_data.get("logo_url") or profile.logo_url
            profile.wikipedia_url = wiki_data.get("wikipedia_url") or profile.wikipedia_url
            profile.servicebund_url = sb_data.get("url") or profile.servicebund_url
            profile.servicebund_description = sb_data.get("description") or profile.servicebund_description
            profile.servicebund_main_address = sb_main_addr or profile.servicebund_main_address
            profile.servicebund_secondary_address = sb_sec_addr or profile.servicebund_secondary_address
            profile.servicebund_phone = sb_data.get("phone") or profile.servicebund_phone
            profile.servicebund_fax = sb_data.get("fax") or profile.servicebund_fax
            profile.servicebund_email = sb_data.get("email") or profile.servicebund_email
            profile.servicebund_website = sb_data.get("website") or profile.servicebund_website
            profile.crawled_date = datetime.now(UTC).replace(tzinfo=None)
        else:
            profile = CompanyProfile(
                company_id=company_id,
                description=wiki_data.get("description"),
                full_text=wiki_data.get("full_text") or wiki_data.get("description"),
                logo_url=wiki_data.get("logo_url"),
                wikipedia_url=wiki_data.get("wikipedia_url"),
                servicebund_url=sb_data.get("url"),
                servicebund_description=sb_data.get("description"),
                servicebund_main_address=sb_main_addr,
                servicebund_secondary_address=sb_sec_addr,
                servicebund_phone=sb_data.get("phone"),
                servicebund_fax=sb_data.get("fax"),
                servicebund_email=sb_data.get("email"),
                servicebund_website=sb_data.get("website"),
                crawled_date=datetime.now(UTC).replace(tzinfo=None),
            )
            db.add(profile)

        await db.commit()
        await db.refresh(profile)
        return profile
    except Exception as e:
        logger.warning(f"Crawling service call for company {company_id} encountered error/fallback: {e}")

    if profile:
        return profile

    return CompanyProfile(
        company_id=company_id,
        description=f"Unternehmensprofil für {company_id}",
        logo_url=None,
        wikipedia_url=None,
        crawled_date=datetime.now(UTC).replace(tzinfo=None),
    )


@router.post("/company/{company_id}/summarize/{summary_type}", response_model=CompanyProfileSchema)
async def summarize_company_data(company_id: str, summary_type: str, db: AsyncSession = Depends(get_db)):
    """Generate an AI summary for financials, hiring, or reputation."""
    from urllib.parse import unquote
    company_id = unquote(company_id)
    from core.ai_client import get_ai_client
    from models.bid import CompanyJobEntry, CompanyMood, CompanyRegisterEntry
    from sqlalchemy import select

    allowed_types = ["financial", "hiring", "buyer_reputation", "mhp_reputation", "news", "executive"]
    if summary_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid summary type")

    # DB stores naive UTC datetimes — compare naive UTC on both sides
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Get profile
    result = await db.execute(select(CompanyProfile).where(CompanyProfile.company_id == company_id))
    profile = result.scalars().first()

    if not profile:
        profile = CompanyProfile(company_id=company_id, crawled_date=datetime.utcnow())
        db.add(profile)

    # Check cache (normalize executive to news for storage field if needed)
    effective_summary_type = "news" if summary_type == "executive" else summary_type
    summary_field = f"{effective_summary_type}_summary"
    date_field = f"{effective_summary_type}_summary_date"

    existing_summary = getattr(profile, summary_field, None)
    existing_date = getattr(profile, date_field, None)

    if existing_summary and existing_date and existing_date > thirty_days_ago:
        logger.info(f"Returning cached {summary_type} summary for {company_id}")
        return profile

    # Gather raw data based on type
    raw_data = {"company_name": company_id}
    prompt_id = ""

    if summary_type in ("financial",):
        res = await db.execute(select(CompanyRegisterEntry).where(CompanyRegisterEntry.company_id == company_id))
        docs = res.scalars().all()
        raw_data["financial_data"] = [
            {"title": d.title, "content": d.content, "date": str(d.published_date)} for d in docs
        ]
        prompt_id = "bidding_financial_summary"
    elif summary_type in ("hiring",):
        res = await db.execute(select(CompanyJobEntry).where(CompanyJobEntry.company_id == company_id))
        jobs = res.scalars().all()
        raw_data["jobs_data"] = [{"title": j.title, "content": j.content} for j in jobs]
        prompt_id = "bidding_hiring_summary"
    elif summary_type in ("buyer_reputation",):
        res = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
        moods = res.scalars().all()
        raw_data["mood_data"] = [{"title": m.title, "content": m.content, "rating": m.rating} for m in moods]
        prompt_id = "bidding_buyer_reputation"
    elif summary_type in ("news", "executive"):
        from models.bid import CompanyNewsEntry

        res = await db.execute(select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id))
        news = res.scalars().all()
        raw_data["news_data"] = [{"title": n.title, "content": n.content, "date": n.published_date} for n in news]
        prompt_id = "bidding_news_summary"
    elif summary_type == "mhp_reputation":
        prompt_id = "bidding_mhp_reputation"

    # Call AI
    ai = get_ai_client()
    try:
        ai_res = await ai.extract_company_summary(prompt_id, raw_data)
        summary_text = ai_res.get("summary", "No summary generated.")
    except Exception as e:
        logger.error(f"AI generation failed for {summary_type}: {e}")
        raise HTTPException(status_code=502, detail="Failed to generate AI summary")

    setattr(profile, summary_field, summary_text)
    setattr(profile, date_field, datetime.now(UTC).replace(tzinfo=None))

    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/company/{company_id}/historic-tenders", response_model=CompanyProfileSchema)
async def evaluate_historic_tenders(company_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch historic tenders from crawler, cache them, and evaluate incumbent advantage/competitor density."""
    from urllib.parse import unquote
    company_id = unquote(company_id)
    from core.ai_client import get_ai_client
    from models.bid import CompanyHistoricTender

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Get profile
    result = await db.execute(select(CompanyProfile).where(CompanyProfile.company_id == company_id))
    profile = result.scalars().first()

    if not profile:
        profile = CompanyProfile(company_id=company_id, crawled_date=datetime.utcnow())
        db.add(profile)

    # Check cache for historic tenders
    res = await db.execute(select(CompanyHistoricTender).where(CompanyHistoricTender.company_id == company_id))
    tenders = res.scalars().all()

    # If no tenders or they are too old, fetch from crawler
    if not tenders or any(t.crawled_date and t.crawled_date.replace(tzinfo=None) < thirty_days_ago for t in tenders):
        logger.info(f"Triggering TED scraper for historic tenders for {company_id}")
        crawling_url = os.getenv("CRAWLING_URL", "http://tender-crawling:8001")

        try:
            import uuid

            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{crawling_url}/api/v1/scrape/ted/historic?company_id={company_id}", timeout=60
                )
            if resp.status_code == 200:
                # Clear old cache
                if tenders:
                    from sqlalchemy import delete

                    await db.execute(
                        delete(CompanyHistoricTender).where(CompanyHistoricTender.company_id == company_id)
                    )

                fetched = resp.json()
                tenders = []
                for t in fetched:
                    # Save to DB
                    new_tender = CompanyHistoricTender(
                        company_id=company_id,
                        hash=str(uuid.uuid4()),
                        title=t.get("title"),
                        link=t.get("url"),
                        content=t.get("description"),
                        published_date=t.get("published_at"),
                        crawled_date=datetime.now(UTC).replace(tzinfo=None),
                    )
                    db.add(new_tender)
                    tenders.append(new_tender)
                await db.commit()
            else:
                logger.warning(f"Failed to fetch historic tenders: {resp.text}")
        except Exception as e:
            logger.error(f"Error fetching historic tenders: {e}")

    # Serialize tenders for AI evaluation
    tender_dicts = [{"title": t.title, "description": t.content, "date": t.published_date} for t in tenders]

    # Call AI
    ai = get_ai_client()
    try:
        metadata = await ai.evaluate_historic_competition(tender_dicts, company_id)
        profile.incumbent_advantage_summary = metadata.get("incumbent_advantage_summary")
        profile.competitor_density_summary = metadata.get("competitor_density_summary")
        await db.commit()
        await db.refresh(profile)
    except Exception as e:
        logger.error(f"AI generation failed for historic tenders: {e}")

    return profile
