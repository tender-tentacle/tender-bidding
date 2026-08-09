import logging
import os

import httpx
from core.database import get_db
from fastapi import APIRouter, Depends
from models.company_reputation import CompanyReputationCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()

AI_URL = os.getenv("AI_URL", "http://ai:8004").rstrip("/")


@router.get("/company/{company_id:path}/reputation")
async def get_company_reputation(company_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get company intelligence (news, jobs, blog, financials, mood).
    Uses AI Connector as the primary search engine and caches results in DB for 30 days.
    """
    company_name = company_id

    # 1. Check DB Cache (30 days TTL)
    result = await db.execute(select(CompanyReputationCache).filter_by(company_id=company_id))
    cached = result.scalars().all()
    valid_cache = [c for c in cached if c.is_valid]

    categories_data = {
        "news": [],
        "jobs": [],
        "blog": [],
        "financials": [],
        "mood": [],
    }

    if valid_cache:
        for c in valid_cache:
            if c.search_type in categories_data:
                categories_data[c.search_type] = c.cached_data
        return categories_data

    # 2. Cache Miss or Stale Cache: Use AI Connector as Primary Search Engine
    portal_links = {}
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            # Query AI Connector primary search engine endpoint
            ai_search_url = f"{AI_URL}/api/search/company-portals"
            resp = await client.post(ai_search_url, json={"company_name": company_name})
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                portal_links = data.get("portal_links", {})
        except Exception as e:
            logger.warning(f"AI_URL {AI_URL} not directly reachable, invoking AI search module for {company_name}: {e}")
            try:
                import importlib.util
                from pathlib import Path

                ai_web_client_path = (
                    Path(__file__).parents[3] / "artificial-intelligence-connector" / "core" / "web_client.py"
                )
                spec = importlib.util.spec_from_file_location("ai_core_web_client", str(ai_web_client_path))
                ai_web_client = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ai_web_client)
                res_data = await ai_web_client.discover_company_portals(company_name)
                portal_links = res_data.get("portal_links", {})
            except Exception as ex:
                logger.error(f"Fallback discovery failed: {ex}")

    CRAWLING_MS_URL = os.getenv("CRAWLING_URL", "http://tender-crawling:8001").rstrip("/")

    if portal_links:
        # Persist discovered portal links & scraped data into 30-day DB cache
        for cat_key, target_url in portal_links.items():
            search_type = cat_key.replace("_url", "")
            if search_type == "newsroom":
                search_type = "news"
            elif search_type == "financial":
                search_type = "financials"

            if isinstance(target_url, list):
                cat_payload = [
                    {"url": u, "title": f"{company_name} {search_type.capitalize()} Portal"}
                    for u in target_url
                    if isinstance(u, str) and u.strip()
                ]
            elif isinstance(target_url, str) and target_url.strip():
                cat_payload = [
                    {"url": target_url.strip(), "title": f"{company_name} {search_type.capitalize()} Portal"}
                ]
            else:
                cat_payload = []

            if cat_payload:
                categories_data[search_type] = cat_payload

    # 3. Query DDG Reputation Scraper for actual scraped news articles and job offers
    async with httpx.AsyncClient(timeout=25.0) as client:
        for stype in ["news", "jobs"]:
            try:
                res = await client.post(
                    f"{CRAWLING_MS_URL}/api/v1/scrape/reputation/ddg",
                    json={"query": company_name, "search_type": stype},
                    timeout=20.0,
                )
                if res.status_code == 200:
                    ddg_results = res.json()
                    if ddg_results and isinstance(ddg_results, list):
                        existing_urls = {
                            item.get("url")
                            for item in categories_data[stype]
                            if isinstance(item, dict) and item.get("url")
                        }
                        for d_item in ddg_results:
                            if isinstance(d_item, dict) and d_item.get("url") not in existing_urls:
                                d_item["type"] = stype
                                categories_data[stype].append(d_item)
                                existing_urls.add(d_item.get("url"))
            except Exception as e:
                logger.warning(f"Failed to fetch DDG reputation {stype} for {company_name}: {e}")

    # Persist all discovered & scraped categories into DB cache
    for search_type, cat_payload in categories_data.items():
        if cat_payload:
            new_cache = CompanyReputationCache(
                company_id=company_id,
                search_type=search_type,
                cached_data=cat_payload,
            )
            db.add(new_cache)

    if any(categories_data.values()):
        await db.commit()

    return categories_data
