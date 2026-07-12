"""Integration tests: transparent scoring, document↔requirement matching (incl.
cross-bid corpus reuse), and the bid/no-bid recommendation."""

import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


async def _create_bid(client, relay=None) -> dict:
    r = await client.post("/internal/bids/relay", json=relay or SAMPLE_RELAY)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_score_is_transparent_and_reacts_to_progress():
    async with api_client() as client:
        bid = await _create_bid(client)

        score = (await client.get(f"/bids/{bid['id']}/score")).json()
        # Transparent: every criterion carries weight, score and a detail line.
        assert round(sum(c["weight"] for c in score["criteria"]), 2) == 1.0
        assert all(c["detail"] for c in score["criteria"])
        assert 0 <= score["total"] <= 100
        before = score["total"]

        # Completing all formal items must raise the weighted total.
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        for item in [i for i in detail["checklist_items"] if i["criterion_kind"] == "formal"]:
            await client.patch(f"/bids/{bid['id']}/checklist/{item['id']}", json={"status": "done"})
        after = (await client.get(f"/bids/{bid['id']}/score")).json()
        assert after["total"] > before
        formal = next(c for c in after["criteria"] if c["key"] == "formal_readiness")
        assert formal["score"] == 100.0


@pytest.mark.asyncio
async def test_recommendation_has_decision_and_reasons():
    async with api_client() as client:
        bid = await _create_bid(client)
        reco = (await client.get(f"/bids/{bid['id']}/recommendation")).json()
        assert reco["recommendation"] in ("bid", "no_bid", "review")
        assert reco["reasons"]
        assert 0 < reco["confidence"] <= 1
        assert reco["score"]["criteria"]


@pytest.mark.asyncio
async def test_match_links_own_document_to_requirement():
    async with api_client() as client:
        bid = await _create_bid(client)
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        ref_item = next(i for i in detail["checklist_items"] if i["requirement_type"] == "reference")

        # Upload WITHOUT linking it, then let /match find the connection.
        content = b"Comparable references from previous years, client Stadt X."
        files = {"file": ("references.txt", io.BytesIO(content), "text/plain")}
        r = await client.post(f"/bids/{bid['id']}/documents", files=files, data={"kind": "reference"})
        assert r.status_code == 201, r.text

        matched = (await client.post(f"/bids/{bid['id']}/match")).json()
        own = [m for m in matched["matches"] if not m["from_corpus"]]
        assert any(m["checklist_item_id"] == ref_item["id"] for m in own)

        after = (await client.get(f"/bids/{bid['id']}")).json()
        item_after = next(i for i in after["checklist_items"] if i["id"] == ref_item["id"])
        assert item_after["ai_verification"]["status"] == "matched"

        # The re-match is recorded in the audit trail.
        actions = {a["action"] for a in (await client.get(f"/bids/{bid['id']}/activity")).json()}
        assert "documents.matched" in actions


@pytest.mark.asyncio
async def test_cross_bid_corpus_surfaces_reusable_evidence():
    async with api_client() as client:
        # Bid A owns a reference document.
        bid_a = await _create_bid(client)
        content = b"Comparable references from the last three years, public sector clients."
        files = {"file": ("references-corpus.txt", io.BytesIO(content), "text/plain")}
        r = await client.post(f"/bids/{bid_a['id']}/documents", files=files, data={"kind": "reference"})
        assert r.status_code == 201, r.text

        # Bid B (different source_ref) has the same requirement but no uploads.
        relay_b = dict(SAMPLE_RELAY, source_ref="OTHER-REF-2", title="Second Tender")
        bid_b = await _create_bid(client, relay_b)

        reco = (await client.get(f"/bids/{bid_b['id']}/recommendation")).json()
        reusable = reco["reusable_evidence"]
        assert reusable, "expected corpus evidence from bid A"
        assert all(m["from_corpus"] for m in reusable)
        assert any(m["filename"] == "references-corpus.txt" for m in reusable)

        # Corpus hits must NOT auto-complete bid B's items.
        detail_b = (await client.get(f"/bids/{bid_b['id']}")).json()
        ref_items = [i for i in detail_b["checklist_items"] if i["requirement_type"] == "reference"]
        assert all(i["status"] == "open" for i in ref_items)
