"""Decision matrix: expert upload → AI categories, per-bid AI evaluation with
portal intelligence, human override wins, weighted verdict drives the
recommendation."""

import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client

MATRIX_DOC = """# Public Sector Bid/No-Bid Matrix
- Strategic fit (weight 5): cloud platform strategy public sector
- Comparable references (weight 4): references from the last three years
- Competitive environment (weight 3): incumbent advantage and likely competitors
threshold: 30
"""


async def _bid(client, **overrides) -> dict:
    payload = dict(SAMPLE_RELAY, **overrides)
    r = await client.post("/internal/bids/relay", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


async def _upload_matrix(client, text: str = MATRIX_DOC) -> dict:
    files = {"file": ("matrix.md", io.BytesIO(text.encode()), "text/markdown")}
    r = await client.post("/matrix", files=files, headers={"X-User-Role": "admin", "X-User-ID": "head-ps"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_upload_translates_matrix_into_weighted_categories():
    async with api_client() as client:
        m = await _upload_matrix(client)
        assert m["threshold"] == 30
        assert [c["name"] for c in m["categories"]] == [
            "Strategic fit",
            "Comparable references",
            "Competitive environment",
        ]
        assert [c["weight"] for c in m["categories"]] == [5, 4, 3]

        # Unstructured upload falls back to the default category set.
        m2 = await _upload_matrix(client, "just some prose about bidding decisions")
        assert len(m2["categories"]) == 6
        # New upload replaces the active matrix.
        active = (await client.get("/matrix")).json()
        assert active["id"] == m2["id"]


@pytest.mark.asyncio
async def test_evaluation_scores_categories_with_rationale_and_intel():
    async with api_client() as client:
        await _upload_matrix(client)
        bid = await _bid(client, cpv_codes=["72000000-5"])

        ev = (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).json()
        assert ev["evaluated"] is True
        assert ev["max_points"] == 5 * (5 + 4 + 3)
        assert ev["verdict"] in ("bid", "no_bid")
        assert all(c["ai_score"] is not None and c["ai_rationale"] for c in ev["categories"])

        # The competition category is driven by portal intel (3 mock IT competitors → 5-3=2).
        comp = next(c for c in ev["categories"] if "Competitive" in c["name"])
        assert comp["ai_score"] == 2
        assert "TED" in comp["ai_rationale"]

        intel = (await client.get(f"/bids/{bid['id']}/market-intel")).json()
        assert {c["name"] for c in intel["competitors"]} >= {"Materna SE"}
        assert intel["source_portals"] == ["TED", "bund.de"]


@pytest.mark.asyncio
async def test_human_override_wins_and_flips_verdict():
    async with api_client() as client:
        await _upload_matrix(client)
        bid = await _bid(client)
        ev = (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).json()

        # Force NO BID: expert zeroes every category → total 0 < 30.
        for c in ev["categories"]:
            await client.patch(
                f"/bids/{bid['id']}/matrix-evaluation/{c['category_id']}",
                json={"score": 0, "note": "not a fit"},
                headers={"X-User-ID": "head-ps"},
            )
        zeroed = (await client.get(f"/bids/{bid['id']}/matrix-evaluation")).json()
        assert zeroed["total_points"] == 0 and zeroed["verdict"] == "no_bid"

        # The expert overrides every category to 5 → total 60 ≥ 30 → bid.
        for c in ev["categories"]:
            r = await client.patch(
                f"/bids/{bid['id']}/matrix-evaluation/{c['category_id']}",
                json={"score": 5, "note": "strategic priority"},
                headers={"X-User-ID": "head-ps"},
            )
            assert r.status_code == 200, r.text
        after = (await client.get(f"/bids/{bid['id']}/matrix-evaluation")).json()
        assert after["total_points"] == after["max_points"] == 60
        assert after["verdict"] == "bid"
        assert all(c["overridden_by"] == "head-ps" for c in after["categories"])

        # Re-evaluation refreshes AI scores but never touches overrides.
        again = (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).json()
        assert again["verdict"] == "bid"
        assert all(c["human_score"] == 5 for c in again["categories"])

        # Out-of-range override → 400.
        bad = await client.patch(
            f"/bids/{bid['id']}/matrix-evaluation/{ev['categories'][0]['category_id']}", json={"score": 9}
        )
        assert bad.status_code == 400

        # Overrides are on the audit trail.
        actions = {a["action"] for a in (await client.get(f"/bids/{bid['id']}/activity")).json()}
        assert {"matrix.evaluated", "matrix.overridden"} <= actions


@pytest.mark.asyncio
async def test_matrix_verdict_leads_the_recommendation():
    async with api_client() as client:
        await _upload_matrix(client)
        bid = await _bid(client)

        # Without an evaluation the recommendation works as before (no matrix section).
        before = (await client.get(f"/bids/{bid['id']}/recommendation")).json()
        assert before["matrix"] is None

        await client.post(f"/bids/{bid['id']}/matrix-evaluation")
        ev = (await client.get(f"/bids/{bid['id']}/matrix-evaluation")).json()
        reco = (await client.get(f"/bids/{bid['id']}/recommendation")).json()
        assert reco["matrix"]["verdict"] == ev["verdict"]
        assert reco["recommendation"] == ev["verdict"]
        assert any("Decision matrix" in r for r in reco["reasons"])


@pytest.mark.asyncio
async def test_endpoints_without_matrix_return_404():
    async with api_client() as client:
        bid = await _bid(client)
        assert (await client.get("/matrix")).status_code == 404
        assert (await client.get(f"/bids/{bid['id']}/matrix-evaluation")).status_code == 404
        assert (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).status_code == 404
