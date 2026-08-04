import logging
from datetime import UTC, datetime, timedelta

import httpx
from core.config import CRAWLING_MS_URL, DISTRIBUTION_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.bid import CompanyMood
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-mood"])
logger = logging.getLogger("company-mood")

class CompanyMoodSchema(BaseModel):
    id: str
    company_id: str
    comment_hash: str
    title: str | None
    content: str | None
    rating: float | None
    published_date: str | None
    crawled_date: datetime
    overall_score: float | None = None
    score_career: float | None = None
    score_culture: float | None = None
    score_environment: float | None = None
    score_diversity: float | None = None
    review_count: int | None = None
    summary_text: str | None = None
    industry_score: float | None = None
    discovered_url: str | None = None
    culture_compass: str | None = None
    culture_dimensions: dict | None = None
    source_platform: str | None = "kununu"

    class Config:
        from_attributes = True

class ScrapeMoodRequest(BaseModel):
    url: str

@router.get("/company/{company_id:path}/mood", response_model=list[CompanyMoodSchema])
async def get_company_mood(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company mood for a specific company.
    If no recent data is found (less than 30 days old), it will trigger the scraper and override stale records.
    """
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    stmt = select(CompanyMood).where(
        CompanyMood.company_id == company_id,
        CompanyMood.crawled_date >= thirty_days_ago
    )
    result = await db.execute(stmt)
    existing_moods = result.scalars().all()

    if existing_moods:
        logger.info(f"Returning cached Kununu data for company {company_id}")
        return existing_moods

    logger.info(f"No recent Kununu data for {company_id}. Triggering scraper in crawling ms...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Check distributing for a direct Kununu URL
        kununu_url = None
        try:
            dist_res = await client.get(f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links")
            if dist_res.status_code == 200:
                kununu_url = dist_res.json().get("url")
        except Exception as e:
            logger.warning(f"Failed to lookup Kununu URL from distributing ms: {e}")

        payload = {"query": company_id}
        if kununu_url:
            payload["url"] = kununu_url

        scraped_comments = []
        metadata = {}
        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/kununu",
                json=payload
            )
            crawling_response.raise_for_status()
            scraped_payload = crawling_response.json()

            if isinstance(scraped_payload, dict):
                scraped_comments = scraped_payload.get("comments", [])
                metadata = scraped_payload.get("metadata", {})
            elif isinstance(scraped_payload, list):
                scraped_comments = scraped_payload
                metadata = {}

            discovered_url = metadata.get("discovered_url")
            if not discovered_url and scraped_comments and "source_url" in scraped_comments[0]:
                discovered_url = scraped_comments[0].get("source_url")

            if not kununu_url and discovered_url:
                try:
                    await client.post(
                        f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links",
                        json={"url": discovered_url}
                    )
                    logger.info(f"Persisted dynamically discovered Kununu URL: {discovered_url}")
                except Exception as e:
                    logger.error(f"Failed to persist discovered URL: {e}")

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch kununu data from crawling ms: {e}. Returning cached data if available.")
            result = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
            return result.scalars().all()
        except Exception as e:
            logger.warning(f"Unexpected error when calling crawling ms: {e}. Returning cached data if available.")
            result = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
            return result.scalars().all()

        # 2. Scrape Glassdoor Ratings
        try:
            gd_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/glassdoor",
                json={"query": company_id},
                timeout=20.0
            )
            if gd_response.status_code == 200:
                gd_data = gd_response.json()
                gd_comments = gd_data.get("comments", [])
                gd_meta = gd_data.get("metadata", {})
                for c in gd_comments:
                    c["source_platform"] = "glassdoor"
                    c["_meta"] = gd_meta
                    scraped_comments.append(c)
        except Exception as e:
            logger.warning(f"Failed to fetch Glassdoor data: {e}")

    new_moods = []
    for comment in scraped_comments:
        comment_hash = comment.get("comment_hash")
        if not comment_hash:
            continue
        item_meta = comment.get("_meta", metadata)
        source_plat = comment.get("source_platform") or item_meta.get("source_platform") or "kununu"

        stmt_check = select(CompanyMood).where(CompanyMood.comment_hash == comment_hash)
        res = await db.execute(stmt_check)
        existing = res.scalars().first()
        if existing:
            if item_meta.get("overall_score"):
                existing.overall_score = item_meta.get("overall_score")
                existing.score_career = item_meta.get("score_career")
                existing.score_culture = item_meta.get("score_culture")
                existing.score_environment = item_meta.get("score_environment")
                existing.score_diversity = item_meta.get("score_diversity")
                existing.review_count = item_meta.get("review_count")
                existing.summary_text = item_meta.get("summary_text")
                existing.industry_score = item_meta.get("industry_score")
                existing.discovered_url = item_meta.get("discovered_url") or comment.get("source_url") or kununu_url
                existing.culture_compass = item_meta.get("culture_compass")
                existing.culture_dimensions = item_meta.get("culture_dimensions")
                existing.source_platform = source_plat
                existing.crawled_date = datetime.now(UTC)
            continue

        mood = CompanyMood(
            company_id=company_id,
            comment_hash=comment_hash,
            title=comment.get("title"),
            content=comment.get("content"),
            rating=comment.get("rating"),
            published_date=comment.get("published_date"),
            overall_score=item_meta.get("overall_score"),
            score_career=item_meta.get("score_career"),
            score_culture=item_meta.get("score_culture"),
            score_environment=item_meta.get("score_environment"),
            score_diversity=item_meta.get("score_diversity"),
            review_count=item_meta.get("review_count"),
            summary_text=item_meta.get("summary_text"),
            industry_score=item_meta.get("industry_score"),
            discovered_url=item_meta.get("discovered_url") or comment.get("source_url") or kununu_url,
            culture_compass=item_meta.get("culture_compass"),
            culture_dimensions=item_meta.get("culture_dimensions"),
            source_platform=source_plat,
            crawled_date=datetime.now(UTC)
        )
        db.add(mood)
        new_moods.append(mood)

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Error saving Kununu comments: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving mood")

    result = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
    return result.scalars().all()

@router.post("/company/{company_id:path}/mood/scrape", response_model=list[CompanyMoodSchema])
async def manual_scrape_company_mood(company_id: str, request: ScrapeMoodRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually override and scrape Kununu using a specific URL.
    Saves the URL to distributing MS and scrapes data.
    """
    logger.info(f"Manual Kununu scrape requested for {company_id} with URL {request.url}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            await client.post(
                f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links",
                json={"url": request.url}
            )
            logger.info("Successfully saved Kununu URL to distributing MS.")
        except Exception as e:
            logger.error(f"Could not save Kununu URL to distributing MS: {e}")

        scraped_comments = []
        metadata = {}
        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/kununu",
                json={"query": company_id, "url": request.url}
            )
            crawling_response.raise_for_status()
            scraped_payload = crawling_response.json()

            if isinstance(scraped_payload, dict):
                scraped_comments = scraped_payload.get("comments", [])
                metadata = scraped_payload.get("metadata", {})
            elif isinstance(scraped_payload, list):
                scraped_comments = scraped_payload
                metadata = {}
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            raise HTTPException(status_code=500, detail=f"Scraping failed: {e}")

    new_moods = []
    for comment in scraped_comments:
        comment_hash = comment.get("comment_hash")
        if not comment_hash:
            continue
        stmt_check = select(CompanyMood).where(CompanyMood.comment_hash == comment_hash)
        res = await db.execute(stmt_check)
        existing = res.scalars().first()
        if existing:
            if metadata.get("overall_score"):
                existing.overall_score = metadata.get("overall_score")
                existing.score_career = metadata.get("score_career")
                existing.score_culture = metadata.get("score_culture")
                existing.score_environment = metadata.get("score_environment")
                existing.score_diversity = metadata.get("score_diversity")
                existing.review_count = metadata.get("review_count")
                existing.summary_text = metadata.get("summary_text")
                existing.industry_score = metadata.get("industry_score")
                existing.discovered_url = metadata.get("discovered_url") or request.url
                existing.crawled_date = datetime.now(UTC)
            continue

        mood = CompanyMood(
            company_id=company_id,
            comment_hash=comment_hash,
            title=comment.get("title"),
            content=comment.get("content"),
            rating=comment.get("rating"),
            published_date=comment.get("published_date"),
            overall_score=metadata.get("overall_score"),
            score_career=metadata.get("score_career"),
            score_culture=metadata.get("score_culture"),
            score_environment=metadata.get("score_environment"),
            score_diversity=metadata.get("score_diversity"),
            review_count=metadata.get("review_count"),
            summary_text=metadata.get("summary_text"),
            industry_score=metadata.get("industry_score"),
            discovered_url=metadata.get("discovered_url") or request.url,
            crawled_date=datetime.now(UTC)
        )
        db.add(mood)
        new_moods.append(mood)

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Error saving Kununu comments: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving mood")

    result = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
    return result.scalars().all()
