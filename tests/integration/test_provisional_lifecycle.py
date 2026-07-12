"""Integration tests for FEAT-051: the "interesting" trigger lifecycle.

interesting → provisional relay → exploring workspace
bid         → committed relay   → promotion to draft (analysis kept)
no_bid      → discard           → archived, but ONLY while exploring
"""

import pytest
from tests.helpers import SAMPLE_RELAY, api_client

PROVISIONAL = dict(SAMPLE_RELAY, source_ref="PROV-1", provisional=True)


@pytest.mark.asyncio
async def test_provisional_relay_creates_exploring_workspace():
    async with api_client() as client:
        r = await client.post("/internal/bids/relay", json=PROVISIONAL)
        assert r.status_code == 200, r.text
        bid = r.json()
        assert bid["status"] == "exploring"

        # The analysis (checklist, deadlines) is already there — that is the point.
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        assert detail["checklist_items"], "bidding enrichment must run at the interesting stage"
        assert detail["key_dates"]

        # Recommendation works on a provisional workspace too.
        reco = (await client.get(f"/bids/{bid['id']}/recommendation")).json()
        assert reco["recommendation"] in ("bid", "no_bid", "review")


@pytest.mark.asyncio
async def test_provisional_relay_is_idempotent():
    async with api_client() as client:
        first = (await client.post("/internal/bids/relay", json=PROVISIONAL)).json()
        second = (await client.post("/internal/bids/relay", json=PROVISIONAL)).json()
        assert first["id"] == second["id"]
        assert second["status"] == "exploring"


@pytest.mark.asyncio
async def test_committed_relay_promotes_exploring_to_draft():
    async with api_client() as client:
        provisional = dict(SAMPLE_RELAY, source_ref="PROV-PROMOTE-1", provisional=True, driver_user_id=None)
        bid = (await client.post("/internal/bids/relay", json=provisional)).json()
        assert bid["status"] == "exploring"

        # Human work done during exploration must survive promotion.
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        first_item = detail["checklist_items"][0]
        await client.patch(f"/bids/{bid['id']}/checklist/{first_item['id']}", json={"status": "done"})

        committed = dict(SAMPLE_RELAY, source_ref="PROV-PROMOTE-1", provisional=False, driver_user_id="u-driver")
        promoted = (await client.post("/internal/bids/relay", json=committed)).json()
        assert promoted["id"] == bid["id"]
        assert promoted["status"] == "draft"
        assert promoted["version"] == bid["version"] + 1

        after = (await client.get(f"/bids/{bid['id']}")).json()
        # Analysis + human state kept, driver assigned as lead on promotion.
        item_after = next(i for i in after["checklist_items"] if i["id"] == first_item["id"])
        assert item_after["status"] == "done"
        assert after["driver_user_id"] == "u-driver"
        assert any(c["user_id"] == "u-driver" and c["role"] == "lead" for c in after["collaborators"])

        # Promotion is in the audit trail.
        actions = {a["action"] for a in (await client.get(f"/bids/{bid['id']}/activity")).json()}
        assert "bid.promoted" in actions


@pytest.mark.asyncio
async def test_discard_archives_only_exploring_workspaces():
    async with api_client() as client:
        # Exploring workspace → archived.
        provisional = dict(SAMPLE_RELAY, source_ref="PROV-DISCARD-1", provisional=True)
        bid = (await client.post("/internal/bids/relay", json=provisional)).json()
        r = await client.post("/internal/bids/discard", json={"source_ref": "PROV-DISCARD-1"})
        assert r.status_code == 200, r.text
        assert r.json() == {
            "bid_id": bid["id"],
            "source_ref": "PROV-DISCARD-1",
            "status": "withdrawn",
            "archived": True,
        }
        actions = {a["action"] for a in (await client.get(f"/bids/{bid['id']}/activity")).json()}
        assert "bid.archived" in actions

        # Committed bid → untouched by an upstream triage flip.
        committed = dict(SAMPLE_RELAY, source_ref="PROV-DISCARD-2", provisional=False)
        bid2 = (await client.post("/internal/bids/relay", json=committed)).json()
        r2 = await client.post("/internal/bids/discard", json={"source_ref": "PROV-DISCARD-2"})
        assert r2.status_code == 200
        assert r2.json()["archived"] is False
        assert (await client.get(f"/bids/{bid2['id']}")).json()["status"] == "draft"


@pytest.mark.asyncio
async def test_discard_unknown_source_ref_is_404():
    async with api_client() as client:
        r = await client.post("/internal/bids/discard", json={"source_ref": "NEVER-RELAYED"})
        assert r.status_code == 404
