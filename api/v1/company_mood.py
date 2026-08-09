import hashlib
import logging
import re
from datetime import UTC, datetime

import httpx
from core.config import CRAWLING_MS_URL, DISTRIBUTION_MS_URL
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.bid import CompanyJobEntry, CompanyMood, CompanySalaryEntry
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["company-mood"])
logger = logging.getLogger("company-mood")


class CompanySalarySchema(BaseModel):
    id: str
    company_id: str
    hash: str
    job_title: str
    sample_count: int
    avg_salary: float
    currency: str | None = "EUR"
    crawled_date: datetime


class CompanyJobSchema(BaseModel):
    id: str
    company_id: str
    hash: str
    title: str
    location: str | None = "Deutschland"
    employment_type: str | None = "Vollzeit"
    url: str | None = None
    published_date: str | None = None
    salary_range: str | None = None
    crawled_date: datetime


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
    salary_satisfaction_percentage: float | None = None
    salary_satisfaction_text: str | None = None
    salary_satisfaction_review_count: int | None = None
    salary_benefits_score: float | None = None
    salary_benefits_review_count: int | None = None
    source_platform: str | None = "kununu"

    class Config:
        from_attributes = True


class ScrapeMoodRequest(BaseModel):
    url: str
    force: bool = False


@router.get("/company/{company_id:path}/salaries", response_model=list[CompanySalarySchema])
async def get_company_salaries(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company salary job titles for a specific company ordered by number of people using that title (sample_count DESC).
    """
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = (
        select(CompanySalaryEntry)
        .where(
            (func.lower(CompanySalaryEntry.company_id) == company_id.lower())
            | (func.lower(CompanySalaryEntry.company_id).contains(clean_id))
            | (func.lower(CompanySalaryEntry.company_id).contains(short_id) if len(short_id) >= 3 else False)
        )
        .order_by(CompanySalaryEntry.sample_count.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/company/{company_id:path}/kununu_jobs", response_model=list[CompanyJobSchema])
async def get_company_kununu_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get open Kununu job postings for a specific company.
    """
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = (
        select(CompanyJobEntry)
        .where(
            (func.lower(CompanyJobEntry.company_id) == company_id.lower())
            | (func.lower(CompanyJobEntry.company_id).contains(clean_id))
            | (func.lower(CompanyJobEntry.company_id).contains(short_id) if len(short_id) >= 3 else False)
        )
        .order_by(CompanyJobEntry.crawled_date.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/company/{company_id:path}/mood", response_model=list[CompanyMoodSchema])
async def get_company_mood(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get cached employee mood reviews for a specific company.
    If no data is cached, it will trigger an on-the-fly scrape in crawling ms.
    """
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = select(CompanyMood).where(
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    if records:
        latest_crawl = max((r.crawled_date for r in records if r.crawled_date), default=None)
        if latest_crawl:
            if latest_crawl.tzinfo is None:
                latest_crawl = latest_crawl.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - latest_crawl).days
            if age_days < 30:
                logger.info(f"Returning cached Kununu data for '{company_id}' (age: {age_days}d < 30d).")
                return records

    url = f"https://www.kununu.com/de/{clean_id.replace(' ', '-')}"
    dummy_req = ScrapeMoodRequest(url=url)
    return await manual_scrape_company_mood(company_id=company_id, request=dummy_req, db=db)



@router.post("/company/{company_id:path}/mood/scrape", response_model=list[CompanyMoodSchema])
async def manual_scrape_company_mood(company_id: str, request: ScrapeMoodRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually override and scrape Kununu using a specific URL.
    Saves the URL to distributing MS and scrapes data.
    If cached data exists and was scraped within the last 30 days, scraping is skipped to save crawler resources unless force=True.
    """
    logger.info(f"Manual Kununu scrape requested for {company_id} with URL {request.url}")

    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = select(CompanyMood).where(
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    if records and not request.force:
        latest_crawl = max((r.crawled_date for r in records if r.crawled_date), default=None)
        if latest_crawl:
            if latest_crawl.tzinfo is None:
                latest_crawl = latest_crawl.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - latest_crawl).days
            if age_days < 30:
                logger.info(
                    f"Skipping Kununu scrape for '{company_id}': cached data was scraped {age_days}d ago (< 30 days). Saving crawler resources."
                )
                return records


    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            await client.post(
                f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links",
                json={"url": request.url},
            )
            logger.info("Successfully saved Kununu URL to distributing MS.")
        except Exception as e:
            logger.error(f"Could not save Kununu URL to distributing MS: {e}")

        payload = {}
        scraped_comments = []
        metadata = {}
        is_fallback = False
        is_successful_crawl = False

        try:
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/kununu", json={"query": company_id, "url": request.url}
            )
            if crawling_response.status_code in (402, 429):
                err_detail = "Firecrawl API credit limit or quota reached."
                try:
                    err_detail = crawling_response.json().get("detail", err_detail)
                except Exception as e:
                    logger.debug(f"Could not parse detail from crawling response: {e}")
                logger.error(f"Firecrawl quota limit for {company_id}: {err_detail}")
                raise HTTPException(status_code=402, detail=err_detail)

            crawling_response.raise_for_status()
            scraped_payload = crawling_response.json()

            payload = scraped_payload if isinstance(scraped_payload, dict) else {"comments": scraped_payload}
            scraped_comments = payload.get("comments", [])
            metadata = payload.get("metadata", {})
            is_fallback = payload.get("is_fallback", False)
            if scraped_comments or payload.get("jobs") or payload.get("salaries"):
                is_successful_crawl = True
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            logger.error(f"Scraping failed or blocked for {company_id}: {e}\n{traceback.format_exc()}")

    new_moods = []
    for comment in scraped_comments:
        raw_hash = comment.get("comment_hash") or f"{comment.get('title')}_{comment.get('content')}_{comment.get('published_date')}"
        comment_hash = hashlib.sha256(f"{company_id}_{raw_hash}".encode()).hexdigest()

        stmt_check = select(CompanyMood).where(
            CompanyMood.comment_hash == comment_hash,
            CompanyMood.company_id == company_id
        )
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
                existing.salary_satisfaction_percentage = metadata.get("salary_satisfaction_percentage")
                existing.salary_satisfaction_text = metadata.get("salary_satisfaction_text")
                existing.salary_satisfaction_review_count = metadata.get("salary_satisfaction_review_count")
                existing.salary_benefits_score = metadata.get("salary_benefits_score")
                existing.salary_benefits_review_count = metadata.get("salary_benefits_review_count")
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
            salary_satisfaction_percentage=metadata.get("salary_satisfaction_percentage"),
            salary_satisfaction_text=metadata.get("salary_satisfaction_text"),
            salary_satisfaction_review_count=metadata.get("salary_satisfaction_review_count"),
            salary_benefits_score=metadata.get("salary_benefits_score"),
            salary_benefits_review_count=metadata.get("salary_benefits_review_count"),
            crawled_date=datetime.now(UTC),
        )
        db.add(mood)
        new_moods.append(mood)

    scraped_salaries = payload.get("salaries", [])
    if scraped_salaries:
        for sal in scraped_salaries:
            s_title = sal.get("job_title", "").strip()
            if not s_title:
                continue
            s_hash = sal.get("hash") or hashlib.sha256(f"{company_id}_{s_title}".encode()).hexdigest()
            res_sal = await db.execute(
                select(CompanySalaryEntry).where(CompanySalaryEntry.hash == s_hash)
            )
            existing_sal = res_sal.scalars().first()
            if existing_sal:
                existing_sal.company_id = company_id
                existing_sal.avg_salary = float(sal.get("avg_salary", 0.0))
                existing_sal.sample_count = int(sal.get("sample_count", 1))
                existing_sal.crawled_date = datetime.now(UTC)
            else:
                db.add(
                    CompanySalaryEntry(
                        company_id=company_id,
                        hash=s_hash,
                        job_title=s_title,
                        sample_count=int(sal.get("sample_count", 1)),
                        avg_salary=float(sal.get("avg_salary", 0.0)),
                        currency=sal.get("currency", "EUR"),
                        crawled_date=datetime.now(UTC),
                    )
                )

    scraped_jobs = payload.get("jobs", [])
    if scraped_jobs:
        for j in scraped_jobs:
            j_title = j.get("title", "").strip()
            j_url = j.get("url", "").strip()
            if not j_title or not j_url:
                continue
            j_hash = j.get("hash") or hashlib.sha256(f"{company_id}_{j_title}_{j_url}".encode()).hexdigest()
            res_j = await db.execute(
                select(CompanyJobEntry).where(CompanyJobEntry.hash == j_hash)
            )
            existing_j = res_j.scalars().first()
            if existing_j:
                existing_j.company_id = company_id
                existing_j.location = j.get("location", "Deutschland")
                existing_j.employment_type = j.get("employment_type", "Vollzeit")
                existing_j.published_date = j.get("published_at") or j.get("published_date")
                existing_j.salary_range = j.get("salary_range")
                existing_j.crawled_date = datetime.now(UTC)
            else:
                db.add(
                    CompanyJobEntry(
                        company_id=company_id,
                        hash=j_hash,
                        title=j_title,
                        location=j.get("location", "Deutschland"),
                        employment_type=j.get("employment_type", "Vollzeit"),
                        url=j_url,
                        published_date=j.get("published_at") or j.get("published_date"),
                        salary_range=j.get("salary_range"),
                        crawled_date=datetime.now(UTC),
                    )
                )

    try:
        await db.commit()
        logger.info(f"Successfully committed {len(new_moods)} comments, {len(scraped_salaries)} salary entries & {len(scraped_jobs)} jobs for {company_id}.")
    except Exception as e:
        logger.error(f"Error saving Kununu comments for {company_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving mood")

    result = await db.execute(select(CompanyMood).where(func.lower(CompanyMood.company_id) == company_id.lower()))
    all_moods = result.scalars().all()
    logger.error(f"DEBUG_SCRAPE: company_id='{company_id}', new_moods={len(new_moods)}, all_moods={len(all_moods)}")
    return all_moods


# ---------------------------------------------------------------------------
# Browser-Relay Ingest: accepts pre-parsed data fetched by the user's local browser
# ---------------------------------------------------------------------------


class IngestCommentSchema(BaseModel):
    comment_hash: str
    title: str | None = None
    content: str | None = None
    rating: float | None = None
    published_date: str | None = None
    source_url: str | None = None


class IngestSalarySchema(BaseModel):
    hash: str
    job_title: str
    avg_salary: float
    sample_count: int
    currency: str | None = "EUR"


class IngestJobSchema(BaseModel):
    hash: str
    title: str
    location: str | None = "Deutschland"
    employment_type: str | None = "Vollzeit"
    url: str | None = None
    published_at: str | None = None
    salary_range: str | None = None


class IngestMetadataSchema(BaseModel):
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
    salary_satisfaction_percentage: float | None = None
    salary_satisfaction_text: str | None = None
    salary_satisfaction_review_count: int | None = None
    salary_benefits_score: float | None = None
    salary_benefits_review_count: int | None = None


class IngestPayload(BaseModel):
    """
    Pre-parsed Kununu payload sent by the user's local browser relay.
    The browser fetches Kununu from the user's residential IP (bypassing WAF),
    parses locally, then POSTs here to persist.
    """
    metadata: IngestMetadataSchema = IngestMetadataSchema()
    comments: list[IngestCommentSchema] = []
    salaries: list[IngestSalarySchema] = []
    jobs: list[IngestJobSchema] = []
    source: str | None = "browser-relay"  # audit trail


@router.post("/company/{company_id:path}/mood/ingest", response_model=list[CompanyMoodSchema])
async def ingest_browser_crawl(
    company_id: str,
    payload: IngestPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts pre-parsed Kununu data from the browser-relay local proxy.
    The browser fetches Kununu using the user's residential IP (no WAF block),
    parses the HTML locally, and uploads the structured result here.
    """
    logger.info(
        f"Browser-relay ingest for '{company_id}': "
        f"{len(payload.comments)} comments, "
        f"{len(payload.salaries)} salaries, "
        f"{len(payload.jobs)} jobs "
        f"(source={payload.source})"
    )

    metadata = payload.metadata.model_dump()
    new_moods: list[CompanyMood] = []

    for comment in payload.comments:
        raw_hash = comment.comment_hash or f"{comment.title}_{comment.content}_{comment.published_date}"
        comment_hash = hashlib.sha256(f"{company_id}_{raw_hash}".encode()).hexdigest()

        res = await db.execute(
            select(CompanyMood).where(
                CompanyMood.comment_hash == comment_hash,
                CompanyMood.company_id == company_id,
            )
        )
        existing = res.scalars().first()
        if existing:
            # Refresh metadata fields on each ingest
            existing.overall_score = metadata.get("overall_score")
            existing.score_career = metadata.get("score_career")
            existing.score_culture = metadata.get("score_culture")
            existing.score_environment = metadata.get("score_environment")
            existing.score_diversity = metadata.get("score_diversity")
            existing.review_count = metadata.get("review_count")
            existing.summary_text = metadata.get("summary_text")
            existing.industry_score = metadata.get("industry_score")
            existing.discovered_url = metadata.get("discovered_url") or comment.source_url
            existing.culture_compass = metadata.get("culture_compass")
            existing.culture_dimensions = metadata.get("culture_dimensions")
            existing.salary_satisfaction_percentage = metadata.get("salary_satisfaction_percentage")
            existing.salary_satisfaction_text = metadata.get("salary_satisfaction_text")
            existing.salary_satisfaction_review_count = metadata.get("salary_satisfaction_review_count")
            existing.salary_benefits_score = metadata.get("salary_benefits_score")
            existing.salary_benefits_review_count = metadata.get("salary_benefits_review_count")
            existing.source_platform = "kununu"
            existing.crawled_date = datetime.now(UTC)
            continue

        mood = CompanyMood(
            company_id=company_id,
            comment_hash=comment_hash,
            title=comment.title,
            content=comment.content,
            rating=comment.rating,
            published_date=comment.published_date,
            overall_score=metadata.get("overall_score"),
            score_career=metadata.get("score_career"),
            score_culture=metadata.get("score_culture"),
            score_environment=metadata.get("score_environment"),
            score_diversity=metadata.get("score_diversity"),
            review_count=metadata.get("review_count"),
            summary_text=metadata.get("summary_text"),
            industry_score=metadata.get("industry_score"),
            discovered_url=metadata.get("discovered_url") or comment.source_url,
            culture_compass=metadata.get("culture_compass"),
            culture_dimensions=metadata.get("culture_dimensions"),
            salary_satisfaction_percentage=metadata.get("salary_satisfaction_percentage"),
            salary_satisfaction_text=metadata.get("salary_satisfaction_text"),
            salary_satisfaction_review_count=metadata.get("salary_satisfaction_review_count"),
            salary_benefits_score=metadata.get("salary_benefits_score"),
            salary_benefits_review_count=metadata.get("salary_benefits_review_count"),
            source_platform="kununu",
            crawled_date=datetime.now(UTC),
        )
        db.add(mood)
        new_moods.append(mood)

    # Upsert salaries
    for sal in payload.salaries:
        s_title = (sal.job_title or "").strip()
        if not s_title:
            continue
        s_hash = sal.hash or hashlib.sha256(f"{company_id}_{s_title}".encode()).hexdigest()
        res_sal = await db.execute(select(CompanySalaryEntry).where(CompanySalaryEntry.hash == s_hash))
        existing_sal = res_sal.scalars().first()
        if existing_sal:
            existing_sal.company_id = company_id
            existing_sal.avg_salary = float(sal.avg_salary)
            existing_sal.sample_count = int(sal.sample_count)
            existing_sal.crawled_date = datetime.now(UTC)
        else:
            db.add(
                CompanySalaryEntry(
                    company_id=company_id,
                    hash=s_hash,
                    job_title=s_title,
                    sample_count=int(sal.sample_count),
                    avg_salary=float(sal.avg_salary),
                    currency=sal.currency or "EUR",
                    crawled_date=datetime.now(UTC),
                )
            )

    # Upsert jobs
    for j in payload.jobs:
        j_title = (j.title or "").strip()
        j_url = (j.url or "").strip()
        if not j_title or not j_url:
            continue
        j_hash = j.hash or hashlib.sha256(f"{company_id}_{j_title}_{j_url}".encode()).hexdigest()
        res_j = await db.execute(select(CompanyJobEntry).where(CompanyJobEntry.hash == j_hash))
        existing_j = res_j.scalars().first()
        if existing_j:
            existing_j.company_id = company_id
            existing_j.location = j.location or "Deutschland"
            existing_j.employment_type = j.employment_type or "Vollzeit"
            existing_j.published_date = j.published_at
            existing_j.salary_range = j.salary_range
            existing_j.crawled_date = datetime.now(UTC)
        else:
            db.add(
                CompanyJobEntry(
                    company_id=company_id,
                    hash=j_hash,
                    title=j_title,
                    location=j.location or "Deutschland",
                    employment_type=j.employment_type or "Vollzeit",
                    url=j_url,
                    published_date=j.published_at,
                    salary_range=j.salary_range,
                    crawled_date=datetime.now(UTC),
                )
            )

    try:
        await db.commit()
        logger.info(
            f"Browser-relay ingest committed: {len(new_moods)} new moods, "
            f"{len(payload.salaries)} salaries, {len(payload.jobs)} jobs for '{company_id}'."
        )
    except Exception as e:
        logger.error(f"Error in browser-relay ingest for '{company_id}': {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while ingesting browser relay data")

    result = await db.execute(
        select(CompanyMood).where(func.lower(CompanyMood.company_id) == company_id.lower())
    )
    return result.scalars().all()


@router.delete("/company/{company_id:path}/mood")
async def delete_company_mood(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Purge cached Kununu employee mood, salary entries, and job postings for a company.
    """
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    cond_mood = (
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    cond_salary = (
        (func.lower(CompanySalaryEntry.company_id) == company_id.lower())
        | (func.lower(CompanySalaryEntry.company_id).contains(clean_id))
        | (func.lower(CompanySalaryEntry.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    cond_job = (
        (func.lower(CompanyJobEntry.company_id) == company_id.lower())
        | (func.lower(CompanyJobEntry.company_id).contains(clean_id))
        | (func.lower(CompanyJobEntry.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )

    res_mood = await db.execute(delete(CompanyMood).where(cond_mood))
    res_salary = await db.execute(delete(CompanySalaryEntry).where(cond_salary))
    res_job = await db.execute(delete(CompanyJobEntry).where(cond_job))
    await db.commit()

    return {
        "status": "cleared",
        "company_id": company_id,
        "deleted_moods": res_mood.rowcount,
        "deleted_salaries": res_salary.rowcount,
        "deleted_jobs": res_job.rowcount,
    }
