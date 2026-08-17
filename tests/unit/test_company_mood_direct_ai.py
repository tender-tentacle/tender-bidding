from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_company_mood_direct_ai_connector_scraping():
    """Verify that manual_scrape_company_mood calls AI Connector directly, bypassing crawling-app."""
    from api.v1.company_mood import ScrapeMoodRequest, manual_scrape_company_mood

    mock_db = AsyncMock()
    new_mood = CompanyMood(id="1", company_id="MHP Management- und IT-Beratung GmbH", title="Direct AI Review")
    
    res_empty = MagicMock()
    res_empty.scalars.return_value.all.return_value = []
    res_empty.scalars.return_value.first.return_value = None

    res_found = MagicMock()
    res_found.scalars.return_value.all.return_value = [new_mood]
    res_found.scalars.return_value.first.return_value = None

    mock_db.execute.side_effect = lambda *args, **kwargs: res_found if "from bid_company_mood" in str(args[0]).lower() and mock_db.execute.call_count > 3 else res_empty

    mock_ai_resp = MagicMock()
    mock_ai_resp.status_code = 200
    mock_ai_resp.json.return_value = {
        "status": "success",
        "data": {
            "metadata": {
                "overall_score": 4.5,
                "review_count": 100,
                "summary_text": "Great company"
            },
            "comments": [
                {
                    "title": "Direct AI Review",
                    "content": "Excellent culture and management",
                    "rating": 5.0,
                    "published_date": "2026-08-01"
                }
            ],
            "salaries": [],
            "jobs": []
        }
    }

    mock_post = AsyncMock(return_value=mock_ai_resp)

    with patch("httpx.AsyncClient.post", mock_post):
        req = ScrapeMoodRequest(url="https://www.kununu.com/de/mhp-management-und-it-beratung", force=True)
        moods = await manual_scrape_company_mood("MHP Management- und IT-Beratung GmbH", req, mock_db)

        # Assert direct AI Connector endpoint (/api/inference) was called
        called_urls = [str(call[0][0]) for call in mock_post.call_args_list]
        assert any("/api/inference" in url for url in called_urls)
        # Assert crawling-app endpoint was NOT called
        assert not any("scrape/kununu" in url for url in called_urls)

        assert len(moods) == 1
        assert moods[0].title == "Direct AI Review"
