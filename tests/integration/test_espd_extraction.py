import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


async def _create_bid(client) -> dict:
    r = await client.post("/internal/bids/relay", json=SAMPLE_RELAY)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_espd_extraction_on_upload(mocker):
    # Mock enriching HTTP call
    import httpx

    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json = lambda: {
        "id": "11111111-2222-3333-4444-555555555555",
        "external_id": "LIFE-TEST-123",
        "title": "Cloud Platform Services",
        "customer": "Stadt Musterstadt",
        "source_system": "Öffentliche Vergabe",
        "assigned_user_id": "user-456",
    }
    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        if "enriching" in str(url):
            return mock_response
        return await original_get(self, url, *args, **kwargs)

    mocker.patch("httpx.AsyncClient.get", mock_get)

    async with api_client() as client:
        # Enrich the bid first, which creates bid + populates required_documents
        enrich_resp = await client.post(
            "/bids/enrich", json={"source_id": "11111111-2222-3333-4444-555555555555", "source_kind": "tender"}
        )
        assert enrich_resp.status_code == 200
        bid = enrich_resp.json()

        get_res = await client.get(f"/bids/{bid['id']}")
        detail = get_res.json()

        assert len(detail["required_documents"]) > 0
        rd = detail["required_documents"][0]

        # Upload a file
        content = b"Mock document content that proves the requirement."
        files = {"file": ("document.pdf", io.BytesIO(content), "application/pdf")}
        r = await client.post(
            f"/bids/{bid['id']}/required-documents/{rd['id']}/upload",
            files=files,
            headers={"X-User-ID": "test@user.com"},
        )
        assert r.status_code == 201

        # Verify the extraction
        res = r.json()
        assert res["extracted_metadata"] is not None
        assert res["extracted_metadata"]["project_title"] == "Mock Project"
        assert res["extracted_metadata"]["person_name"] == "Max Mustermann"
