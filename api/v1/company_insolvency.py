import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import httpx
from core.database import get_db
from fastapi import APIRouter, Depends
from models.bid import CompanyInsolvency
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["company-insolvency"])

CRAWLING_MS_URL = os.getenv("CRAWLING_MS_URL", "http://tender-tentacle-tender-crawling-1:8001")

class CompanyInsolvencySchema(BaseModel):
    id: str
    company_id: str
    has_notices: bool
    notices: list[dict[str, Any]] | None = None
    crawled_date: datetime

    class Config:
        from_attributes = True

@router.get("/company/{company_id:path}/insolvency", response_model=Optional[CompanyInsolvencySchema])
async def get_company_insolvency(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company insolvency status.
    If no recent data is found (last 30 days), it will trigger the scraper.
    """
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    stmt = select(CompanyInsolvency).where(
        CompanyInsolvency.company_id == company_id,
        CompanyInsolvency.crawled_date >= thirty_days_ago
    )
    result = await db.execute(stmt)
    existing_insolvency = result.scalar_one_or_none()

    if existing_insolvency:
        logger.info(f"Returning cached Insolvency data for company {company_id}")
        return existing_insolvency

    logger.info(f"No recent Insolvency data for {company_id}. Triggering scraper in crawling ms...")

    # Clean company ID similar to jobs
    cleaned_company_id = re.sub(r'\(.*?\)', '', company_id)
    cleaned_company_id = re.sub(r'\b(GmbH & Co\.? KG|GmbH|AG|UG|haftungsbeschränkt|e\.?V\.?|KG|OHG)\b', '', cleaned_company_id, flags=re.IGNORECASE)
    cleaned_company_id = cleaned_company_id.strip()

    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {"query": cleaned_company_id}

        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/insolvency",
                json=payload
            )
            crawling_response.raise_for_status()
            scraped_data = crawling_response.json()

            # Save to DB
            stmt_old = select(CompanyInsolvency).where(CompanyInsolvency.company_id == company_id)
            res_old = await db.execute(stmt_old)
            old_record = res_old.scalar_one_or_none()

            if old_record:
                old_record.has_notices = scraped_data.get("has_notices", False)
                old_record.notices = scraped_data.get("notices", [])
                old_record.crawled_date = datetime.now(UTC)
                new_insolvency = old_record
            else:
                new_insolvency = CompanyInsolvency(
                    company_id=company_id,
                    has_notices=scraped_data.get("has_notices", False),
                    notices=scraped_data.get("notices", []),
                    crawled_date=datetime.now(UTC)
                )
                db.add(new_insolvency)

            await db.commit()
            await db.refresh(new_insolvency)
            return new_insolvency

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch insolvency data from crawling ms: {e}. Returning cached data if available.")
            result = await db.execute(select(CompanyInsolvency).where(CompanyInsolvency.company_id == company_id))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Unexpected error when calling crawling ms: {e}. Returning cached data if available.")
            result = await db.execute(select(CompanyInsolvency).where(CompanyInsolvency.company_id == company_id))
            return result.scalar_one_or_none()
