import hashlib
import logging
import re
from datetime import UTC, datetime

import httpx
from core.config import AI_URL, CRAWLING_MS_URL, DISTRIBUTION_MS_URL
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
    scarf_status: float | None = None
    scarf_certainty: float | None = None
    scarf_autonomy: float | None = None
    scarf_relatedness: float | None = None
    scarf_fairness: float | None = None
    scarf_primary_threat: str | None = None
    scarf_primary_reward: str | None = None
    scarf_rationale: str | None = None
    scarf_enriched_at: datetime | None = None

    class Config:
        from_attributes = True


class ScrapeMoodRequest(BaseModel):
    url: str
    force: bool = False


@router.get("/company/{company_id}/salaries", response_model=list[CompanySalarySchema])
async def get_company_salaries(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company salary job titles for a specific company ordered by number of people using that title (sample_count DESC).
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
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


@router.get("/company/{company_id}/kununu_jobs", response_model=list[CompanyJobSchema])
async def get_company_kununu_jobs(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get open Kununu job postings for a specific company.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
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


@router.get("/company/{company_id}/mood", response_model=list[CompanyMoodSchema])
async def get_company_mood(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get cached employee mood reviews for a specific company.
    Returns cached DB records without triggering automatic live scraping or guessing URLs.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = select(CompanyMood).where(
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    for r in records:
        if not r.source_platform:
            url_lower = (r.discovered_url or "").lower()
            if "glassdoor" in url_lower:
                r.source_platform = "glassdoor"
            else:
                r.source_platform = "kununu"
    return records


import urllib.parse


def clean_kununu_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    u_str = url.strip()
    if "kununu.com" not in u_str.lower():
        return None
    try:
        decoded = urllib.parse.unquote(u_str)
        match = re.search(r"kununu\.com/(?:([a-z]{2})/)?([^/?#]+)", decoded, flags=re.IGNORECASE)
        if not match:
            return None

        country_code = (match.group(1) or "de").lower()
        if country_code not in ("de", "ch", "at"):
            country_code = "de"

        raw_slug = match.group(2).strip()
        replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
        for orig, rep in replacements.items():
            raw_slug = raw_slug.replace(orig, rep)
        raw_slug = re.sub(r"\([^)]*\)", "", raw_slug)
        slug = re.sub(r"[^a-z0-9]+", "-", raw_slug.lower()).strip("-")
        if not slug or slug in ("search", "suche", "pvs-holding", "unternehmen", "job", "jobs"):
            return None
        return f"https://www.kununu.com/{country_code}/{slug}"
    except Exception:
        return None


def clean_glassdoor_url(url: str | None) -> str | None:
    """Sanitizes raw or URL-encoded Glassdoor links into valid company profile URLs."""
    if not url or not isinstance(url, str):
        return None
    u_str = url.strip()
    if "glassdoor.com" not in u_str.lower() and "glassdoor.de" not in u_str.lower():
        return None

    try:
        decoded = urllib.parse.unquote(u_str)
        match = re.search(r"(glassdoor\.(?:com|de)/[^\s\?\#]+)", decoded, flags=re.IGNORECASE)
        if not match:
            return None
        return f"https://www.{match.group(1)}"
    except Exception:
        return None



@router.post("/company/{company_id}/mood/scrape", response_model=list[CompanyMoodSchema])
async def manual_scrape_company_mood(company_id: str, request: ScrapeMoodRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually scrape Kununu or Glassdoor using a specific, validated URL.
    Requires an explicit kununu.com or glassdoor.com/de URL. Never scrapes without a URL.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)

    raw_url = (request.url or "").strip().lower()
    if not raw_url or not ("kununu.com" in raw_url or "glassdoor" in raw_url):
        raise HTTPException(status_code=400, detail="A valid Kununu or Glassdoor URL is required.")
    is_glassdoor = "glassdoor" in raw_url or "glassdoor" in company_id.lower()
    cleaned_url = clean_glassdoor_url(request.url) if is_glassdoor else clean_kununu_url(request.url)

    if not cleaned_url:
        clean_slug = re.sub(r"[^a-zA-Z0-9]", "-", company_id).strip("-").lower()
        if is_glassdoor:
            target_url = f"https://www.glassdoor.de/Bewertungen/{clean_slug}-Bewertungen"
        else:
            target_url = f"https://www.kununu.com/de/{clean_slug}"
    else:
        target_url = cleaned_url.strip()

    platform_name = "glassdoor" if is_glassdoor else "kununu"

    logger.info(f"Manual {platform_name} scrape requested for {company_id} with URL {target_url}")

    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = select(CompanyMood).where(
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    result = await db.execute(stmt)
    records = [r for r in result.scalars().all() if (r.source_platform or "kununu") == platform_name]
    if records and not request.force:
        latest_crawl = max((r.crawled_date for r in records if r.crawled_date), default=None)
        if latest_crawl:
            if latest_crawl.tzinfo is None:
                latest_crawl = latest_crawl.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - latest_crawl).days
            if age_days < 30:
                logger.info(
                    f"Skipping {platform_name} scrape for '{company_id}': cached data was scraped {age_days}d ago (< 30 days). Saving crawler resources."
                )
                return records

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            await client.post(
                f"{DISTRIBUTION_MS_URL}/api/v1/taxonomy/target_companies/by_name/{company_id}/links",
                json={"url": target_url},
            )
            logger.info(f"Successfully saved {platform_name} URL to distributing MS.")
        except Exception as e:
            logger.error(f"Could not save {platform_name} URL to distributing MS: {e}")

        payload = {}
        scraped_comments = []
        metadata = {}
        is_fallback = False
        is_successful_crawl = False

        try:
            scrape_path = "glassdoor" if is_glassdoor else "kununu"
            existing_count = len(records)
            crawling_response = await client.post(
                f"{CRAWLING_MS_URL}/api/v1/scrape/{scrape_path}",
                json={"query": company_id, "url": target_url, "existing_count": existing_count}
            )
            if crawling_response.status_code in (402, 429):
                err_detail = "Firecrawl API credit limit or quota reached."
                try:
                    err_detail = crawling_response.json().get("detail", err_detail)
                except Exception as e:
                    logger.debug(f"Could not parse detail from crawling response: {e}")
                logger.error(f"Firecrawl quota limit for {company_id}: {err_detail}")
                raise HTTPException(status_code=402, detail=err_detail)

            if crawling_response.status_code != 200:
                err_detail = f"{platform_name.capitalize()} crawl failed with HTTP {crawling_response.status_code}"
                try:
                    err_detail = crawling_response.json().get("detail", err_detail)
                except Exception as exc:
                    logger.debug(f"Could not parse JSON detail from crawling response: {exc}")
                logger.error(f"{platform_name.capitalize()} crawl error for {company_id}: {err_detail}")
                if records:
                    logger.info(f"Returning {len(records)} cached records after crawl failure.")
                    return records
                raise HTTPException(status_code=502, detail=err_detail)

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
            if records:
                return records

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
                existing.source_platform = platform_name
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
            source_platform=platform_name,
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
                existing_j.url = j_url
                existing_j.source_url = j_url
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
                        source_url=j_url,
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

    # Automatically run on-the-fly SCARF AI enrichment for newly scraped comments
    try:
        await enrich_company_mood_scarf(company_id=company_id, db=db)
        logger.info(f"On-the-fly SCARF enrichment completed for '{company_id}'.")
    except Exception as exc:
        logger.warning(f"On-the-fly SCARF enrichment failed for '{company_id}': {exc}")

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


@router.post("/company/{company_id}/mood/ingest", response_model=list[CompanyMoodSchema])
async def ingest_browser_crawl(
    company_id: str,
    payload: IngestPayload,
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import unquote
    company_id = unquote(company_id)
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

    target_platform = "kununu"
    disc_url = (metadata.get("discovered_url") or "").lower()
    src_platform = (metadata.get("source_platform") or "").lower()
    if "glassdoor" in disc_url or "glassdoor" in src_platform:
        target_platform = "glassdoor"

    for comment in payload.comments:
        c_url = (comment.source_url or "").lower()
        if "glassdoor" in c_url:
            comment_platform = "glassdoor"
        else:
            comment_platform = target_platform

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
            existing.source_platform = comment_platform
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
            source_platform=comment_platform,
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

    # Automatically run on-the-fly SCARF AI enrichment for ingested comments
    try:
        await enrich_company_mood_scarf(company_id=company_id, db=db)
        logger.info(f"On-the-fly SCARF enrichment completed after ingest for '{company_id}'.")
    except Exception as exc:
        logger.warning(f"On-the-fly SCARF enrichment failed after ingest for '{company_id}': {exc}")

    result = await db.execute(
        select(CompanyMood).where(func.lower(CompanyMood.company_id) == company_id.lower())
    )
    return result.scalars().all()


@router.delete("/company/{company_id}/mood")
async def delete_company_mood(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Purge cached Kununu employee mood, salary entries, and job postings for a company.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
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


@router.post("/company/{company_id}/mood/enrich-scarf", response_model=dict)
async def enrich_company_mood_scarf(
    company_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers AI SCARF model enrichment for all un-analyzed Kununu comments of a company.
    Calculates 5 SCARF dimension scores (0-100) per comment and persists them in DB.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()

    stmt = select(CompanyMood).where(
        (func.lower(CompanyMood.company_id) == company_id.lower())
        | (func.lower(CompanyMood.company_id).contains(clean_id))
        | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
    )
    res = await db.execute(stmt)
    moods = res.scalars().all()

    if not moods:
        return {
            "status": "no_comments",
            "company_id": company_id,
            "total_comments": 0,
            "analyzed_count": 0,
            "waiting_count": 0,
            "moods": []
        }

    # Call AI MS /api/v1/enrich/scarf or local extractor fallback
    comment_inputs = []
    for m in moods:
        c_id = m.comment_hash or str(m.id)
        comment_inputs.append({
            "id": c_id,
            "title": m.title or "",
            "content": m.content or m.summary_text or "",
            "rating": m.rating or m.overall_score or 3.0
        })

    # Fetch configurable versioned prompt template from bidding prompt_config
    prompt_template = None
    try:
        from services.prompt_config import current_template
        prompt_template = await current_template(db, "bidding_scarf_enrichment")
    except Exception as exc:
        logger.debug(f"Could not load bidding_scarf_enrichment prompt template: {exc}")

    enriched_map = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            ai_res = await client.post(
                f"{AI_URL}/api/v1/enrich/scarf",
                json={
                    "comments": comment_inputs,
                    "prompt_template": prompt_template
                }
            )
            if ai_res.status_code == 200:
                data = ai_res.json()
                for item in data.get("enriched_comments", []):
                    enriched_map[item["id"]] = item
        except Exception as err:
            logger.warning(f"AI MS SCARF enrichment failed, falling back to local extractor: {err}")

    # Fallback to local extract_scarf_dimensions if AI MS call wasn't available
    try:
        from artificial_intelligence_connector.core.scarf_extractor import extract_scarf_dimensions  # type: ignore
    except ModuleNotFoundError:
        extract_scarf_dimensions = None

    updated_count = 0
    now_utc = datetime.now(UTC)

    for m in moods:
        c_id = m.comment_hash or str(m.id)
        res_data = enriched_map.get(c_id)

        if res_data and "scarf_scores" in res_data:
            s_scores = res_data["scarf_scores"]
            m.scarf_status = float(s_scores["status"]) if s_scores.get("status") is not None else None
            m.scarf_certainty = float(s_scores["certainty"]) if s_scores.get("certainty") is not None else None
            m.scarf_autonomy = float(s_scores["autonomy"]) if s_scores.get("autonomy") is not None else None
            m.scarf_relatedness = float(s_scores["relatedness"]) if s_scores.get("relatedness") is not None else None
            m.scarf_fairness = float(s_scores["fairness"]) if s_scores.get("fairness") is not None else None
            m.scarf_primary_threat = res_data.get("primary_threat")
            m.scarf_primary_reward = res_data.get("primary_reward")
            m.scarf_rationale = res_data.get("rationale")
            m.scarf_enriched_at = now_utc
            updated_count += 1
        elif extract_scarf_dimensions:
            local_res = extract_scarf_dimensions(
                title=m.title,
                content=m.content or m.summary_text,
                rating=m.rating or m.overall_score or 3.0
            )
            if local_res and isinstance(local_res, dict):
                m.scarf_status = float(local_res["status"]) if local_res.get("status") is not None else None
                m.scarf_certainty = float(local_res["certainty"]) if local_res.get("certainty") is not None else None
                m.scarf_autonomy = float(local_res["autonomy"]) if local_res.get("autonomy") is not None else None
                m.scarf_relatedness = float(local_res["relatedness"]) if local_res.get("relatedness") is not None else None
                m.scarf_fairness = float(local_res["fairness"]) if local_res.get("fairness") is not None else None
                m.scarf_primary_threat = local_res.get("primary_threat")
                m.scarf_primary_reward = local_res.get("primary_reward")
                m.scarf_rationale = local_res.get("rationale")
                m.scarf_enriched_at = now_utc
                updated_count += 1
        else:
            logger.info(f"No AI SCARF enrichment response available for comment {c_id}. Skipping mock data creation.")

    await db.commit()

    return {
        "status": "success",
        "company_id": company_id,
        "total_comments": len(moods),
        "analyzed_count": len(moods),
        "waiting_count": 0,
        "updated_count": updated_count
    }
