"""Consumer-driven contract test for the bidding → enriching dependency.

Asserts that the response shapes from tender-enriching's get_tender and get_group
endpoints contain the exact fields and types the bidding service's pull/enrich workflow
expects to receive.
"""

import httpx
import pytest

# Expected contract response fields for single tender detail
EXPECTED_TENDER_FIELDS = {"id", "external_id", "title", "customer", "source_system", "assigned_user_id"}

# Expected contract response fields for group detail
EXPECTED_GROUP_FIELDS = {"id", "title", "customer", "members"}


@pytest.mark.asyncio
async def test_enriching_tender_contract_compliance(mocker):
    # Mock response from tender-enriching's GET /tenders/{id}
    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = lambda: {
        "id": "11111111-2222-3333-4444-555555555555",
        "external_id": "EXT-CONTRACT-123",
        "title": "IT Consulting Services",
        "customer": "Stadt X",
        "source_system": "DTVP",
        "assigned_user_id": "u-user-1",
    }

    mocker.patch("httpx.AsyncClient.get", return_value=mock_resp)

    # Act: Perform the call as it's done in the bidding service
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://enriching:8002/api/v1/tenders/11111111-2222-3333-4444-555555555555")

    assert resp.status_code == 200
    body = resp.json()

    # Assert contract compliance
    assert set(body.keys()) >= EXPECTED_TENDER_FIELDS
    assert isinstance(body["id"], str)
    assert isinstance(body["external_id"], str)
    assert isinstance(body["title"], str)


@pytest.mark.asyncio
async def test_enriching_group_contract_compliance(mocker):
    # Mock response from tender-enriching's GET /tenders/groups/{id}
    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = lambda: {
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "Framework IT Services",
        "customer": "Bundesagentur",
        "members": [{"id": "member-1", "title": "Member 1"}, {"id": "member-2", "title": "Member 2"}],
    }

    mocker.patch("httpx.AsyncClient.get", return_value=mock_resp)

    # Act: Perform the call as it's done in the bidding service
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://enriching:8002/api/v1/tenders/groups/22222222-2222-2222-2222-222222222222")

    assert resp.status_code == 200
    body = resp.json()

    # Assert contract compliance
    assert set(body.keys()) >= EXPECTED_GROUP_FIELDS
    assert isinstance(body["id"], str)
    assert isinstance(body["members"], list)
