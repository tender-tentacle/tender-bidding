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
                ai_web_client_path = Path(__file__).parents[3] / "artificial-intelligence-connector" / "core" / "web_client.py"
                spec = importlib.util.spec_from_file_location("ai_core_web_client", str(ai_web_client_path))
                ai_web_client = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ai_web_client)
                res_data = await ai_web_client.discover_company_portals(company_name)
                portal_links = res_data.get("portal_links", {})
            except Exception as ex:
                logger.error(f"Fallback discovery failed: {ex}")

    if portal_links:
        # Persist discovered portal links & scraped data into 30-day DB cache
        for cat_key, target_url in portal_links.items():
            search_type = cat_key.replace("_url", "")
            if search_type == "newsroom":
                search_type = "news"
            elif search_type == "financial":
                search_type = "financials"

            if isinstance(target_url, list):
                cat_payload = [{"url": u, "title": f"{company_name} {search_type.capitalize()} Portal"} for u in target_url if isinstance(u, str) and u.strip()]
            elif isinstance(target_url, str) and target_url.strip():
                cat_payload = [{"url": target_url.strip(), "title": f"{company_name} {search_type.capitalize()} Portal"}]
            else:
                cat_payload = []

            if cat_payload:
                categories_data[search_type] = cat_payload

                new_cache = CompanyReputationCache(
                    company_id=company_id,
                    search_type=search_type,
                    cached_data=cat_payload,
                )
                db.add(new_cache)

        await db.commit()

    return categories_data
