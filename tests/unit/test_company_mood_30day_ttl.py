from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_company_mood_30day_ttl_override_behavior():
    """Verify company mood overrides cached data when older than 30 days."""
    from api.v1.company_mood import ScrapeMoodRequest, manual_scrape_company_mood

    mock_db = AsyncMock()

    # Create mock result for query 1 (30-day cache check -> empty)
    res1 = MagicMock()
    res1.scalars.return_value.all.return_value = []

    # Create mock result for query 2 (check if comment_hash exists -> None)
    res2 = MagicMock()
    res2.scalars.return_value.first.return_value = None

    # Create mock result for query 3 (final return -> returns newly added mood)
    new_mood = CompanyMood(
        id="new-1",
        company_id="HOCH Health Ostschweiz",
        comment_hash="newhash1",
        title="Neuer Kommentar",
        content="Super Arbeitsumfeld",
        rating=4.0,
        published_date="2026-06-01",
        overall_score=3.3,
        score_career=3.2,
        score_culture=3.4,
        score_environment=3.4,
        score_diversity=3.7,
        review_count=435,
        summary_text="Seit 2009 haben 435...",
        industry_score=3.6,
    )
    res3 = MagicMock()
    res3.scalars.return_value.all.return_value = [new_mood]

    mock_db.execute.side_effect = [res1, res1, res2, res3]

    mock_crawling_resp = MagicMock()
    mock_crawling_resp.status_code = 200
    mock_crawling_resp.json.return_value = {
        "metadata": {
            "overall_score": 3.3,
            "score_career": 3.2,
            "score_culture": 3.4,
            "score_environment": 3.4,
            "score_diversity": 3.7,
            "review_count": 435,
            "industry_score": 3.6,
            "summary_text": "Seit 2009 haben 435 Mitarbeiter:innen... 3,3 Punkten bewertet.",
        },
        "comments": [
            {
                "comment_hash": "newhash1",
                "title": "Neuer Kommentar",
                "content": "Super Arbeitsumfeld",
                "rating": 4.0,
                "published_date": "2026-06-01",
            }
        ],
    }

    with (
        patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_crawling_resp)),
        patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(status_code=404))),
    ):
        res = await manual_scrape_company_mood("HOCH Health Ostschweiz", ScrapeMoodRequest(url="https://www.kununu.com/de/hoch-health-ostschweiz", force=True), mock_db)

        assert mock_db.add.call_count == 1
        added_mood = mock_db.add.call_args[0][0]
        assert added_mood.overall_score == 3.3
        assert added_mood.score_career == 3.2
        assert added_mood.score_culture == 3.4
        assert added_mood.score_environment == 3.4
        assert added_mood.score_diversity == 3.7
        assert added_mood.review_count == 435
        assert added_mood.industry_score == 3.6
        assert len(res) == 1
