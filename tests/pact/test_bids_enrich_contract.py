"""Consumer-driven contract test for enriching -> bidding /api/v1/bids/enrich endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from tests.helpers import api_client

ENRICH_REQUEST_PAYLOAD = {
    "source_id": "PACT-ENRICH-SRC-1",
    "source_kind": "tender",
}

EXPECTED_ENRICH_RESPONSE_FIELDS = {"id", "source_ref", "title", "key_dates", "required_documents"}


@pytest.mark.asyncio
async def test_bids_enrich_contract_honored_by_provider():
    mock_tender_data = {
        "external_id": "PACT-ENRICH-SRC-1",
        "title": "Cloud Migration Tender",
        "customer": "Ministry of Digitalization",
        "source_system": "TED",
        "document_text": "Required documents: Security Clearance ISO 27001",
    }

    mock_docs = [
        {"title": "Security Clearance", "category": "Legal", "description": "ISO 27001 certificate"}
    ]
    mock_dates = [
        {"kind": "Submission Deadline", "date": "2026-09-15T12:00:00Z"}
    ]

    with patch("api.v1.bids._fetch_tender_data", AsyncMock(return_value=mock_tender_data)), \
         patch("core.ai_client.AIClient.extract_required_documents", AsyncMock(return_value=mock_docs)), \
         patch("core.ai_client.AIClient.extract_bidding_deadlines", AsyncMock(return_value=mock_dates)):

        async with api_client() as client:
            resp = await client.post("/bids/enrich", json=ENRICH_REQUEST_PAYLOAD)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body.keys()) >= EXPECTED_ENRICH_RESPONSE_FIELDS
            assert body["source_ref"] == "PACT-ENRICH-SRC-1"
            assert isinstance(body["required_documents"], list)
            assert isinstance(body["key_dates"], list)

