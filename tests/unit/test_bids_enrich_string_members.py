from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.asyncio
async def test_bids_enrich_with_string_members_does_not_crash():
    """Verify POST /api/v1/bids/enrich handles members as strings or non-dicts without throwing 500 TypeError."""
    mock_tender_data = {
        "id": "group-test-123",
        "title": "Group Tender Test",
        "customer": "Stadt Köln",
        "members": ["attachments", "tender-id-1"],  # String containing 'attachments'
        "attachments": []
    }

    with patch("api.v1.bids._fetch_tender_data", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_tender_data

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/bids/enrich",
                json={"source_id": "group-test-123", "source_kind": "group"}
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            data = res.json()
            assert data["id"] is not None
