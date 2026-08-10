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
    title: str | None
    link: str | None
    content: str | None
    category: str | None
    published_date: str | None

    class Config:
        from_attributes = True


@router.get("/company/{company_id:path}/news", response_model=list[CompanyNewsEntrySchema])
async def get_company_news(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company news for a given company.
    Checks master data for custom newsroom/blog portal links, crawls them via crawling MS,
    and falls back to Tagesschau if no portal links exist or return zero results.
    """
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
    logger.info(f"Triggering DuckDuckGo News scraper for {company_name}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{crawling_url}/api/v1/scrape/news", json={"query": company_name}, timeout=25.0)
            if res.status_code == 200:
                scraped_articles.extend(res.json())
    except Exception as e:
        logger.warning(f"Failed to fetch DuckDuckGo news for {company_name}: {e}")

    # Step 3: Crawl custom or DDG-discovered newsroom/blog URLs
    async with httpx.AsyncClient(timeout=30.0) as client:
        if target_newsroom_urls:
            for url in target_newsroom_urls:
                try:
                    logger.info(f"Crawling master-data newsroom URL for {company_name}: {url}")
                    res = await client.post(
                        f"{crawling_url}/api/v1/scrape/newsroom",
                        json={"url": url, "company_name": company_name},
                        timeout=25.0,
                    )
                    if res.status_code == 200:
                        scraped_articles.extend(res.json())
                except Exception as e:
                    logger.warning(f"Failed to crawl newsroom URL {url}: {e}")
        else:
            try:
                logger.info(f"Triggering DuckDuckGo newsroom discovery for {company_name}")
                res = await client.post(
                    f"{crawling_url}/api/v1/scrape/newsroom", json={"company_name": company_name}, timeout=25.0
                )
                if res.status_code == 200:
                    scraped_articles.extend(res.json())
            except Exception as e:
                logger.warning(f"Failed to discover/crawl newsrooms for {company_name}: {e}")

    # Step 4: Fallback to Tagesschau search if no articles found so far
    if not scraped_articles:
        logger.info(f"Fallback: Triggering Tagesschau scraper for {company_name}")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{crawling_url}/api/v1/scrape/tagesschau", json={"query": company_name}, timeout=25.0
                )
                if res.status_code == 200:
                    scraped_articles.extend(res.json())
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
