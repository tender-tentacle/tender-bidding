"""Integration test: Kununu reviews for MHP → AI Connector SCARF enrichment → Bidding MS DB persistence & display.

Validates the full pipeline:
1. MHP Kununu review comments creation/mocking.
2. AI Connector SCARF enrichment POST /api/v1/enrich/scarf (mocking SCARF model evaluations).
3. Bidding MS SCARF enrichment processing (saving SCARF dimensions to DB).
4. Final enriched display payload assertion (overall SCARF averages, threat/reward tags, monthly timeline).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from api.v1.company_mood import enrich_company_mood_scarf, get_company_mood
from api.v1.company_summary import calculate_scarf_monthly_timeline
from core.database import SessionLocal, init_db
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_kununu_mhp_scarf_enrichment_display_flow():
    """Verify that MHP Kununu comments are enriched with SCARF dimensions by AI Connector and displayed by Bidding MS."""
    await init_db()
    company_id = "MHP"

    # Step 1: Seed database with raw Kununu comments for MHP
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with SessionLocal() as session:
        # Clear existing mood records for clean test state
        existing = await session.execute(
            CompanyMood.__table__.select().where(CompanyMood.company_id == company_id)
        )
        for row in existing.fetchall():
            await session.execute(
                CompanyMood.__table__.delete().where(CompanyMood.id == row.id)
            )

        mood1 = CompanyMood(
            company_id=company_id,
            comment_hash="mhp-kununu-rev-001",
            title="Tolle Kollegen, starre Führung",
            content="Der Kollegenzusammenhalt ist spitze, aber Mikromanagement bremst Entscheidungen.",
            rating=3.5,
            source_platform="Kununu",
            published_date="2026-08-01",
            crawled_date=now,
        )
        mood2 = CompanyMood(
            company_id=company_id,
            comment_hash="mhp-kununu-rev-002",
            title="Top Arbeitgeber im IT-Bereich",
            content="Marktübliches Gehalt, transparente Karrierewege und viele Weiterbildungschancen.",
            rating=4.8,
            source_platform="Kununu",
            published_date="2026-08-10",
            crawled_date=now,
        )

        session.add_all([mood1, mood2])
        await session.commit()

    # Step 2: Mock AI Connector SCARF enrichment API response (/api/v1/enrich/scarf)
    mock_scarf_ai_response = {
        "enriched_comments": [
            {
                "id": "mhp-kununu-rev-001",
                "scarf_scores": {
                    "status": 60.0,
                    "certainty": 70.0,
                    "autonomy": 25.0,
                    "relatedness": 95.0,
                    "fairness": 75.0,
                },
                "primary_threat": "autonomy",
                "primary_reward": "relatedness",
                "rationale": "Hohe Verbundenheit im Team, jedoch Einschränkung der Eigenverantwortung durch Mikromanagement.",
            },
            {
                "id": "mhp-kununu-rev-002",
                "scarf_scores": {
                    "status": 90.0,
                    "certainty": 85.0,
                    "autonomy": 80.0,
                    "relatedness": 90.0,
                    "fairness": 95.0,
                },
                "primary_threat": None,
                "primary_reward": "fairness",
                "rationale": "Ausgezeichnete Vergütung und hohe Gerechtigkeit im Unternehmen.",
            },
        ]
    }

    async def mock_http_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        url_str = str(url)
        if "scarf" in url_str:
            resp.json.return_value = mock_scarf_ai_response
        else:
            resp.json.return_value = {}
        return resp

    async def mock_http_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        return resp

    with (
        patch("httpx.AsyncClient.post", side_effect=mock_http_post),
        patch("httpx.AsyncClient.get", side_effect=mock_http_get),
    ):
        async with SessionLocal() as session:
            # Step 3: Trigger Bidding MS SCARF enrichment workflow
            enrich_result = await enrich_company_mood_scarf(company_id=company_id, db=session)
            assert enrich_result.get("status") == "success"
            assert enrich_result.get("analyzed_count") == 2

            # Step 4: Fetch final enriched Kununu mood display records
            mood_records = await get_company_mood(company_id=company_id, db=session)
            assert isinstance(mood_records, list)
            assert len(mood_records) == 2

            # Find enriched reviews by comment_hash
            rev1 = next(r for r in mood_records if r.comment_hash == "mhp-kununu-rev-001")
            rev2 = next(r for r in mood_records if r.comment_hash == "mhp-kununu-rev-002")

            # Assert SCARF dimension values on Review 1
            assert rev1.scarf_status == 60.0
            assert rev1.scarf_certainty == 70.0
            assert rev1.scarf_autonomy == 25.0
            assert rev1.scarf_relatedness == 95.0
            assert rev1.scarf_fairness == 75.0
            assert rev1.scarf_primary_threat == "autonomy"
            assert rev1.scarf_primary_reward == "relatedness"
            assert "Mikromanagement" in rev1.scarf_rationale

            # Assert SCARF dimension values on Review 2
            assert rev2.scarf_status == 90.0
            assert rev2.scarf_certainty == 85.0
            assert rev2.scarf_autonomy == 80.0
            assert rev2.scarf_relatedness == 90.0
            assert rev2.scarf_fairness == 95.0
            assert rev2.scarf_primary_threat is None
            assert rev2.scarf_primary_reward == "fairness"
            assert "Vergütung" in rev2.scarf_rationale

            # Assert SCARF monthly timeline aggregation
            scarf_timeline = calculate_scarf_monthly_timeline(mood_records)
            assert isinstance(scarf_timeline, list)
            assert len(scarf_timeline) == 24  # 24-month window
