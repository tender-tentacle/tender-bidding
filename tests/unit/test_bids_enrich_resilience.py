"""
Resilience and edge-case unit tests for /api/v1/bids/enrich endpoint
=====================================================================
Tests that string lots, non-dict raw responses, and long key-date kinds
are handled safely without triggering 500 Internal Server Errors.
"""

from unittest.mock import AsyncMock, patch

import pytest
from models.bid import Bid


@pytest.mark.asyncio
async def test_enrich_bid_requirements_string_lots_and_non_dict_raw_member():
    """Verify that when tender_data contains string lots and raw member responses are non-dict/None,
    enrich_bid_requirements completes with 200 instead of crashing with 500.
    """
    from api.v1.bids import enrich_bid_requirements
    from schemas import EnrichBiddingPayload

    fake_group_data = {
        "id": "d95364b1-88bd-4e9f-9825-603e95f6f192",
        "title": "Group Tender Test",
        "customer": "Bundesministerium des Innern",
        "source_system": "Group",
        "lots": ["Lot 1", "Lot 2"],  # List of strings instead of dicts
        "members": [
            "tender-member-id-1",
            {"id": "tender-member-id-2", "title": "Member 2", "description": "Desc"}
        ],
        "attachments": [],
    }

    mock_db = AsyncMock()
    mock_request = AsyncMock()
    mock_request.headers.get.return_value = "user-123"

    mock_ai = AsyncMock()
    mock_ai.extract_required_documents.return_value = [
        {
            "document_name": "Standard ISO Cert",
            "description": ["Must be ISO 27001 certified", "Or equivalent"],  # Non-string list
            "category": "suitability",
            "is_mandatory": True,
        }
    ]
    mock_ai.extract_bidding_deadlines.return_value = [
        {
            "date": "2026-09-01T12:00:00Z",
            "kind": "submission_deadline_extended_extra_long_kind_name",  # > 20 chars
            "source_link": "https://example.com/notice"
        }
    ]

    mock_bid = Bid(
        id="bid-group-123",
        source_ref="d95364b1-88bd-4e9f-9825-603e95f6f192",
        source_kind="group",
        title="Group Tender Test",
        customer="Bundesministerium des Innern",
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
        patch("api.v1.bids._fetch_tender_data", AsyncMock(return_value=fake_group_data)),
        patch("services.bid_service.get_by_source_ref", AsyncMock(return_value=mock_bid)),
        patch("core.ai_client.get_ai_client", return_value=mock_ai),
        patch("services.activity.record", return_value=None),
    ):
        payload = EnrichBiddingPayload(source_id="d95364b1-88bd-4e9f-9825-603e95f6f192", source_kind="group")
        res = await enrich_bid_requirements(payload, mock_request, mock_db)

        assert res.id == "bid-group-123"
        assert res.version == 2
