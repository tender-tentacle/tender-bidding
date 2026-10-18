"""Unit test: Verify auto-sync of moods from market-research and SCARF enrichment when DB has no records."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_mood import auto_sync_moods_from_market_research


@pytest.mark.asyncio
async def test_auto_sync_moods_from_market_research():
    """Verify that auto_sync_moods_from_market_research fetches reviews from market research and creates CompanyMood entries."""
    db_mock = AsyncMock()
    # Mock existing check to return None (not found)
    empty_scalars = MagicMock()
    empty_scalars.first.return_value = None
    res_mock = MagicMock()
    res_mock.scalars.return_value = empty_scalars
    db_mock.execute.return_value = res_mock

    mock_market_research_response = {
        "kununu": {
            "metadata": {"overall_score": 3.8, "review_count": 2},
            "comments": [
                {
                    "title": "Tolle Unternehmenskultur",
                    "pros": "Gutes Team, faire Führung",
                    "cons": "Hohe Auslastung",
                    "rating": 4.0,
                    "published_date": "2026-07-01",
                },
                {
                    "title": "Interessante Aufgaben",
                    "pros": "Moderne Tech, flexible Arbeitszeiten",
                    "cons": "Wenig Parkplätze",
                    "rating": 3.5,
                    "published_date": "2026-08-01",
                },
            ],
        },
        "glassdoor": {},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_market_research_response

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        created = await auto_sync_moods_from_market_research("MHP", db_mock)

    assert len(created) == 2
    assert created[0].company_id == "MHP"
    assert created[0].rating == 4.0
    assert "Gutes Team" in (created[0].content or "")
    assert created[1].rating == 3.5
    assert db_mock.commit.called

