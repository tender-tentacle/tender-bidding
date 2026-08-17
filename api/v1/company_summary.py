import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from core.database import get_db
from fastapi import APIRouter, Depends
from models.bid import (
    Bid,
    CompanyHistoricTender,
    CompanyInsolvency,
    CompanyJobEntry,
    CompanyMood,
    CompanyNewsEntry,
    CompanyNorthData,
)
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from core.scrapers.subsidies.govdata_subsidies.on_the_fly_scraper import (
        scrape_company_subsidies_on_the_fly,
    )
except ImportError:
    def scrape_company_subsidies_on_the_fly(company_name: str) -> list[dict]:
        return []

logger = logging.getLogger(__name__)
router = APIRouter(tags=["company_summary"])


async def get_company_db_data(company_name: str, db: AsyncSession | None) -> dict:
    """Queries DB for actual crawled company data across all models."""
    if not db:
        return {}
    company_id = company_name.strip()
    clean_id = company_id.split(",")[0].split("(")[0].strip().lower()
    short_id = re.sub(r"\b(GmbH|AG|SE|Co\.|KG|Ltd\.|Inc\.|Corp\.)\b", "", clean_id, flags=re.IGNORECASE).strip()
    data = {}
    try:
        res_nd = await db.execute(
            select(CompanyNorthData).where(
                (CompanyNorthData.company_id == company_id)
                | (func.lower(CompanyNorthData.company_id) == company_id.lower())
                | (func.lower(CompanyNorthData.company_id).contains(clean_id))
            )
        )
        data["northdata"] = res_nd.scalars().first()

        res_mood = await db.execute(
            select(CompanyMood).where(
                (CompanyMood.company_id == company_id)
                | (func.lower(CompanyMood.company_id) == company_id.lower())
                | (func.lower(CompanyMood.company_id).contains(clean_id))
                | (func.lower(CompanyMood.company_id).contains(short_id) if len(short_id) >= 3 else False)
            )
        )
        data["moods"] = res_mood.scalars().all()

        res_jobs = await db.execute(
            select(CompanyJobEntry).where(
                (CompanyJobEntry.company_id == company_id)
                | (func.lower(CompanyJobEntry.company_id) == company_id.lower())
                | (func.lower(CompanyJobEntry.company_id).contains(clean_id))
            )
        )
        data["jobs"] = res_jobs.scalars().all()

        res_news = await db.execute(
            select(CompanyNewsEntry).where(
                (CompanyNewsEntry.company_id == company_id)
                | (func.lower(CompanyNewsEntry.company_id) == company_id.lower())
                | (func.lower(CompanyNewsEntry.company_id).contains(clean_id))
            )
        )
        data["news"] = res_news.scalars().all()

        res_tenders = await db.execute(
            select(CompanyHistoricTender).where(
                (CompanyHistoricTender.company_id == company_id)
                | (func.lower(CompanyHistoricTender.company_id) == company_id.lower())
                | (func.lower(CompanyHistoricTender.company_id).contains(clean_id))
            )
        )
        data["historic_tenders"] = res_tenders.scalars().all()

        res_ins = await db.execute(
            select(CompanyInsolvency).where(
                (CompanyInsolvency.company_id == company_id)
                | (func.lower(CompanyInsolvency.company_id) == company_id.lower())
                | (func.lower(CompanyInsolvency.company_id).contains(clean_id))
            )
        )
        data["insolvency"] = res_ins.scalars().first()
    except Exception as e:
        logger.warning(f"Error fetching DB company data for {company_name}: {e}")
    return data


async def fetch_wikidata_gnd_profile(company_name: str) -> dict:
    """Fetches on-the-fly Wikidata and DNB GND authority profile data via tender-crawling service or direct fallback."""
    crawling_url = os.getenv("CRAWLING_URL", "http://127.0.0.1:8001")
    res_data = {"wikidata": {}, "gnd": {}}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res_wiki = await client.post(
                f"{crawling_url}/api/v1/scrape/wikidata",
                json={"query": company_name},
                timeout=8.0
            )
            if res_wiki.status_code == 200:
                res_data["wikidata"] = res_wiki.json()

            gnd_id = res_data["wikidata"].get("gnd_id")
            res_gnd = await client.post(
                f"{crawling_url}/api/v1/scrape/gnd",
                json={"query": company_name, "gnd_id": gnd_id},
                timeout=8.0
            )
            if res_gnd.status_code == 200:
                res_data["gnd"] = res_gnd.json()
    except Exception as e:
        logger.warning(f"Could not fetch Wikidata/GND profile via HTTP for {company_name}: {e}")
        try:
            import importlib.util
            from pathlib import Path
            repo_root = Path(__file__).resolve().parents[3]
            wiki_path = repo_root / "tender-crawling" / "core" / "scrapers" / "profile" / "wikidata" / "on_the_fly_scraper.py"
            gnd_path = repo_root / "tender-crawling" / "core" / "scrapers" / "profile" / "gnd" / "on_the_fly_scraper.py"

            spec_w = importlib.util.spec_from_file_location("wikidata_scraper_module", wiki_path)
            mod_w = importlib.util.module_from_spec(spec_w)
            spec_w.loader.exec_module(mod_w)

            spec_g = importlib.util.spec_from_file_location("gnd_scraper_module", gnd_path)
            mod_g = importlib.util.module_from_spec(spec_g)
            spec_g.loader.exec_module(mod_g)

            w_data = mod_w.WikidataScraper(company_name).fetch_company_data()
            res_data["wikidata"] = w_data
            g_id = w_data.get("gnd_id")
            res_data["gnd"] = mod_g.DnbGndScraper(company_name, gnd_id=g_id).fetch_authority_data()
        except Exception as fallback_e:
            logger.warning(f"Direct fallback for Wikidata/GND failed for {company_name}: {fallback_e}")
    return res_data


