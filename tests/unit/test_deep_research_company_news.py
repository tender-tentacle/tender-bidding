from unittest.mock import AsyncMock, patch

import pytest
from api.v1.company_news import run_deep_research_company_news


@pytest.mark.asyncio
async def test_run_deep_research_company_news_parsing(mocker):
    """Test that run_deep_research_company_news correctly formats prompt and parses structured JSON output."""
    mock_raw_output = {
        "press_news": [
            {
                "title": "MHP Expands IT Advisory Business in EU",
                "link": "https://news.example.com/mhp-growth",
                "summary": "MHP reports strong revenue growth in automotive IT consulting.",
                "published_date": "2026-08-10",
                "sentiment_score": 85,
                "sentiment_label": "Positiv",
                "sentiment_rationale": "High revenue growth reported",
                "key_topics": ["IT Consulting", "Growth"]
            }
        ],
        "company_blog": [
            {
                "title": "Our Vision for AI in Supply Chain",
                "link": "https://mhp.com/blog/ai-supply-chain",
                "summary": "MHP blog post on AI integration in logistics.",
                "published_date": "2026-08-12",
                "sentiment_score": 90,
                "sentiment_label": "Positiv",
                "sentiment_rationale": "Innovative AI strategy showcase",
                "key_topics": ["AI", "Logistics"]
            }
        ]
    }

    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "data": {
            "raw_output": mock_raw_output
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await run_deep_research_company_news("MHP GmbH")

        assert "press_news" in res
        assert "company_blog" in res
        assert len(res["press_news"]) == 1
        assert len(res["company_blog"]) == 1
        assert res["press_news"][0]["sentiment_score"] == 85
        assert res["company_blog"][0]["sentiment_score"] == 90

        # Verify model_tier sent to AI connector was "deep-research"
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model_tier"] == "deep-research"
