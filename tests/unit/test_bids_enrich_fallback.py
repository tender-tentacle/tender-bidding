from unittest.mock import AsyncMock, patch

import pytest
from models.bid import Bid


@pytest.mark.asyncio
async def test_enrich_bid_requirements_ai_fallback():
    """Verify that when AI client fails or encounters rate limits during bidding requirements enrichment,
    the endpoint logs a warning and returns 200 with fallback empty lists instead of crashing with 500.
    """
    from api.v1.bids import enrich_bid_requirements
    from schemas import EnrichBiddingPayload

    fake_tender_data = {
        "id": "02ff5d0f-81a0-4dab-9a47-b67fd31d728a",
        "title": "Charité ITSM ESM Platform",
        "customer": "Charité - Universitätsmedizin Berlin",
        "external_id": "ext-charite-123",
        "source_system": "TED",
        "attachments": [],
    }

    mock_db = AsyncMock()
    mock_request = AsyncMock()
    mock_request.state.user = {"sub": "test.user@local"}

    mock_ai = AsyncMock()
    mock_ai.extract_required_documents.side_effect = RuntimeError("500: Rate limit exceeded")
    mock_ai.extract_bidding_deadlines.side_effect = RuntimeError("500: Rate limit exceeded")

    mock_bid = Bid(
        id="bid-123",
        source_ref="02ff5d0f-81a0-4dab-9a47-b67fd31d728a",
        source_kind="group",
        title="Charité ITSM ESM Platform",
        customer="Charité - Universitätsmedizin Berlin",
        status="DRAFT",
        version=1,
        required_documents=[],
        key_dates=[],
        collaborators=[],
        matched_labels=[],
        matched_sectors=[],
        matched_services=[],
        matched_people=[],
        matched_campaigns=[],
        matched_trends=[],
        matched_practices=[],
        matched_clusters=[],
        matched_ressorts=[],
        matched_horizontals=[],
        classification_matches=[],
    )

    with (
        patch("api.v1.bids._fetch_tender_data", AsyncMock(return_value=fake_tender_data)),
        patch("services.bid_service.get_by_source_ref", AsyncMock(return_value=mock_bid)),
        patch("core.ai_client.get_ai_client", return_value=mock_ai),
        patch("api.v1.bids._create_required_documents", return_value=None),
        patch("api.v1.bids._create_key_dates", return_value=None),
        patch("services.activity.record", return_value=None),
    ):
        payload = EnrichBiddingPayload(source_id="02ff5d0f-81a0-4dab-9a47-b67fd31d728a", source_kind="group")
        res = await enrich_bid_requirements(payload, mock_request, mock_db)

        assert res.id == "bid-123"
        assert res.version == 2