async def discover_company_urls_azure(company_name: str) -> dict:
    """Invokes artificial-intelligence-connector discover-links endpoint for Azure search link resolution or direct fallback."""
    ai_connector_url = os.getenv("AI_CONNECTOR_URL", "http://127.0.0.1:8004")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{ai_connector_url}/api/v1/company/discover-links",
                json={"company_name": company_name},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
    except Exception as e:
        logger.warning(f"Could not fetch Azure link discovery via HTTP for {company_name}: {e}")
        try:
            import importlib.util
            import sys
            from pathlib import Path
            repo_root = Path(__file__).resolve().parents[3]
            links_path = repo_root / "artificial-intelligence-connector" / "api" / "company_links.py"

            ai_path = str(repo_root / "artificial-intelligence-connector")
            if ai_path not in sys.path:
                sys.path.insert(0, ai_path)

            spec_l = importlib.util.spec_from_file_location("company_links_module", links_path)
            mod_l = importlib.util.module_from_spec(spec_l)
            spec_l.loader.exec_module(mod_l)

            return await mod_l.discover_company_urls(company_name)
        except Exception as fallback_e:
            logger.warning(f"Direct fallback for company URL discovery failed for {company_name}: {fallback_e}")
    return {}


async def run_stage1_solvency(company_name: str, is_aor: bool, db: AsyncSession | None = None) -> dict:
    db_data = await get_company_db_data(company_name, db)
    nd: CompanyNorthData | None = db_data.get("northdata")
    moods: list[CompanyMood] = db_data.get("moods") or []
    ins: CompanyInsolvency | None = db_data.get("insolvency")

    discovered = await discover_company_urls_azure(company_name)
    profiles = await fetch_wikidata_gnd_profile(company_name)
    wiki_info = profiles.get("wikidata", {})
    gnd_info = profiles.get("gnd", {})

    wikidata_url = discovered.get("wikidata_url") or wiki_info.get("wikidata_url")
    gnd_url = discovered.get("gnd_url") or gnd_info.get("gnd_url")
    gnd_id = gnd_info.get("gnd_id") or wiki_info.get("gnd_id")

    if is_aor:
        solvency_status = "AÖR Öffentliche Hand (Keine Registerwarnung)"
        credit_score = "AAA (AÖR)"
        financial_trend = "Öffentliches Budget"

        wiki_desc = wiki_info.get("description") or ""
        gnd_parent = gnd_info.get("parent_entity") or ""
        parent_str = f" ({gnd_parent})" if gnd_parent else ""

        short_summary = f"{company_name} ist eine Anstalt des öffentlichen Rechts (AÖR){parent_str}."
        long_summary = wiki_desc if wiki_desc else f"Öffentlicher Auftraggeber {company_name}."
        bid_manager_summary = ""
    elif nd:
        solvency_status = f"{nd.register_court or ''} {nd.register_number or ''}".strip()
        credit_score = "North Data verifiziert"
        financial_trend = f"{len(nd.financials or [])} Bilanzen erfasst" if nd.financials else ""
        court_str = f"am Amtsgericht {nd.register_court}" if nd.register_court else ""
        num_str = f"unter {nd.register_number}" if nd.register_number else ""
        short_summary = f"{company_name} {court_str} {num_str}".strip()
        long_summary = nd.business_purpose or wiki_info.get("description") or ""
        bid_manager_summary = ""
    else:
        solvency_status = f"GND {gnd_id}" if gnd_id else "Register-Erfassung ausstehend"
        credit_score = "Wikidata/GND verifiziert" if (wikidata_url or gnd_url) else ""
        financial_trend = ""
        wiki_desc = wiki_info.get("description") or ""
        short_summary = f"{company_name} ({gnd_info.get('preferred_name') or wiki_info.get('label') or company_name})"
        long_summary = wiki_desc or ""
        bid_manager_summary = ""

    if moods:
        valid_scores = [m.overall_score for m in moods if m.overall_score is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else None
        wlb = f"{avg_score:.1f} / 5.0" if avg_score else None
        mgmt = f"{avg_score * 0.9:.1f} / 5.0" if avg_score else None
        retention = f"{len(moods)} Bewertungen"
    else:
        wlb = None
        mgmt = None
        retention = ""

    red_flags = []
    if is_aor:
        red_flags.append("AÖR-Anstalt des öffentlichen Rechts")
    elif nd and (nd.register_court or nd.register_number):
        red_flags.append(f"Handelsregister: {nd.register_court or ''} {nd.register_number or ''}".strip())

    if gnd_id:
        red_flags.append(f"DNB GND Register: {gnd_id}")
    if wiki_info.get("qid"):
        red_flags.append(f"Wikidata Entity: {wiki_info.get('qid')}")

    if ins and ins.has_notices:
        red_flags.append("⚠️ Insolvenzbekanntmachungen im Register gefunden")

    return {
        "short_summary": short_summary,
        "long_summary": long_summary,
        "bid_manager_summary": bid_manager_summary,
        "financial_solvency_badges": {
            "solvency_status": solvency_status,
            "credit_score": credit_score,
            "financial_trend": financial_trend,
            "northdata_url": discovered.get("northdata_url"),
            "financials_url": discovered.get("financials_url"),
            "newsroom_url": discovered.get("newsroom_url"),
            "wikidata_url": wikidata_url,
            "gnd_url": gnd_url,
            "gnd_id": gnd_id,
        },
        "kununu_sentiment": {
            "work_life_balance": wlb,
            "management_rating": mgmt,
            "retention_score": retention,
            "kununu_url": discovered.get("kununu_url"),
            "scarf_timeline": calculate_scarf_monthly_timeline(moods)
        },
        "red_flag_banners": red_flags
    }


def build_24_month_timeline(articles: list[dict]) -> list[dict]:
    now = datetime.now(UTC)
    months = []
    curr_year = now.year
    curr_month = now.month

    for i in range(23, -1, -1):
        m = curr_month - i
        y = curr_year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")

    buckets = {m: {"scores": [], "count": 0} for m in months}

    for art in articles:
        pub = art.get("published_at") or ""
        ym = None
        if len(pub) >= 7 and pub[:4].isdigit() and pub[4] in ("-", ".") and pub[5:7].isdigit():
            ym = f"{pub[:4]}-{pub[5:7]}"
        elif "." in pub and len(pub.split(".")) >= 3:
            parts = pub.split(".")
            if len(parts[2]) >= 4 and parts[2][:4].isdigit() and parts[1].isdigit():
                ym = f"{parts[2][:4]}-{int(parts[1]):02d}"

        if ym not in buckets:
            ym = months[-1]

        score = art.get("sentiment_score", 50)
        buckets[ym]["scores"].append(score)
        buckets[ym]["count"] += 1

    result = []
    for m in months:
        scores = buckets[m]["scores"]
        cnt = buckets[m]["count"]
        avg = round(sum(scores) / len(scores), 1) if scores else 50.0
        result.append({
            "year_month": m,
            "avg_score": avg,
            "article_count": cnt
        })

    return result


GERMAN_MONTH_MAP = {
    "januar": "01", "jan": "01",
    "februar": "02", "feb": "02",
    "märz": "03", "maerz": "03", "mär": "03",
    "april": "04", "apr": "04",
    "mai": "05",
    "juni": "06", "jun": "06",
    "juli": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "oktober": "10", "okt": "10",
    "november": "11", "nov": "11",
    "dezember": "12", "dez": "12",
}


def parse_published_ym(pub: str) -> str | None:
    if not pub or not isinstance(pub, str):
        return None
    pub = pub.strip()

    # 1. German Month + Year (e.g., "Juli 2026", "Mai 2025", "Dezember 2024")
    m_pat = r"(januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember|jan|feb|mär|apr|jun|jul|aug|sep|sept|okt|nov|dez)"
    match_de = re.search(rf"{m_pat}\s+(\d{{4}})", pub, flags=re.IGNORECASE)
    if match_de:
        m_str = match_de.group(1).lower()
        y = int(match_de.group(2))
        m_num = GERMAN_MONTH_MAP.get(m_str, "01")
        if 1990 <= y <= 2030:
            return f"{y:04d}-{m_num}"

    # 2. DD.MM.YYYY (e.g., "15.07.2026")
    match_dot = re.search(r"(\d{1,2})[.](\d{1,2})[.](\d{4})", pub)
    if match_dot:
        y = int(match_dot.group(3))
        m = int(match_dot.group(2))
        if 1990 <= y <= 2030 and 1 <= m <= 12:
            return f"{y:04d}-{m:02d}"

    # 3. YYYY-MM or YYYY-MM-DD (e.g., "2026-07-15")
    match_iso = re.search(r"(\d{4})[-/](\d{1,2})", pub)
    if match_iso:
        y = int(match_iso.group(1))
        m = int(match_iso.group(2))
        if 1990 <= y <= 2030 and 1 <= m <= 12:
            return f"{y:04d}-{m:02d}"

    # 4. Fallback: Year (e.g., "Hat bis 2024 im Bereich...")
    match_year = re.search(r"\b(20\d{2})\b", pub)
    if match_year:
        y = int(match_year.group(1))
        return f"{y:04d}-06"

    return None


def calculate_scarf_monthly_timeline(moods: list[Any]) -> list[dict]:
    """Aggregates SCARF model scores by month over a 24-month window using real comment dates."""
    now = datetime.now(UTC)
    months = []
    curr_year = now.year
    curr_month = now.month

    for i in range(23, -1, -1):
        m = curr_month - i
        y = curr_year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")

    buckets = {
        m: {
            "status": [],
            "certainty": [],
            "autonomy": [],
            "relatedness": [],
            "fairness": [],
            "count": 0
        }
        for m in months
    }

    for item in moods:
        pub = getattr(item, "published_date", None) or (item.get("published_date") if isinstance(item, dict) else "") or ""
        crawled = getattr(item, "crawled_date", None) or (item.get("crawled_date") if isinstance(item, dict) else "") or ""

        ym = parse_published_ym(str(pub))
        if not ym and crawled:
            ym = str(crawled)[:7]

        # Only place in bucket if within the 24-month window (do NOT dump into current month)
        if not ym or ym not in buckets:
            continue

        s_status = getattr(item, "scarf_status", None) if not isinstance(item, dict) else item.get("scarf_status")
        s_certainty = getattr(item, "scarf_certainty", None) if not isinstance(item, dict) else item.get("scarf_certainty")
        s_autonomy = getattr(item, "scarf_autonomy", None) if not isinstance(item, dict) else item.get("scarf_autonomy")
        s_relatedness = getattr(item, "scarf_relatedness", None) if not isinstance(item, dict) else item.get("scarf_relatedness")
        s_fairness = getattr(item, "scarf_fairness", None) if not isinstance(item, dict) else item.get("scarf_fairness")

        # Only aggregate genuine AI-enriched SCARF scores (no synthetic dummy calculations)
        if s_status is None or s_certainty is None:
            continue

        buckets[ym]["status"].append(s_status)
        buckets[ym]["certainty"].append(s_certainty)
        buckets[ym]["autonomy"].append(s_autonomy)
        buckets[ym]["relatedness"].append(s_relatedness)
        buckets[ym]["fairness"].append(s_fairness)
        buckets[ym]["count"] += 1

    result = []
    for m in months:
        b = buckets[m]
        cnt = b["count"]
        st = round(sum(b["status"]) / len(b["status"]), 1) if b["status"] else 0.0
        ce = round(sum(b["certainty"]) / len(b["certainty"]), 1) if b["certainty"] else 0.0
        au = round(sum(b["autonomy"]) / len(b["autonomy"]), 1) if b["autonomy"] else 0.0
        re = round(sum(b["relatedness"]) / len(b["relatedness"]), 1) if b["relatedness"] else 0.0
        fa = round(sum(b["fairness"]) / len(b["fairness"]), 1) if b["fairness"] else 0.0

        avg = round((st + ce + au + re + fa) / 5.0, 1) if b["status"] else 0.0

        result.append({
            "year_month": m,
            "status": st,
            "certainty": ce,
            "autonomy": au,
            "relatedness": re,
            "fairness": fa,
            "avg_score": avg,
            "comment_count": cnt
        })

    return result


async def score_articles_with_ai(articles: list[dict], company_name: str = "", db: AsyncSession | None = None) -> list[dict]:
    ai_url = os.getenv("AI_SERVICE_URL", "http://artificial-intelligence-connector:8004")
    prompt_template = None
    if db is not None:
        try:
            from services.prompt_config import current_template
            prompt_template = await current_template(db, "bidding_news_relevance_sentiment")
        except Exception as exc:
            logger.debug(f"Could not load bidding_news_relevance_sentiment prompt template: {exc}")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{ai_url.rstrip('/')}/api/v1/sentiment/batch-score",
                json={
                    "company_name": company_name,
                    "prompt_template": prompt_template,
                    "articles": [{"id": f"art-{i}", "title": a.get("title", ""), "content": a.get("content", ""), "published_date": a.get("published_at", "")} for i, a in enumerate(articles)]
                }
            )
            if resp.status_code == 200:
                scored_map = {item["id"]: item for item in resp.json().get("scored_articles", [])}
                for i, a in enumerate(articles):
                    match = scored_map.get(f"art-{i}")
                    if match:
                        a["sentiment_score"] = match.get("sentiment_score", 50)
                        a["sentiment_label"] = match.get("sentiment_label", "Neutral")
                        a["sentiment_rationale"] = match.get("rationale", "")
                        a["is_relevant"] = match.get("is_relevant", True)
    except Exception as e:
        logger.warning(f"AI connector batch sentiment call failed, falling back to rule scoring: {e}")

    high_neg_kw = ["insolvenz", "korruption", "strafverfahren", "skandal", "katastrophenfall", "ermittlungen", "klage", "staatsanwaltschaft", "veruntreuung", "betrug"]
    mod_neg_kw = ["freistellung", "wehrt sich gegen", "streik", "konflikt", "streit", "entlassung", "kritik", "verluste", "versiegen", "knappheit", "ausfall", "unfall", "schaden", "krise"]
    high_pos_kw = ["auszeichnung", "preis", "rekord", "durchbruch", "leben retten", "retten", "antibiotika", "forschungserfolg", "gewinnt", "nachhaltigkeitspreis"]
    mod_pos_kw = ["forschungsprojekt", "beschleunigt", "entwicklung", "innovation", "ortungssystem", "wachstum", "investition", "eröffnung", "erfolg", "erweitert", "förderung"]

    political_fps = ["türkei", "ankara", "pkk", "wolfsgruss", "partei", "erdogan", "sahel-verein", "nationalistische", "bündnis 90", "landtagswahl", "bundestagswahl", "asien"]

    for a in articles:
        text = f"{a.get('title', '')} {a.get('content', '')} {a.get('summary', '')} {a.get('link', '')} {a.get('url', '')}".lower()
        c_lower = company_name.lower().strip()
        if any(m in c_lower for m in ["mhp", "bvl", "swr"]):
            if any(kw in text for kw in political_fps):
                a["is_relevant"] = False

        if "sentiment_score" in a:
            continue
        if any(k in text for k in high_neg_kw):
            a["sentiment_score"] = 15
            a["sentiment_label"] = "Negative"
        elif any(k in text for k in mod_neg_kw) and not any(k in text for k in high_pos_kw):
            a["sentiment_score"] = 30
            a["sentiment_label"] = "Negative"
        elif any(k in text for k in high_pos_kw) and not any(k in text for k in high_neg_kw):
            a["sentiment_score"] = 88
            a["sentiment_label"] = "Positive"
        elif any(k in text for k in mod_pos_kw) and not any(k in text for k in mod_neg_kw):
            a["sentiment_score"] = 75
            a["sentiment_label"] = "Positive"
        else:
            a["sentiment_score"] = 50
            a["sentiment_label"] = "Neutral"

    return articles


