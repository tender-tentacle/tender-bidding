"""Integration tests for the Bidding Requirements enrichment and by-source resolution workflows."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_enrich_tender_success(mocker):
    # Mock the HTTP call to tender-enriching
    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json = lambda: {
        "id": "11111111-2222-3333-4444-555555555555",
        "external_id": "EXT-TEST-123",
        "title": "Cloud Platform Services",
        "customer": "Stadt Musterstadt",
        "source_system": "Öffentliche Vergabe",
        "assigned_user_id": "user-456"
    }

    # Intercept only external calls to enriching service
    original_get = httpx.AsyncClient.get
    async def mock_get(self, url, *args, **kwargs):
        if "enriching" in str(url):
            return mock_response
        return await original_get(self, url, *args, **kwargs)

    mocker.patch("httpx.AsyncClient.get", mock_get)

    async with api_client() as client:
        # Trigger enrichment
        resp = await client.post("/bids/enrich", json={
            "source_id": "11111111-2222-3333-4444-555555555555",
            "source_kind": "tender"
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        
        # Check bid was created with external_id as source_ref
        assert data["source_ref"] == "EXT-TEST-123"
        assert data["title"] == "Cloud Platform Services"
        assert data["customer"] == "Stadt Musterstadt"
        
        # Check required documents are populated
        assert len(data["required_documents"]) > 0
        doc_names = [d["document_name"] for d in data["required_documents"]]
        assert "Handelsregisterauszug" in doc_names
        
        # Check deadlines are populated
        assert len(data["key_dates"]) > 0
        kinds = {kd["kind"] for kd in data["key_dates"]}
        assert "submission" in kinds
        assert "questions" in kinds
        
        # Verify it can be retrieved by UUID using the by-source fallback logic
        get_resp = await client.get("/bids/by-source/11111111-2222-3333-4444-555555555555")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == data["id"]


@pytest.mark.asyncio
async def test_enrich_group_success(mocker):
    # Mock calls for group and members
    original_get = httpx.AsyncClient.get
    async def mock_get(self, url, *args, **kwargs):
        if "enriching" in str(url):
            resp = mocker.MagicMock(spec=httpx.Response)
            resp.status_code = 200
            if "/groups/" in str(url):
                resp.json = lambda: {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "title": "Group Services",
                    "customer": "Stadt Group",
                    "members": [{"id": "member-uuid-1", "title": "Member 1"}, {"id": "member-uuid-2", "title": "Member 2"}]
                }
            elif "/raw" in str(url):
                resp.json = lambda: {"document_text": "Requirements document text."}
            else:
                resp.json = lambda: {"title": "Member Detail"}
            return resp
        return await original_get(self, url, *args, **kwargs)

    mocker.patch("httpx.AsyncClient.get", mock_get)

    async with api_client() as client:
        resp = await client.post("/bids/enrich", json={
            "source_id": "22222222-2222-2222-2222-222222222222",
            "source_kind": "group"
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        
        assert data["source_ref"] == "22222222-2222-2222-2222-222222222222"
        assert data["source_kind"] == "group"
        assert len(data["required_documents"]) > 0


@pytest.mark.asyncio
async def test_enrich_service_unavailable(mocker):
    # Mock Enriching service being down / throwing error
    original_get = httpx.AsyncClient.get
    async def mock_get(self, url, *args, **kwargs):
        if "enriching" in str(url):
            raise httpx.RequestError("Enriching down")
        return await original_get(self, url, *args, **kwargs)
        
    mocker.patch("httpx.AsyncClient.get", mock_get)
    
    async with api_client() as client:
        resp = await client.post("/bids/enrich", json={
            "source_id": "11111111-2222-3333-4444-555555555555",
            "source_kind": "tender"
        })
        assert resp.status_code == 503
        assert "unreachable" in resp.json()["detail"]
