import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.database import engine, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from api.v1.bids import enrich_bid_requirements, get_bid_by_source, _fetch_tender_data
from api.v1.company_summary import extract_company_summary, get_company_summary
from schemas import EnrichBiddingPayload
from models.bid import Bid, RequiredDocument, KeyDate


@pytest.mark.asyncio
async def test_enrich_bid_requirements_loads_relationships_without_500():
    """
    Test that POST /api/v1/bids/enrich uses _load(db, bid.id) to prevent
    MissingGreenlet 500 error when returning BidDetail after db.commit().
    """
    bid_id = "63ca6cd0-728e-47cd-8f28-17f0309607b7"
    
    mock_tender_data = {
        "id": bid_id,
        "external_id": bid_id,
        "title": "Test Tender for Resilient Enrich",
        "customer": "Test Buyer",
        "source_system": "TED",
        "assigned_user_id": "user-123",
        "attachments": []
    }

    mock_request = MagicMock()
    mock_request.headers.get.return_value = "user-123"

    async with AsyncSession(engine) as db:
        with patch("api.v1.bids._fetch_tender_data", new=AsyncMock(return_value=mock_tender_data)), \
             patch("core.ai_client.MockAIClient.extract_required_documents", new=AsyncMock(return_value=[
                 {
                     "id": "doc-1",
                     "document_name": "Eignungsnachweis",
                     "description": "Nachweis der Fachkunde",
                     "category": "suitability",
                     "short_summary": "Fachkunde",
                     "quote_original": "Par 122 GWB",
                     "source_doc_name": "notice",
                     "is_mandatory": True
                 }
             ])), \
             patch("core.ai_client.MockAIClient.extract_bidding_deadlines", new=AsyncMock(return_value=[
                 {
                     "kind": "submission",
                     "date": "2026-09-01T12:00:00Z",
                     "source_link": "https://example.com"
                 }
             ])):

            payload = EnrichBiddingPayload(source_id=bid_id, source_kind="tender")
            res = await enrich_bid_requirements(payload, mock_request, db)
            assert res.id is not None
            assert len(res.required_documents) == 1
            assert len(res.key_dates) == 1


@pytest.mark.asyncio
async def test_get_bid_by_source_auto_initializes_provisional_when_not_found():
    """
    Test that GET /api/v1/bids/by-source/{source_ref} auto-initializes a provisional bid
    instead of throwing 404 when tender-enriching returns non-200.
    """
    source_ref = "unknown-tender-uuid-9999"

    async with AsyncSession(engine) as db:
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=404))):
            res = await get_bid_by_source(source_ref, db)
            assert res.source_ref == source_ref
            assert res.status == "exploring"


@pytest.mark.asyncio
async def test_fetch_tender_data_fallback_group_and_placeholder():
    """
    Test that _fetch_tender_data falls back to group endpoint and default payload on 404.
    """
    source_id = "group-or-unknown-uuid"
    
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=404))):
        data = await _fetch_tender_data(source_id, "tender")
        assert data["id"] == source_id
        assert data["customer"] == "Ziel-Auftraggeber"


@pytest.mark.asyncio
async def test_extract_company_summary_resolves_group_customer():
    """
    Test that extract_company_summary checks both tender and group endpoints when resolving buyer.
    """
    bid_id = "group-summary-uuid"

    async with AsyncSession(engine) as db:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"customer": "Stadt Köln"}

        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
            data = await extract_company_summary(bid_id, db=db)
            assert data["company_name"] == "Stadt Köln"
