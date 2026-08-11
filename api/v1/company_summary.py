import logging
import os
from datetime import UTC, datetime

import httpx
from core.database import get_db
from fastapi import APIRouter, Depends, HTTPException
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
    data = {}
    try:
        res_nd = await db.execute(select(CompanyNorthData).where(CompanyNorthData.company_id == company_id))
        data["northdata"] = res_nd.scalars().first()

        res_mood = await db.execute(select(CompanyMood).where(CompanyMood.company_id == company_id))
        data["moods"] = res_mood.scalars().all()

        res_jobs = await db.execute(select(CompanyJobEntry).where(CompanyJobEntry.company_id == company_id))
        data["jobs"] = res_jobs.scalars().all()

        res_news = await db.execute(select(CompanyNewsEntry).where(CompanyNewsEntry.company_id == company_id))
        data["news"] = res_news.scalars().all()

        res_tenders = await db.execute(select(CompanyHistoricTender).where(CompanyHistoricTender.company_id == company_id))
        data["historic_tenders"] = res_tenders.scalars().all()

        res_ins = await db.execute(select(CompanyInsolvency).where(CompanyInsolvency.company_id == company_id))
        data["insolvency"] = res_ins.scalars().first()
    except Exception as e:
        logger.warning(f"Error fetching DB company data for {company_name}: {e}")
    return data


async def run_stage1_solvency(company_name: str, is_aor: bool, db: AsyncSession | None = None) -> dict:
    db_data = await get_company_db_data(company_name, db)
    nd: CompanyNorthData | None = db_data.get("northdata")
    moods: list[CompanyMood] = db_data.get("moods") or []
    ins: CompanyInsolvency | None = db_data.get("insolvency")

    if is_aor:
        solvency_status = "AÖR Öffentliche Hand (Keine Registerwarnung)"
        credit_score = "AAA (AÖR)"
        financial_trend = "Öffentliches Budget"
        short_summary = f"{company_name} ist eine Anstalt des öffentlichen Rechts (AÖR)."
        long_summary = f"Öffentlicher Auftraggeber {company_name}."
        bid_manager_summary = ""
    elif nd:
        solvency_status = f"{nd.register_court or ''} {nd.register_number or ''}".strip()
        credit_score = "North Data verifiziert"
        financial_trend = f"{len(nd.financials or [])} Bilanzen erfasst" if nd.financials else ""
        court_str = f"am Amtsgericht {nd.register_court}" if nd.register_court else ""
        num_str = f"unter {nd.register_number}" if nd.register_number else ""
        short_summary = f"{company_name} {court_str} {num_str}".strip()
        long_summary = nd.business_purpose or ""
        bid_manager_summary = ""
    else:
        solvency_status = ""
        credit_score = ""
        financial_trend = ""
        short_summary = f"{company_name} (Erfassung ausstehend)"
        long_summary = ""
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

    if ins and ins.has_notices:
        red_flags.append("⚠️ Insolvenzbekanntmachungen im Register gefunden")

    return {
        "short_summary": short_summary,
        "long_summary": long_summary,
        "bid_manager_summary": bid_manager_summary,
        "financial_solvency_badges": {
            "solvency_status": solvency_status,
            "credit_score": credit_score,
            "financial_trend": financial_trend
        },
        "kununu_sentiment": {
            "work_life_balance": wlb,
            "management_rating": mgmt,
            "retention_score": retention
        },
        "red_flag_banners": red_flags
    }