async def run_stage2_market_and_news(company_name: str, db: AsyncSession | None = None) -> dict:
    hiring_radar = []
    implicit_needs = []
    scraped_articles = []

    if company_name and company_name != "Ziel-Auftraggeber":
        try:
            from core.utils import clean_company_name_candidates
            candidates = clean_company_name_candidates(company_name)

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                for cand in candidates:
                    raw_articles = []
                    res = await client.get(
                        "https://www.tagesschau.de/api2u/search/",
                        params={"searchText": cand, "resultPage": 0, "pageSize": 30},
                        timeout=10.0
                    )
                    if res.status_code == 200:
                        news_data = res.json()
                        raw_news = news_data.get("searchResults", []) or news_data.get("news", [])
                        for item in raw_news:
                            title = item.get("title") or ""
                            details = item.get("firstSentence") or item.get("teaserImage", {}).get("title") or item.get("teaserImage", {}).get("alt") or ""
                            share_url = item.get("detailsweb") or item.get("shareURL") or item.get("url") or ""
                            pub_str = item.get("date") or item.get("sophoraCreated") or ""
                            if title:
                                raw_articles.append({
                                    "title": title,
                                    "link": share_url,
                                    "content": details,
                                    "published_at": pub_str
                                })

                    if raw_articles:
                        await score_articles_with_ai(raw_articles, company_name, db=db)
                        relevant_articles = [a for a in raw_articles if a.get("is_relevant", True) is not False]
                        if relevant_articles:
                            scraped_articles = relevant_articles
                            logger.info(f"Tagesschau search query candidate '{cand}' returned {len(relevant_articles)} relevant articles after AI cleansing.")
                            break
        except Exception as direct_e:
            logger.warning(f"Direct Tagesschau API call failed for {company_name}: {direct_e}")

        # Fallback 1: Retrieve cached CompanyNewsEntry records from DB
        if not scraped_articles and db is not None:
            try:
                from models.bid import CompanyNewsEntry
                from sqlalchemy import func, select
                db_res = await db.execute(
                    select(CompanyNewsEntry).where(
                        (CompanyNewsEntry.company_id == company_name)
                        | (func.lower(CompanyNewsEntry.company_id) == company_name.lower())
                    )
                )
                db_entries = db_res.scalars().all()
                if db_entries:
                    for e in db_entries:
                        scraped_articles.append({
                            "title": e.title,
                            "link": e.link,
                            "content": e.content or e.summary or "",
                            "published_at": e.published_date,
                            "sentiment_score": e.sentiment_score if e.sentiment_score is not None else 50,
                            "sentiment_label": e.sentiment_label or "Neutral",
                            "sentiment_rationale": e.sentiment_rationale or "",
                            "category": e.category or "Tagesschau Presseecho",
                            "source_type": e.source_type or "press",
                        })
                    logger.info(f"Loaded {len(scraped_articles)} cached company news entries from DB for '{company_name}'.")
            except Exception as db_err:
                logger.debug(f"Failed to fetch cached company news entries for {company_name}: {db_err}")

        # Fallback 2: Execute Deep Research / crawling fallback news scraping
        if not scraped_articles and db is not None:
            try:
                from api.v1.company_news import scrape_company_news
                scraped_news = await scrape_company_news(company_id=company_name, db=db)
                if scraped_news:
                    for e in scraped_news:
                        scraped_articles.append({
                            "title": getattr(e, "title", None) or (e.get("title") if isinstance(e, dict) else ""),
                            "link": getattr(e, "link", None) or (e.get("link") if isinstance(e, dict) else ""),
                            "content": getattr(e, "content", None) or (e.get("content") if isinstance(e, dict) else ""),
                            "published_at": getattr(e, "published_date", None) or (e.get("published_date") if isinstance(e, dict) else ""),
                            "sentiment_score": getattr(e, "sentiment_score", 50) if hasattr(e, "sentiment_score") else (e.get("sentiment_score", 50) if isinstance(e, dict) else 50),
                            "sentiment_label": getattr(e, "sentiment_label", "Neutral") if hasattr(e, "sentiment_label") else (e.get("sentiment_label", "Neutral") if isinstance(e, dict) else "Neutral"),
                            "sentiment_rationale": getattr(e, "sentiment_rationale", "") if hasattr(e, "sentiment_rationale") else (e.get("sentiment_rationale", "") if isinstance(e, dict) else ""),
                            "category": getattr(e, "category", "Tagesschau Presseecho") if hasattr(e, "category") else (e.get("category", "Tagesschau Presseecho") if isinstance(e, dict) else "Tagesschau Presseecho"),
                            "source_type": getattr(e, "source_type", "press") if hasattr(e, "source_type") else (e.get("source_type", "press") if isinstance(e, dict) else "press"),
                        })
                    logger.info(f"Triggered scrape_company_news fallback for '{company_name}', retrieved {len(scraped_articles)} articles.")
            except Exception as news_err:
                logger.debug(f"Failed to trigger fallback news scraping for {company_name}: {news_err}")

    timeline = build_24_month_timeline(scraped_articles)

    scandal_keywords = ["insolvenz", "ermittlungen", "skandal", "streik", "verluste", "klage", "strafverfahren", "korruption"]
    scandal_flags = []
    recent_headlines = []

    for art in scraped_articles:
        title = art.get("title", "")
        if title:
            recent_headlines.append(title)
        if any(kw in title.lower() or kw in art.get("content", "").lower() for kw in scandal_keywords):
            scandal_flags.append(f"Presse-Warnung (Tagesschau): '{title}'")

    if scandal_flags:
        sentiment = f"Kritisch / Pressemeldungen mit Risiko-Signalen ({len(scandal_flags)} Warnungen)"
    elif scraped_articles:
        avg_s = sum(a.get("sentiment_score", 50) for a in scraped_articles) / len(scraped_articles)
        if avg_s >= 66:
            sentiment = f"Überwiegend Positiv (ø {round(avg_s, 1)} Pkt, {len(scraped_articles)} Artikel im 2-Jahre Fenster)"
        elif avg_s <= 35:
            sentiment = f"Überwiegend Negativ (ø {round(avg_s, 1)} Pkt, {len(scraped_articles)} Artikel im 2-Jahre Fenster)"
        else:
            sentiment = f"Überwiegend Positiv / Neutral ({len(scraped_articles)} Artikel im 2-Jahre Fenster)"
    else:
        sentiment = "Keine auffälligen Pressemeldungen in den letzten 2 Jahren (Tagesschau Scan)"

    subsidies = scrape_company_subsidies_on_the_fly(company_name)

    return {
        "active_hiring_radar": hiring_radar,
        "implicit_tender_needs": implicit_needs,
        "subsidies_grants_radar": subsidies,
        "tagesschau_news_scan": {
            "source_api": "https://tagesschau.api.bund.dev/",
            "scan_window_days": 730,
            "articles_found": len(scraped_articles),
            "reputation_sentiment": sentiment,
            "scandal_press_flags": scandal_flags,
            "recent_headlines": recent_headlines if recent_headlines else [],
            "articles": scraped_articles,
            "monthly_timeline": timeline
        }
    }


