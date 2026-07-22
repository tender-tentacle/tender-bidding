"""Integration tests over the in-process API: relay → workspace → checklist →
documents → comments → deadlines → win/loss, plus optimistic concurrency."""

import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


async def _create_bid(client) -> dict:
    r = await client.post("/internal/bids/relay", json=SAMPLE_RELAY)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_relay_creates_bid_with_checklist_and_is_idempotent():
    async with api_client() as client:
        bid = await _create_bid(client)
        assert bid["portal_key"] == "oeffentliche-vergabe"
        assert bid["driver_user_id"] == "u-driver"

        detail = (await client.get(f"/bids/{bid['id']}")).json()
        kinds = {i["criterion_kind"] for i in detail["checklist_items"]}
        assert kinds == {"formal", "suitability", "award"}
        # Formal gate blocks while formal items are open.
        assert detail["formal_gate"]["ready"] is False
        assert detail["formal_gate"]["formal_open"] > 0
        # Deadlines extracted from the snapshot.
        assert {kd["kind"] for kd in detail["key_dates"]} >= {"submission", "questions"}
        # Lead collaborator = driver.
        assert any(c["role"] == "lead" and c["user_id"] == "u-driver" for c in detail["collaborators"])

        # Idempotent relay: same source_ref returns the same bid.
        again = await _create_bid(client)
        assert again["id"] == bid["id"]
        assert len((await client.get("/bids")).json()) == 1


@pytest.mark.asyncio
async def test_formal_gate_clears_when_formal_items_done():
    async with api_client() as client:
        bid = await _create_bid(client)
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        formal = [i for i in detail["checklist_items"] if i["criterion_kind"] == "formal"]
        for item in formal:
            r = await client.patch(f"/bids/{bid['id']}/checklist/{item['id']}", json={"status": "done"})
            assert r.status_code == 200
        gate = (await client.get(f"/bids/{bid['id']}")).json()["formal_gate"]
        assert gate["ready"] is True and gate["formal_open"] == 0


@pytest.mark.asyncio
async def test_optimistic_concurrency_conflict():
    async with api_client() as client:
        bid = await _create_bid(client)
        v = bid["version"]
        ok = await client.post(f"/bids/{bid['id']}/status", json={"status": "in_progress", "expected_version": v})
        assert ok.status_code == 200
        # Stale write with the old version → 409.
        stale = await client.post(f"/bids/{bid['id']}/status", json={"status": "submitted", "expected_version": v})
        assert stale.status_code == 409


@pytest.mark.asyncio
async def test_win_loss_capture_requires_reason():
    async with api_client() as client:
        bid = await _create_bid(client)
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        v = detail["version"]
        # 'lost' without a reason → 400.
        bad = await client.post(f"/bids/{bid['id']}/status", json={"status": "lost", "expected_version": v})
        assert bad.status_code == 400
        good = await client.post(
            f"/bids/{bid['id']}/status",
            json={"status": "lost", "expected_version": v, "loss_reason": "formal", "loss_note": "missing signature"},
        )
        assert good.status_code == 200
        assert good.json()["loss_reason"] == "formal"


@pytest.mark.asyncio
async def test_document_upload_verifies_and_completes_item():
    async with api_client() as client:
        bid = await _create_bid(client)
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        ref_item = next(i for i in detail["checklist_items"] if i["requirement_type"] == "reference")

        content = b"Reference project: comparable references from the last three years, client Stadt X."
        files = {"file": ("references.txt", io.BytesIO(content), "text/plain")}
        data = {"kind": "reference", "doc_type": "reference_list", "checklist_item_id": ref_item["id"]}
        r = await client.post(f"/bids/{bid['id']}/documents", files=files, data=data)
        assert r.status_code == 201, r.text
        assert r.json()["ai_verification"]["status"] == "matched"

        # The linked checklist item auto-completes on a matched upload.
        after = (await client.get(f"/bids/{bid['id']}")).json()
        assert next(i for i in after["checklist_items"] if i["id"] == ref_item["id"])["status"] == "done"


@pytest.mark.asyncio
async def test_comments_and_activity_log():
    async with api_client() as client:
        bid = await _create_bid(client)
        c = await client.post(
            f"/bids/{bid['id']}/comments",
            json={"target_type": "bid", "body": "Kickoff scheduled"},
            headers={"X-User-ID": "u2"},
        )
        assert c.status_code == 201
        assert len((await client.get(f"/bids/{bid['id']}/comments")).json()) == 1

        # Activity log recorded bid.created + comment.added (append-only audit).
        actions = {a["action"] for a in (await client.get(f"/bids/{bid['id']}/activity")).json()}
        assert {"bid.created", "comment.added"} <= actions


@pytest.mark.asyncio
async def test_regenerate_is_additive():
    async with api_client() as client:
        bid = await _create_bid(client)
        before = (await client.get(f"/bids/{bid['id']}")).json()
        # Mark one item done, then regenerate — human state must survive.
        item = before["checklist_items"][0]
        await client.patch(f"/bids/{bid['id']}/checklist/{item['id']}", json={"status": "done"})
        r = await client.post(f"/bids/{bid['id']}/regenerate", json={})
        assert r.status_code == 200
        after = r.json()
        assert next(i for i in after["checklist_items"] if i["id"] == item["id"])["status"] == "done"


@pytest.mark.asyncio
async def test_portal_guide_and_deadlines_endpoints():
    async with api_client() as client:
        bid = await _create_bid(client)
        guide = (await client.get(f"/bids/{bid['id']}/portal-guide")).json()
        assert guide["portal_key"] == "oeffentliche-vergabe"
        assert guide["registration_steps"]
        dls = (await client.get(f"/bids/{bid['id']}/deadlines")).json()
        assert all("days_remaining" in d for d in dls)


@pytest.mark.asyncio
async def test_required_document_upload_and_override(mocker):
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
        print("BID SERIALIZED:", bid)
        get_res = await client.get(f"/bids/{bid['id']}")
        print("GET DETAIL STATUS:", get_res.status_code)
        print("GET DETAIL BODY:", get_res.json())
        detail = get_res.json()

        # Verify required document list exists and default states
        assert len(detail["required_documents"]) > 0
        rd = detail["required_documents"][0]
        assert rd["status"] == "open"
        assert rd["user_override"] is False

        # 1. Upload a file for this specific required document
        content = b"Aktueller Auszug aus dem Handelsregister."
        files = {"file": ("handelsregister.txt", io.BytesIO(content), "text/plain")}
        r = await client.post(
            f"/bids/{bid['id']}/required-documents/{rd['id']}/upload",
            files=files,
            headers={"X-User-ID": "test-uploader@email.com", "X-User-Name": "Uploader Name"},
        )
        assert r.status_code == 201
        res = r.json()
        assert res["uploaded_filename"] == "handelsregister.txt"
        assert res["uploaded_by"] == "test-uploader@email.com"

        # Verify state is updated to done due to matching text
        detail_after = (await client.get(f"/bids/{bid['id']}")).json()
        rd_after = next(d for d in detail_after["required_documents"] if d["id"] == rd["id"])
        assert rd_after["status"] == "done"

        # 2. Human override status to open
        over_resp = await client.post(
            f"/bids/{bid['id']}/required-documents/{rd['id']}/override", json={"status": "open"}
        )
        assert over_resp.status_code == 200
        assert over_resp.json()["status"] == "open"
        assert over_resp.json()["user_override"] is True
