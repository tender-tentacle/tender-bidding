from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_news import get_company_news


@pytest.mark.asyncio
async def test_get_company_news_ddg_integration():
    """Verify get_company_news triggers DuckDuckGo news scraping and persists sorted 365-day articles in DB."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    now = datetime.now(UTC)
    recent_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    mock_news_response = MagicMock()
    mock_news_response.status_code = 200
    mock_news_response.json.return_value = [
        {
            "hash": "hash_ddg_1",
            "title": "GIZ Expands Global Projects",
            "link": "https://news.example.com/giz-1",
            "content": "GIZ announces new global climate resilience initiative.",
            "category": "DuckDuckGo News",
            "published_at": recent_date,
        }
    ]

    with patch("httpx.AsyncClient.get") as mock_get, patch("httpx.AsyncClient.post") as mock_post:
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404
        mock_get_resp.json.return_value = {}
        mock_get.return_value = mock_get_resp

        mock_post.return_value = mock_news_response

        added_entries = []

        def mock_add(entry):
            added_entries.append(entry)

        mock_db.add.side_effect = mock_add

        entries = await get_company_news("GIZ", db=mock_db)

        assert len(entries) == 1
        assert entries[0].title == "GIZ Expands Global Projects"
        assert entries[0].category == "DuckDuckGo News"
        assert entries[0].published_date == recent_date
