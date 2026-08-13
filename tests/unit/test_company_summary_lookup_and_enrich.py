from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_summary import get_company_summary
from models.bid import Bid


@pytest.mark.asyncio
async def test_get_company_summary_lookup_by_source_ref_or_id():
    """Verify get_company_summary finds bid by id, source_ref, or enriching_id."""
    mock_db = AsyncMock()
    mock_res = MagicMock()

    dummy_bid = Bid(
        id="9bd44ff2-f620-46e0-ad83-6b2720f70a70",
        source_ref="DP31-202600017",
        enriching_id="d95364b1-88bd-4e9f-9825-603e95f6f192",
        title="Test Workspace",
        company_summary={"company_name": "Hamburg LIG", "status": "ok"},
    )

    mock_res.scalar_one_or_none.return_value = dummy_bid
    mock_res.scalars.return_value.first.return_value = dummy_bid
    mock_db.execute.return_value = mock_res

    # Query using tender UUID
    result = await get_company_summary("9bd44ff2-f620-46e0-ad83-6b2720f70a70", mock_db)
    assert result == {"company_name": "Hamburg LIG", "status": "ok"}

    # Assert query used or_ clause across id, source_ref, and enriching_id
    call_stmt = mock_db.execute.call_args[0][0]
    compiled_stmt = str(call_stmt)
    assert "bid.id =" in compiled_stmt or "bid.source_ref =" in compiled_stmt or "bid.enriching_id =" in compiled_stmt


@pytest.mark.asyncio
async def test_get_company_summary_auto_generates_when_missing():
    """Verify get_company_summary auto-extracts summary on-the-fly when not pre-existing (preventing 404)."""
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_res

    with patch("api.v1.company_summary.extract_company_summary", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = {"company_name": "Ziel-Auftraggeber", "auto_generated": True}

        res = await get_company_summary("9bd44ff2-f620-46e0-ad83-6b2720f70a70", mock_db)
        assert res == {"company_name": "Ziel-Auftraggeber", "auto_generated": True}
        assert mock_extract.call_count == 1
