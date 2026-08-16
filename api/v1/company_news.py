import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
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
    """Queries AI Connector using model_tier='deep-research' for dual-section press news & blog synthesis."""
    from core.config import AI_URL
    ai_url = AI_URL or os.getenv("AI_URL", "http://ai:8004")
    prompt_payload = {
        "prompt_id": "company_deep_research_news",
        "input_text": f"Execute deep research for news and official blog articles regarding company: '{company_name}'. Official newsroom/blog URLs: {newsroom_urls or []}.",
        "model_tier": "deep-research",
        "output_structure": {
            "press_news": [
                {
                    "title": "Headline",
                    "link": "https://...",
                    "summary": "2-sentence summary of news item",
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
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{ai_url}/api/inference", json=prompt_payload)
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
                    return json.loads(cleaned)
                if isinstance(raw_out, dict):
                    return raw_out
    except Exception as e:
        logger.warning(f"Deep Research call for {company_name} failed: {e}")
    return {}


@router.get("/company/{company_id}/news", response_model=list[CompanyNewsEntrySchema])
async def get_company_news(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company news for a given company.
    Checks master data for custom newsroom/blog portal links, crawls them via crawling MS,
    and falls back to Tagesschau if no portal links exist or return zero results.
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

    crawling_url = os.getenv("CRAWLING_URL", "http://tender-crawling:8001")
    distributing_url = os.getenv("DISTRIBUTING_URL", "http://tender-distributing:8005")

    # Step 1: Discover newsroom and blog links from master-data
    target_newsroom_urls = []
    company_name = company_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            md_res = await client.get(f"{distributing_url}/api/master-data")
            if md_res.status_code == 200:
                md_data = md_res.json()
                target_companies = md_data.get("target_companies", [])
                for comp in target_companies:
                    if comp.get("id") == company_id or comp.get("name", "").lower() == company_id.lower():
                        company_name = comp.get("name", company_id)
                        pl = comp.get("portal_links") or {}

                        # Extract list arrays or string fallbacks
                        def _extract_url_list(val):
                            if not val:
                                return []
                            if isinstance(val, list):
                                return [str(u).strip() for u in val if isinstance(u, str) and u.strip()]
                            if isinstance(val, str) and val.strip():
                                return [val.strip()]
                            return []

                        newsroom_list = _extract_url_list(pl.get("newsroom")) or _extract_url_list(
                            pl.get("newsroom_url")
                        )
                        blog_list = _extract_url_list(pl.get("blog")) or _extract_url_list(pl.get("blog_url"))

                        target_newsroom_urls.extend(newsroom_list)
                        target_newsroom_urls.extend(blog_list)
                        break
    except Exception as e:
        logger.warning(f"Could not fetch master data portal links for {company_id}: {e}")

    scraped_articles = []

    # Step 2: Crawl DuckDuckGo News for target company/buyer
    from core.utils import clean_company_name_candidates
    candidates = clean_company_name_candidates(company_name)
    primary_query = candidates[0] if candidates else company_name

    logger.info(f"Triggering DuckDuckGo News scraper for {primary_query} (raw: {company_name})")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{crawling_url}/api/v1/scrape/news", json={"query": primary_query}, timeout=25.0)
            if res.status_code == 200:
                scraped_articles.extend(res.json())
    except Exception as e:
        logger.warning(f"Failed to fetch DuckDuckGo news for {primary_query}: {e}")

    # Step 3: Crawl custom or DDG-discovered newsroom/blog URLs
    async with httpx.AsyncClient(timeout=30.0) as client:
        if target_newsroom_urls:
            for url in target_newsroom_urls:
                try:
                    logger.info(f"Crawling master-data newsroom URL for {company_name}: {url}")
                    res = await client.post(
                        f"{crawling_url}/api/v1/scrape/newsroom",
                        json={"url": url, "company_name": primary_query},
                        timeout=25.0,
                    )
                    if res.status_code == 200:
                        scraped_articles.extend(res.json())
                except Exception as e:
                    logger.warning(f"Failed to crawl newsroom URL {url}: {e}")
        else:
            try:
                logger.info(f"Triggering DuckDuckGo newsroom discovery for {primary_query}")
                res = await client.post(
                    f"{crawling_url}/api/v1/scrape/newsroom", json={"company_name": primary_query}, timeout=25.0
                )
                if res.status_code == 200:
                    scraped_articles.extend(res.json())
            except Exception as e:
                logger.warning(f"Failed to discover/crawl newsrooms for {primary_query}: {e}")

    # Step 4: Fallback to Tagesschau search if no articles found so far
    if not scraped_articles:
        logger.info(f"Fallback: Triggering Tagesschau scraper for {company_name} (candidates: {candidates})")
        for cand in candidates:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(
                        f"{crawling_url}/api/v1/scrape/tagesschau", json={"query": cand}, timeout=25.0
                    )
                    if res.status_code == 200 and res.json():
                        scraped_articles.extend(res.json())
                        break
            except Exception as e:
                logger.error(f"Failed to connect to crawling service for Tagesschau fallback: {e}")

    if not scraped_articles:
        logger.info(f"No news articles found for {company_id}")
        return news_entries

    # Step 5: Deduplicate, filter to last 30 days (Tagesschau & News scan), and sort by published date descending
    cutoff_date = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
    seen_hashes = set()
    filtered_articles = []

    for item in scraped_articles:
        article_hash = item.get("hash") or item.get("link")
        if not article_hash or article_hash in seen_hashes:
            continue
        seen_hashes.add(article_hash)

        pub_date = item.get("published_at") or item.get("published_date") or datetime.now(UTC).strftime("%Y-%m-%d")
        if pub_date >= cutoff_date:
            item["_pub_date"] = pub_date
            filtered_articles.append(item)

    filtered_articles.sort(key=lambda x: x.get("_pub_date", ""), reverse=True)

    # Step 6: Clear old entries and save new ones
    try:
        for old_entry in news_entries:
            await db.delete(old_entry)

        new_entries = []
        for item in filtered_articles:
            entry = CompanyNewsEntry(
                company_id=company_id,
                hash=item.get("hash", ""),
                title=item.get("title", ""),
                link=item.get("link", ""),
                content=item.get("content", ""),
                category=item.get("category", "DuckDuckGo News"),
                published_date=item.get("_pub_date", ""),
                crawled_date=datetime.now(UTC).replace(tzinfo=None),
            )
            db.add(entry)
            new_entries.append(entry)

        await db.commit()
        for e in new_entries:
            await db.refresh(e)

        return new_entries

    except Exception as e:
        logger.error(f"Error updating company news DB: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/company/{company_id}/news/scrape", response_model=list[CompanyNewsEntrySchema])
async def scrape_company_news(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Force re-scrape company news and execute Deep Research for press news & corporate blog/newsroom.
    """
    from urllib.parse import unquote
    company_id = unquote(company_id)
    crawling_url = os.getenv("CRAWLING_URL", "http://tender-crawling:8001")

    # Step 1: Execute Deep Research for Press & Company Blog
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

    # Step 2: Fallback to Tagesschau scraper if zero items from Deep Research
    if not scraped_articles:
        candidates = [company_id]
        if len(company_id) <= 5:
            candidates.extend([f"{company_id} Management", f"{company_id} Beratung", f"{company_id} GmbH", f"{company_id} IT"])

        for cand in candidates:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(
                        f"{crawling_url}/api/v1/scrape/tagesschau", json={"query": cand}, timeout=25.0
                    )
                    if res.status_code == 200 and res.json():
                        for it in res.json():
                            it["source_type"] = "press"
                            scraped_articles.append(it)
                        break
            except Exception as e:
                logger.error(f"Failed to connect to crawling service for Tagesschau scrape: {e}")

    # Step 3: Clear old entries for company and persist new entries
    old_entries_res = await db.execute(select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id))
    for old in old_entries_res.scalars().all():
        await db.delete(old)

    seen_hashes = set()
    new_entries = []
    for item in scraped_articles:
        article_hash = item.get("hash") or item.get("link") or item.get("title")
        if not article_hash or article_hash in seen_hashes:
            continue
        seen_hashes.add(article_hash)

        pub_date = item.get("published_at") or item.get("published_date") or datetime.now(UTC).strftime("%Y-%m-%d")
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
