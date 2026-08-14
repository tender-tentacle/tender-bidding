import logging
from datetime import datetime

from core.database import get_db
from fastapi import APIRouter, Depends
from models.bid import CompanyRegisterEntry
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-financials"])
logger = logging.getLogger("company-financials")


class CompanyFinancialsSchema(BaseModel):
    id: str
    company_id: str
    hash: str
    title: str | None
    link: str | None
    content: str | None
    category: str | None
    published_date: str | None
    crawled_date: datetime

    class Config:
        from_attributes = True


@router.get("/company/{company_id}/financials", response_model=list[CompanyFinancialsSchema])
async def get_company_financials(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company financials and register entries for a specific company.
    Currently only returns cached data from the DB since live scraping is blocked.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    stmt = select(CompanyRegisterEntry).where(CompanyRegisterEntry.company_id == company_id)
    result = await db.execute(stmt)
    existing_entries = result.scalars().all()

    logger.info(f"Returning {len(existing_entries)} cached financial records for company {company_id}")
    return existing_entries
