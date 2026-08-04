import httpx
import pytest
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_enrich_group_requirements_resilient_to_raw_errors(mocker):
    """Verify group requirements extraction succeeds even if member raw text endpoint fails or member is missing raw text."""
    group_id = "b519ded5-c9a8-4980-8ee6-a201f58dd187"
    
    mock_group_response = {
        "id": group_id,
        "title": "Rahmenvereinbarung Projektplattform",
        "customer": "Flughafen München GmbH",
        "members": [
            {
                "id": "member-1",
                "title": "Lot 1 Platform",
                "description": "Cloud base platform",
                "attachments": [{"title": "Notice.pdf", "url": "https://example.com/notice.pdf"}]
            },
            {
                "id": "member-2",
                "title": "Lot 2 Support",
                "description": "24/7 Operations",
                "attachments": None
            }
        ]
    }

    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        url_str = str(url)
        if f"/api/v1/tenders/groups/{group_id}" in url_str:
            resp = httpx.Response(200, json=mock_group_response)
            return resp
        if "/raw" in url_str:
            # Simulate exception or failure on raw text endpoint for a member
            raise httpx.RequestError("Raw endpoint unreachable")
        return await original_get(self, url, *args, **kwargs)

    mocker.patch("httpx.AsyncClient.get", mock_get)

    async with api_client() as client:
        resp = await client.post(
            "/bids/enrich",
            json={"source_id": group_id, "source_kind": "group"}
        )
        assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["source_ref"] == group_id
        assert data["source_kind"] == "group"
        assert len(data["required_documents"]) > 0
