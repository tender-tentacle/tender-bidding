"""
Unit test verifying the 30-day data freshness guard for company mood reviews in tender-bidding.
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_mood import get_company_mood
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_fresh_data_returned_without_scrape():
    """If DB contains reviews younger than 30 days, return cached data without triggering scrape."""
    mock_db = AsyncMock()
    fresh_date = datetime.now(UTC) - timedelta(days=5)

    record = CompanyMood(
        id="test-1",
        company_id="Toll Collect GmbH",
        title="Super Arbeitgeber",
        rating=4.5,
        crawled_date=fresh_date,
    )

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [record]
    mock_db.execute.return_value = mock_result

    with patch("api.v1.company_mood.manual_scrape_company_mood") as mock_scrape:
        records = await get_company_mood("Toll Collect GmbH", db=mock_db)

        assert len(records) == 1
        assert records[0].title == "Super Arbeitgeber"
        mock_scrape.assert_not_called()


@pytest.mark.asyncio
async def test_get_company_mood_never_triggers_automatic_scrape():
    """Verify get_company_mood only reads cached records and NEVER triggers manual_scrape_company_mood automatically."""
    mock_db = AsyncMock()
    old_date = datetime.now(UTC) - timedelta(days=35)

    record = CompanyMood(
        id="test-1",
        company_id="Toll Collect GmbH",
        title="Old Review",
        rating=3.0,
        crawled_date=old_date,
    )

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [record]
    mock_db.execute.return_value = mock_result

    with patch("api.v1.company_mood.manual_scrape_company_mood", new_callable=AsyncMock) as mock_scrape:
        records = await get_company_mood("Toll Collect GmbH", db=mock_db)

        assert len(records) == 1
        assert records[0].title == "Old Review"
        mock_scrape.assert_not_called()


@pytest.mark.asyncio
async def test_delete_company_mood():
    """Verify delete_company_mood executes delete queries and commits transaction."""
    from api.v1.company_mood import delete_company_mood

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 2
    mock_db.execute.return_value = mock_res

    res = await delete_company_mood("Toll Collect GmbH", db=mock_db)

    assert res["status"] == "cleared"
    assert res["company_id"] == "Toll Collect GmbH"
    assert res["deleted_moods"] == 2
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_manual_scrape_requires_valid_kununu_url():
    """Verify manual_scrape_company_mood rejects requests without a valid kununu.com URL with HTTP 400."""
    from api.v1.company_mood import ScrapeMoodRequest, manual_scrape_company_mood
    from fastapi import HTTPException

    mock_db = AsyncMock()

    # 1. Missing URL
    with pytest.raises(HTTPException) as exc_info:
        await manual_scrape_company_mood("Toll Collect GmbH", ScrapeMoodRequest(url=""), db=mock_db)
    assert exc_info.value.status_code == 400
    assert "valid Kununu or Glassdoor URL" in exc_info.value.detail

    # 2. Non-kununu and non-glassdoor URL
    with pytest.raises(HTTPException) as exc_info2:
        await manual_scrape_company_mood("Toll Collect GmbH", ScrapeMoodRequest(url="https://google.com"), db=mock_db)
    assert exc_info2.value.status_code == 400
    assert "valid Kununu or Glassdoor URL" in exc_info2.value.detail

