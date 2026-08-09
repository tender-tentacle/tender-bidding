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
async def test_stale_data_triggers_scrape():
    """If DB records are older than 30 days, trigger manual_scrape_company_mood."""
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
        mock_scrape.return_value = [record]

        records = await get_company_mood("Toll Collect GmbH", db=mock_db)

        mock_scrape.assert_called_once()


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