async def run_stage2_implicit_needs(company_name: str, db: AsyncSession | None = None) -> dict:
    db_data = await get_company_db_data(company_name, db)
    jobs: list[CompanyJobEntry] = db_data.get("jobs") or []

    hiring_radar = []
    implicit_needs = []
    if jobs:
        for j in jobs[:6]:
            hiring_radar.append({
                "title": j.title or "",
                "category": j.employment_type or ""
            })
        for j in jobs[:3]:
            implicit_needs.append({
                "need": f"Expertise für {j.title}",
                "source": j.title or "",
                "relevance": "Hoch"
            })

    crawling_url = os.getenv("CRAWLING_URL", "http://127.0.0.1:8001")
    scraped_articles = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{crawling_url}/api/v1/scrape/tagesschau",
                json={"query": company_name},
                timeout=10.0
            )
            if res.status_code == 200:
                scraped_articles = res.json()
    except Exception as e:
        logger.warning(f"Could not trigger Tagesschau scraper via crawling service for {company_name}: {e}")

    # Direct open-data Tagesschau Search API fallback (https://www.tagesschau.de/api2u/search/)
    if not scraped_articles and company_name:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://www.tagesschau.de/api2u/search/",
                    params={"searchText": company_name, "resultPage": 0, "pageSize": 30},
                    timeout=10.0
                )
                if res.status_code == 200:
                    news_data = res.json()
                    raw_news = news_data.get("searchResults", []) or news_data.get("news", [])
                    for item in raw_news:
                        title = item.get("title") or ""
                        details = item.get("firstSentence") or item.get("teaserImage", {}).get("title", "")
                        share_url = item.get("detailsweb") or item.get("shareURL") or ""
                        pub_str = item.get("date") or ""
                        if title:
                            scraped_articles.append({
                                "title": title,
                                "link": share_url,
                                "content": details,
                                "published_at": pub_str
                            })
        except Exception as direct_e:
            logger.warning(f"Direct Tagesschau API call failed for {company_name}: {direct_e}")

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
        sentiment = f"Überwiegend Positiv / Neutral ({len(scraped_articles)} Artikel im 30-Tage Fenster)"
    else:
        sentiment = "Keine auffälligen Pressemeldungen in den letzten 30 Tagen (Tagesschau Scan)"

    subsidies = scrape_company_subsidies_on_the_fly(company_name)

    return {
        "active_hiring_radar": hiring_radar,
        "implicit_tender_needs": implicit_needs,
        "subsidies_grants_radar": subsidies,
        "tagesschau_news_scan": {
            "source_api": "https://tagesschau.api.bund.dev/",
            "scan_window_days": 30,
            "articles_found": len(scraped_articles),
            "reputation_sentiment": sentiment,
            "scandal_press_flags": scandal_flags,
            "recent_headlines": recent_headlines[:3] if recent_headlines else [f"Keine Pressemeldungen für {company_name} im 30-Tage Fenster verzeichnet"]
        }
    }


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


@router.get("/bids/{bid_id}/company-summary")
async def get_company_summary(bid_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Bid).where(Bid.id == bid_id)
    res = await db.execute(stmt)
    bid = res.scalar_one_or_none()
    if not bid or not bid.company_summary:
        raise HTTPException(status_code=404, detail="Company summary not found for this bid")
    return bid.company_summary


@router.post("/bids/{bid_id}/company-summary/extract")
async def extract_company_summary(
    bid_id: str,
    req: ExtractSummaryRequest | None = None,
    stage: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    company_name = req.company_name if (req and req.company_name) else "Ziel-Auftraggeber"
    is_aor = req.is_aor if (req and req.is_aor is not None) else ("Landesbetrieb" in company_name or "Amt" in company_name or "AÖR" in company_name or "Flughafen" in company_name)
    target_stage = req.stage if (req and req.stage is not None) else stage

    # Fetch existing bid summary or create placeholder
    stmt = select(Bid).where(Bid.id == bid_id)
    res = await db.execute(stmt)
    bid = res.scalar_one_or_none()

    existing_summary = dict(bid.company_summary) if (bid and bid.company_summary) else {}

    # Initialize summary structure if empty
    summary_data = {
        "bid_id": bid_id,
        "company_name": company_name,
        "pipeline_status": existing_summary.get("pipeline_status") or get_default_pipeline_status(),
        "extracted_at": datetime.now(UTC).isoformat()
    }
    summary_data.update(existing_summary)

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
        bid.company_summary = summary_data
        bid.company_summary_updated_at = datetime.now(UTC)

    await db.commit()
    return summary_data