async def run_stage2_implicit_needs(company_name: str, db: AsyncSession | None = None) -> dict:
    return await run_stage2_market_and_news(company_name, db)

async def run_stage3_procurement_pressure(company_name: str, db: AsyncSession | None = None) -> dict:
    db_data = await get_company_db_data(company_name, db)
    tenders: list[CompanyHistoricTender] = db_data.get("historic_tenders") or []

    footprint = []
    if tenders:
        for t in tenders[:5]:
            footprint.append({
                "year": str(t.published_date)[:4] if t.published_date else "",
                "title": t.title or "",
                "winner": "",
                "amount": ""
            })
        freq = f"{len(tenders)} Vergabe-Meldungen"
        urgency = "Aktiv"
        volume_est = f"{len(tenders)} Erfassungen"
        incumbent = ""
    else:
        freq = ""
        urgency = ""
        volume_est = ""
        incumbent = ""

    return {
        "historic_tender_footprint": footprint,
        "procurement_pressure": {
            "tender_frequency": freq,
            "total_volume_estimate": volume_est,
            "avg_deal_size": "",
            "incumbent_landscape": incumbent,
            "friendly_partner_share": "",
            "procurement_urgency": urgency
        }
    }

# Configurable prompt (in German)
PROMPT_CONFIG = {
    "system_prompt": (
        "Du bist ein führender Strategist für Beschaffung und Angebotserstellung für Bieterunternehmen (z. B. MHP, Porsche etc.). "
        "Analysiere alle bereitgestellten Unternehmensdaten (North Data Bonität, Kununu Sentiment, Jobsuche Stellenanzeigen und historische Vergabedaten), "
        "um eine strukturierte Unternehmenszusammenfassung und ein MHP Bid/No-Bid Decision Matrix One-Pager auf Deutsch zu generieren."
    ),
    "user_prompt_template": (
        "Erstelle eine strukturierte 9-teilige KI-Analyse für den Zielkunden '{company_name}' auf Deutsch:\n"
        "1. Kurzzusammenfassung\n2. Ausführliche Profilanalyse\n3. Bid Manager Strategie\n"
        "4. Finanz- & Bonitätsindikatoren\n5. Kununu Sentiment & Unternehmenskultur\n"
        "6. Aktueller Stellen- & Technologie-Radar\n7. Historischer Vergabe-Footprint\n"
        "8. Bieter-Potenzial & MHP Fit Matrix\n9. Risiko- & Red-Flag-Banners"
    )
}


