import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from core.database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from models.bid import CompanyNewsEntry
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


class CompanyNewsEntrySchema(BaseModel):
    id: str | None = None
    company_id: str | None = None
    hash: str | None = None
    title: str | None = None
    link: str | None = None
    content: str | None = None
    summary: str | None = None
    category: str | None = None
    source_type: str | None = "press"
    published_date: str | None = None
    sentiment_score: int | None = None
    sentiment_label: str | None = None
    sentiment_rationale: str | None = None
    key_topics: list[str] | dict | None = None

    class Config:
        from_attributes = True


async def run_deep_research_company_news(company_name: str, newsroom_urls: list[str] | None = None) -> dict:
    """Queries AI Connector using model_tier='fast' or 'deep-research' for dual-section press news & blog synthesis."""
    from core.config import AI_URL
    base_ai_url = (AI_URL or os.getenv("AI_URL", "http://localhost:8004")).rstrip("/")
    candidate_ai_urls = [
        f"{base_ai_url}/api/inference",
        f"{base_ai_url}/ms/ai/api/inference",
        "http://localhost:8004/api/inference",
        "http://127.0.0.1:8004/api/inference",
        "http://ai-app:8000/api/inference",
        "http://ai-app-test:8000/api/inference",
    ]
    seen_ai = set()
    unique_ai_urls = [u for u in candidate_ai_urls if not (u in seen_ai or seen_ai.add(u))]

    prompt_payload = {
        "prompt_id": "company_deep_research_news",
        "input_text": (
            f"Execute deep research for news and official blog articles regarding company: '{company_name}'. "
            f"Official newsroom/blog URLs: {newsroom_urls or []}. "
            "CRITICAL INSTRUCTIONS:\n"
            "1. Time Window: Extract news, press releases, and blog posts published within the LAST 2 YEARS (730 days).\n"
            "2. Quantity Target: Extract AT LEAST 20 items (and up to 200 max) for 'press_news' (external media & press coverage) "
            "and AT LEAST 20 items (and up to 200 max) for 'company_blog' (official corporate newsroom and blog articles).\n"
            "3. Summary Requirement: 'summary' MUST contain the first 200 words of the article text or a detailed executive summary of the article content. NEVER output a URL, domain name, or empty string in 'summary'.\n"
            "4. Formatting: Extract EACH individual article with its distinct title, link, 200-word summary, publication date (YYYY-MM-DD), sentiment_score (0-100), sentiment_label, sentiment_rationale, and key_topics."
        ),
        "model_tier": "deep-research",
        "enable_web_tools": True,
        "output_structure": {
            "press_news": [
                {
                    "title": "Headline",
                    "link": "https://...",
                    "summary": "First 200 words of the news article content",
                    "published_date": "YYYY-MM-DD",
                    "sentiment_score": 75,
                    "sentiment_label": "Positive",
                    "sentiment_rationale": "Explanation",
                    "key_topics": ["Topic"]
                }
            ],
            "company_blog": [
                {
                    "title": "Blog Headline",
                    "link": "https://...",
                    "summary": "2-sentence summary of blog post",
                    "published_date": "YYYY-MM-DD",
                    "sentiment_score": 80,
                    "sentiment_label": "Positive",
                    "sentiment_rationale": "Explanation",
                    "key_topics": ["Topic"]
                }
            ]
        }
    }
    for ep_url in unique_ai_urls:
        try:
            logger.info(f"Attempting AI Connector company news research for '{company_name}' via {ep_url}...")
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(ep_url, json=prompt_payload)
                if res.status_code == 200:
                    body = res.json()
                    data_field = body.get("data", {})
                    if isinstance(data_field, dict) and ("press_news" in data_field or "company_blog" in data_field):
                        return data_field
                    raw_out = data_field.get("raw_output") if isinstance(data_field, dict) else body.get("raw_output")
                    if isinstance(raw_out, str):
                        import json
                        cleaned = raw_out.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
                        elif cleaned.startswith("```"):
                            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
                        try:
                            parsed = json.loads(cleaned)
                            if isinstance(parsed, dict) and ("press_news" in parsed or "company_blog" in parsed):
                                return parsed
                        except json.JSONDecodeError as ex:
                            logger.error(f"❌ JSON parsing failure for '{company_name}': {ex}")
                    if isinstance(raw_out, dict):
                        return raw_out
        except Exception as e:
            logger.debug(f"AI Connector news endpoint {ep_url} failed for {company_name}: {e}")
    return {}


