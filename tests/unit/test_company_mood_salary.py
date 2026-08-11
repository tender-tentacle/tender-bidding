from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_company_mood_persists_and_returns_salary_fields():
    """Verify company mood API and ORM model process salary satisfaction and benefits metadata."""
    from api.v1.company_mood import ScrapeMoodRequest, manual_scrape_company_mood

    mock_db = AsyncMock()

    # Query 1: 30-day cache check -> returns empty list
    res1 = MagicMock()
    res1.scalars.return_value.all.return_value = []

    # Query 2: existing comment_hash check -> returns None
    res2 = MagicMock()
    res2.scalars.return_value.first.return_value = None

    # Query 3: final return -> returns mood with salary fields
    new_mood = CompanyMood(
        id="mood-giz-1",
        company_id="GIZ",
        comment_hash="gizhash1",
        title="Guter Arbeitgeber",
        content="Gutes Gehalt",
        rating=4.0,
        overall_score=4.0,
        salary_satisfaction_percentage=76.0,
        salary_satisfaction_text="76% sind mit ihren Gehältern zufrieden (basierend auf 483 Bewertungen)",
        salary_satisfaction_review_count=483,
        salary_benefits_score=4.0,
        salary_benefits_review_count=483,
    )
    res3 = MagicMock()
    res3.scalars.return_value.all.return_value = [new_mood]

    mock_db.execute.side_effect = [res1, res2, res3]

    mock_crawling_resp = MagicMock()
    mock_crawling_resp.status_code = 200
    mock_crawling_resp.json.return_value = {
        "metadata": {
            "overall_score": 4.0,
            "salary_satisfaction_percentage": 76.0,
            "salary_satisfaction_text": "76% sind mit ihren Gehältern zufrieden (basierend auf 483 Bewertungen)",
            "salary_satisfaction_review_count": 483,
            "salary_benefits_score": 4.0,
            "salary_benefits_review_count": 483,
        },
        "comments": [
            {
                "comment_hash": "gizhash1",
                "title": "Guter Arbeitgeber",
                "content": "Gutes Gehalt",
                "rating": 4.0,
                "published_date": "2026-08-01",
            }
        ],
    }

    async def mock_post(url, **kwargs):
        if "glassdoor" in url:
            resp = MagicMock()
            resp.status_code = 404
            return resp
        return mock_crawling_resp

    with (
        patch("httpx.AsyncClient.post", AsyncMock(side_effect=mock_post)),
        patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(status_code=404))),
    ):
        res = await manual_scrape_company_mood("GIZ", ScrapeMoodRequest(url="https://www.kununu.com/de/giz", force=True), mock_db)

        assert mock_db.add.call_count == 1
        added_mood = mock_db.add.call_args[0][0]
        assert added_mood.salary_satisfaction_percentage == 76.0
        assert added_mood.salary_satisfaction_review_count == 483
        assert added_mood.salary_benefits_score == 4.0
        assert added_mood.salary_benefits_review_count == 483
        assert "76%" in added_mood.salary_satisfaction_text
        assert len(res) == 1