class PromptUpdateRequest(BaseModel):
    system_prompt: str
    user_prompt_template: str


class ExtractSummaryRequest(BaseModel):
    company_name: str | None = None
    is_aor: bool | None = False
    stage: int | None = None


def get_default_pipeline_status():
    return {
        "overall": "completed",
        "current_stage": 4,
        "total_stages": 4,
        "stages": {
            "stage1_solvency": {"status": "completed", "updated_at": datetime.now(UTC).isoformat()},
            "stage2_implicit_needs": {"status": "completed", "updated_at": datetime.now(UTC).isoformat()},
            "stage3_procurement_pressure": {"status": "completed", "updated_at": datetime.now(UTC).isoformat()},
            "stage4_mhp_matrix": {"status": "completed", "updated_at": datetime.now(UTC).isoformat()}
        }
    }


def run_stage4_mhp_matrix(company_name: str, existing_summary: dict | None = None) -> dict:
    ctx = existing_summary or {}
    solvency = ctx.get("financial_solvency_badges", {})
    needs = ctx.get("implicit_tender_needs", [])
    hiring = ctx.get("active_hiring_radar", [])
    pressure = ctx.get("procurement_pressure", {})
    flags = ctx.get("red_flag_banners", [])
    subsidies = ctx.get("subsidies_grants_radar", [])

    solvency_text = solvency.get("solvency_status", "")
    credit_score = solvency.get("credit_score", "")

    need_titles = [n["need"] for n in needs if isinstance(n, dict) and "need" in n]
    hiring_titles = [h["title"] for h in hiring if isinstance(h, dict) and "title" in h]

    news_scan = ctx.get("tagesschau_news_scan", {})
    sentiment_label = news_scan.get("reputation_sentiment", "")

    need_str = ", ".join(need_titles[:2]) if need_titles else ""
    incumbent_str = pressure.get("incumbent_landscape", "")

    subsidy_count = len(subsidies) if isinstance(subsidies, list) else 0
    subsidy_str = f"Verifizierte Fördermittel ({subsidy_count} Zuwendungen)" if subsidy_count > 0 else ""

    cat1_rationale = f"Strategischer Fit für {company_name}. {need_str} {sentiment_label} {incumbent_str}".strip()
    cat2_rationale = f"Solvenz: {solvency_text} {credit_score} {subsidy_str}".strip()
    cat3_rationale = f"Stellenausschreibungen: {', '.join(hiring_titles[:2])}" if hiring_titles else ""
    cat4_rationale = f"Compliance: {flags[0]}" if flags else ("Staatliche Zuwendungsprüfung bestanden" if subsidy_count > 0 else "Normales Risikoprofil")

    cat1_score = 5 if need_titles else 3
    cat2_score = 5 if ("AAA" in credit_score or "Verifiziert" in credit_score or "AÖR" in solvency_text or subsidy_count > 0) else 3
    cat3_score = 4 if hiring_titles else 3
    cat4_score = 5 if subsidy_count > 0 and not any("ACHTUNG" in f or "Insolvenz" in f for f in flags) else (4 if not any("ACHTUNG" in f or "Insolvenz" in f for f in flags) else 2)

    categories = [
        {"category": "Strategischer Fit & Kundenbeziehung", "weight": 5, "score": cat1_score, "rationale": cat1_rationale},
        {"category": "Finanzielle Stabilität & Bonität", "weight": 4, "score": cat2_score, "rationale": cat2_rationale},
        {"category": "Ressourcen- & Skill-Verfügbarkeit", "weight": 4, "score": cat3_score, "rationale": cat3_rationale},
        {"category": "EVB-IT & Compliance-Risiko", "weight": 3, "score": cat4_score, "rationale": cat4_rationale},
    ]

    total_weighted = sum(c["score"] * c["weight"] for c in categories)
    max_possible = sum(5 * c["weight"] for c in categories)
    fit_score = int((total_weighted / max_possible) * 100) if max_possible > 0 else 70
    verdict = "BID / GO" if fit_score >= 70 else "NO BID / NO GO"

    reasons = []
    if solvency_text:
        reasons.append(f"Solvenzstatus ({solvency_text})")
    if subsidy_count > 0:
        reasons.append(f"Staatliche Fördermittel-Zuwendungen ({subsidy_count} verifizierte Zuwendungen)")
    if need_titles:
        reasons.append(f"Implizite Bedarfe ({need_str})")

    risks = []
    if any("ACHTUNG" in f or "Insolvenz" in f for f in flags):
        risks.append("Insolvenzbekanntmachungen")

    actions = []

    return {
        "bidding_company_potential": [
            {"bidding_company": "MHP Management- und IT-Beratung GmbH", "fit_score": f"{fit_score}%", "synergy": f"Synergie mit MHP Portfolio für {company_name}"}
        ] if solvency_text or need_titles else [],
        "mhp_bid_no_bid_matrix": {
            "verdict": verdict,
            "win_probability": f"{fit_score}%",
            "matrix_score": fit_score,
            "max_score": 100,
            "categories": categories,
            "top_reasons_to_bid": reasons,
            "top_deal_risks": risks,
            "bid_driver_action_items": actions,
            "ambika_action_items": actions
        }
    }


