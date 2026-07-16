"""Consumer contract: user-dashboard → bidding (MVP integration).

The dashboard shows bid preparation on the tender detail page. It depends on:
- GET /bids/by-source/{ref} accepting external_id OR enriching UUID, returning
  required_documents[] and key_dates[] (with days_remaining) — 404 when no
  workspace exists, which the dashboard treats as "feature not available".
- GET /health for the availability probe (bidding is an OPTIONAL service; the
  dashboard hides the whole section when this is unreachable).

In-process contract check, same hermetic style as the other pact files.
"""

import pytest
from tests.helpers import api_client

# What the dashboard's BidPreparation component depends on per response.
BID_FIELDS = {"id", "source_ref", "title", "status", "required_documents", "key_dates", "checklist_items", "selection_criteria"}
REQUIRED_DOC_FIELDS = {"document_name", "description", "category", "status", "user_override", "extracted_metadata"}
KEY_DATE_FIELDS = {"kind", "date", "days_remaining"}


@pytest.mark.asyncio
async def test_by_source_honours_dashboard_contract(mocker):
    async with api_client() as client:
        # Arrange a workspace the way the dashboard triggers it: via /bids/enrich.
        tender = {
            "id": "11111111-2222-3333-4444-555555555555",
            "external_id": "PACT-DASH-1",
            "title": "Dashboard Contract Tender",
            "customer": "Stadt Pact",
            "source_system": "Öffentliche Vergabe",
            "assigned_user_id": "u1",
            "document_text": "Referenzen erforderlich. Angebotsfrist beachten.",
        }

        import httpx

        original_get = httpx.AsyncClient.get

        async def mock_get(self, url, *args, **kwargs):
            if "/api/v1/tenders/" in str(url):
                return httpx.Response(200, json=tender, request=httpx.Request("GET", str(url)))
            return await original_get(self, url, *args, **kwargs)

        mocker.patch("httpx.AsyncClient.get", mock_get)
        r = await client.post("/bids/enrich", json={"source_id": tender["id"], "source_kind": "tender"})
        assert r.status_code == 200, r.text

        # Contract: lookup by external_id AND by enriching UUID return the same bid.
        for ref in (tender["external_id"], tender["id"]):
            resp = await client.get(f"/bids/by-source/{ref}")
            assert resp.status_code == 200, f"{ref}: {resp.text}"
            body = resp.json()
            assert set(body.keys()) >= BID_FIELDS
            assert body["source_ref"] == "PACT-DASH-1"
            for doc in body["required_documents"]:
                assert set(doc.keys()) >= REQUIRED_DOC_FIELDS
            assert body["required_documents"], "requirement detection must yield documents"
            for kd in body["key_dates"]:
                assert set(kd.keys()) >= KEY_DATE_FIELDS
            kinds = {kd["kind"] for kd in body["key_dates"]}
            assert {"submission", "questions"} <= kinds


@pytest.mark.asyncio
async def test_unknown_source_is_404_so_dashboard_hides_the_section():
    async with api_client() as client:
        resp = await client.get("/bids/by-source/NEVER-RELAYED")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_probe_for_optional_deployment():
    """The dashboard probes /health to decide whether bidding features exist."""
    import httpx
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "bidding"
