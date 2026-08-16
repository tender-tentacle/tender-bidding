import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.asyncio
async def test_enrich_scarf_integration():
    """
    Integration test verifying that /company/{company_id}/mood/enrich-scarf
    enriches comments and returns structured response.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/company/MHP/mood/enrich-scarf")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "total_comments" in data or "analyzed_count" in data or "moods" in data