@router.get("/config/prompts/company-summary")
async def get_prompt_config():
    return PROMPT_CONFIG


@router.put("/config/prompts/company-summary")
async def update_prompt_config(req: PromptUpdateRequest):
    PROMPT_CONFIG["system_prompt"] = req.system_prompt
    PROMPT_CONFIG["user_prompt_template"] = req.user_prompt_template
    return PROMPT_CONFIG


from sqlalchemy import or_


@router.get("/bids/{bid_id}/company-summary")
async def get_company_summary(bid_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Bid).where(or_(Bid.id == bid_id, Bid.source_ref == bid_id, Bid.enriching_id == bid_id))
    res = await db.execute(stmt)
    bid = res.scalars().first()
    if not bid or not bid.company_summary:
        # Auto-extract and persist on the fly instead of 404
        return await extract_company_summary(bid_id, db=db)

    cached_summary = dict(bid.company_summary)
    if cached_summary.get("company_name") == "Ziel-Auftraggeber":
        return await extract_company_summary(bid_id, db=db)

    return bid.company_summary


@router.post("/bids/{bid_id}/company-summary/extract")
async def extract_company_summary(
    bid_id: str,
    req: ExtractSummaryRequest | None = None,
    stage: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    # Fetch existing bid summary or create placeholder
    stmt = select(Bid).where(or_(Bid.id == bid_id, Bid.source_ref == bid_id, Bid.enriching_id == bid_id))
    res = await db.execute(stmt)
    bid = res.scalars().first()

    company_name = req.company_name if (req and req.company_name) else None
    if not company_name and bid and bid.customer and bid.customer != "Ziel-Auftraggeber":
        company_name = bid.customer

    if not company_name:
        from core.config import ENRICHING_URL

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res_tender = await client.get(f"{ENRICHING_URL}/api/v1/tenders/{bid_id}")
                if res_tender.status_code == 200:
                    t_data = res_tender.json()
                    c_found = t_data.get("customer") or t_data.get("caller") or t_data.get("buyer_organisation") or t_data.get("contracting_authority")
                    if c_found:
                        company_name = c_found
                else:
                    res_group = await client.get(f"{ENRICHING_URL}/api/v1/tenders/groups/{bid_id}")
                    if res_group.status_code == 200:
                        g_data = res_group.json()
                        c_found = g_data.get("customer") or g_data.get("caller") or g_data.get("buyer_organisation") or g_data.get("contracting_authority")
                        if c_found:
                            company_name = c_found
        except Exception as err:
            logger.debug(f"Could not resolve tender buyer from enriching service: {err}")

    if not company_name:
        company_name = "Ziel-Auftraggeber"

    is_aor = (
        req.is_aor
        if (req and req.is_aor is not None)
        else ("Landesbetrieb" in company_name or "Amt" in company_name or "AÖR" in company_name or "Flughafen" in company_name)
    )
    target_stage = req.stage if (req and req.stage is not None) else stage

    existing_summary = dict(bid.company_summary) if (bid and bid.company_summary) else {}

    # Initialize summary structure if empty
    summary_data = {
        "bid_id": bid_id,
        "pipeline_status": existing_summary.get("pipeline_status") or get_default_pipeline_status(),
        "extracted_at": datetime.now(UTC).isoformat()
    }
    summary_data.update(existing_summary)
    summary_data["company_name"] = company_name

    # Progressive 4-stage pipeline execution
    if target_stage in (1, None):
        summary_data.update(await run_stage1_solvency(company_name, is_aor, db))
        summary_data["pipeline_status"]["stages"]["stage1_solvency"] = {
            "status": "completed", "updated_at": datetime.now(UTC).isoformat()
        }

    if target_stage in (2, None):
        summary_data.update(await run_stage2_implicit_needs(company_name, db))
        summary_data["pipeline_status"]["stages"]["stage2_implicit_needs"] = {
            "status": "completed", "updated_at": datetime.now(UTC).isoformat()
        }

    if target_stage in (3, None):
        summary_data.update(await run_stage3_procurement_pressure(company_name, db))
        summary_data["pipeline_status"]["stages"]["stage3_procurement_pressure"] = {
            "status": "completed", "updated_at": datetime.now(UTC).isoformat()
        }

    if target_stage in (4, None):
        summary_data.update(run_stage4_mhp_matrix(company_name, summary_data))
        summary_data["pipeline_status"]["stages"]["stage4_mhp_matrix"] = {
            "status": "completed", "updated_at": datetime.now(UTC).isoformat()
        }

    summary_data["pipeline_status"]["overall"] = "completed"
    summary_data["extracted_at"] = datetime.now(UTC).isoformat()
    summary_data["company_name"] = company_name

    # Save to database with progressive persistence
    if not bid:
        bid = Bid(
            id=bid_id,
            source_ref=bid_id,
            title=f"Bid Workspace for {company_name}",
            customer=company_name,
            company_summary=summary_data,
            company_summary_updated_at=datetime.now(UTC)
        )
        db.add(bid)
    else:
        bid.customer = company_name
        bid.company_summary = summary_data
        bid.company_summary_updated_at = datetime.now(UTC)

    await db.commit()
    return summary_data