def normalize_news_date(val: str | None) -> str:
    if not val or not str(val).strip():
        return datetime.now(UTC).strftime("%Y-%m-%d")
    s = str(val).strip()
    import re
    m_de = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m_de:
        day, month, year = m_de.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    m_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if m_iso:
        year, month, day = m_iso.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return s[:10]


@router.get("/company/{company_id}/news", response_model=list[CompanyNewsEntrySchema])
async def get_company_news(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company news for a given company.
    Calls AI Connector Deep Research for press & corporate blog synthesis, falling back to Tagesschau if offline.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

    result = await db.execute(select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id))
    news_entries = result.scalars().all()

    # Check if we have recent news
    has_recent = False
    for entry in news_entries:
        crawled_dt = entry.crawled_date.replace(tzinfo=None) if entry.crawled_date.tzinfo else entry.crawled_date
        if crawled_dt > one_hour_ago:
            has_recent = True
            break

    if news_entries and has_recent:
        logger.info(f"Returning cached news for {company_id}")
        return news_entries

    return await scrape_company_news(company_id=company_id, db=db)


@router.post("/company/{company_id}/news/scrape", response_model=list[CompanyNewsEntrySchema])
async def scrape_company_news(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Execute AI Connector Deep Research for company press news & corporate blog.
    Saves results directly to database and returns structured JSON news elements.
    """
    import hashlib
    from urllib.parse import unquote
    company_id = unquote(company_id)
    base_crawling_url = os.getenv("CRAWLING_URL", "http://localhost:8001").rstrip("/")
    candidate_crawling_urls = [
        f"{base_crawling_url}/api/v1/scrape/tagesschau",
        f"{base_crawling_url}/ms/crawling/api/v1/scrape/tagesschau",
        "http://localhost:8001/api/v1/scrape/tagesschau",
        "http://127.0.0.1:8001/api/v1/scrape/tagesschau",
        "http://crawling-app:8000/api/v1/scrape/tagesschau",
        "http://crawling-app-test:8000/api/v1/scrape/tagesschau",
    ]
    seen_cr = set()
    unique_crawling_urls = [u for u in candidate_crawling_urls if not (u in seen_cr or seen_cr.add(u))]

    # Step 1: Execute Deep Research via AI Connector
    logger.info(f"Triggering AI Connector Deep Research for company news: '{company_id}'")
    deep_res = await run_deep_research_company_news(company_id)
    press_items = deep_res.get("press_news") or []
    blog_items = deep_res.get("company_blog") or []

    scraped_articles = []
    for item in press_items:
        item["source_type"] = "press"
        item["category"] = "Presse & Medien (Deep Research)"
        scraped_articles.append(item)

    for item in blog_items:
        item["source_type"] = "company_blog"
        item["category"] = "Corporate Blog & Newsroom (Deep Research)"
        scraped_articles.append(item)

    # Step 2: Fallback to Tagesschau scraper ONLY if zero items from Deep Research
    if not scraped_articles:
        from core.utils import clean_company_name_candidates
        candidates = clean_company_name_candidates(company_id)
        logger.info(f"Fallback: Triggering Tagesschau API for '{company_id}' (candidates: {candidates})")

        # Try crawling microservice candidate URLs first
        for cand in candidates:
            for ep_url in unique_crawling_urls:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        res = await client.post(ep_url, json={"query": cand})
                        if res.status_code == 200 and res.json():
                            for it in res.json():
                                it["source_type"] = "press"
                                it["category"] = it.get("category") or "Tagesschau Presseecho"
                                scraped_articles.append(it)
                            break
                except Exception as e:
                    logger.debug(f"Crawling service Tagesschau fallback failed for {ep_url}: {e}")
            if scraped_articles:
                break

        # If crawling microservice was unreachable, query Tagesschau open API directly from bidding MS
        if not scraped_articles:
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    for cand in candidates:
                        resp = await client.get("https://www.tagesschau.de/api2u/search/", params={"searchText": cand, "pageSize": 20})
                        if resp.status_code == 200:
                            data = resp.json()
                            items = data.get("searchResults", []) or data.get("news", [])
                            for item in items:
                                t = item.get("title", "")
                                if not t:
                                    continue
                                l = item.get("detailsweb") or item.get("shareURL") or item.get("url") or ""
                                h = hashlib.md5(f"{t}{l}".encode()).hexdigest()
                                p = item.get("date") or item.get("sophoraCreated") or datetime.now(UTC).strftime("%Y-%m-%d")
                                scraped_articles.append({
                                    "hash": h,
                                    "title": t,
                                    "link": l,
                                    "summary": item.get("teaserText") or t,
                                    "content": item.get("teaserText") or t,
                                    "published_date": p[:10],
                                    "category": "Tagesschau Presseecho",
                                    "source_type": "press",
                                    "sentiment_score": 50,
                                    "sentiment_label": "Neutral",
                                    "sentiment_rationale": "Tagesschau Presseecho",
                                    "key_topics": ["Tagesschau"]
                                })
                            if scraped_articles:
                                break
            except Exception as ex:
                logger.error(f"Direct Tagesschau API query exception: {ex}")

    # Step 3: Clear old entries for company and persist new entries to DB
    old_entries_res = await db.execute(select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id))
    for old in old_entries_res.scalars().all():
        await db.delete(old)

    cutoff_date = (datetime.now(UTC) - timedelta(days=730)).strftime("%Y-%m-%d")
    seen_hashes = set()
    new_entries = []

    for item in scraped_articles:
        article_hash = item.get("hash") or item.get("link") or item.get("title")
        if not article_hash or article_hash in seen_hashes:
            continue
        seen_hashes.add(article_hash)

        raw_pub = item.get("published_at") or item.get("published_date") or datetime.now(UTC).strftime("%Y-%m-%d")
        pub_date = normalize_news_date(raw_pub)

        if pub_date >= cutoff_date or len(pub_date) < 10:
            entry = CompanyNewsEntry(
                company_id=company_id,
                hash=str(article_hash),
                title=item.get("title", ""),
                link=item.get("link", ""),
                content=item.get("content") or item.get("summary") or "",
                summary=item.get("summary"),
                category=item.get("category", "Unternehmens-News"),
                source_type=item.get("source_type", "press"),
                published_date=pub_date,
                crawled_date=datetime.now(UTC).replace(tzinfo=None),
                sentiment_score=item.get("sentiment_score"),
                sentiment_label=item.get("sentiment_label"),
                sentiment_rationale=item.get("sentiment_rationale"),
                key_topics=item.get("key_topics"),
            )
            db.add(entry)
            new_entries.append(entry)

    try:
        await db.commit()
        for e in new_entries:
            await db.refresh(e)
    except Exception as e:
        logger.warning(f"Save scraped news commit warning: {e}")

    return new_entries


@router.post("/company/{company_id}/news/refresh")
async def refresh_company_news_background(company_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Triggers an asynchronous background Deep Research refresh for company news without blocking the HTTP caller.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)

    async def _bg_worker(c_id: str):
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            try:
                logger.info(f"Starting background Deep Research refresh for '{c_id}'")
                await scrape_company_news(company_id=c_id, db=session)
                logger.info(f"Completed background Deep Research refresh for '{c_id}'")
            except Exception as ex:
                logger.error(f"Background Deep Research refresh error for '{c_id}': {ex}")

    background_tasks.add_task(_bg_worker, company_id)
    return {"status": "queued", "company_id": company_id, "message": "Deep research background refresh task queued"}
