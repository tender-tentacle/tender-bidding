"""Integration tests for FEAT-053 accept/reject: a human decides on a proposed
corpus match; acceptance records provenance, rejection records the why."""

import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


async def _bid_with_corpus(client) -> tuple[dict, dict, dict]:
    """Bid A holds a reference doc (the corpus); bid B has the open requirement.

    Returns (bid_b_detail, ref_item, corpus_match) where corpus_match is the
    proposed cross-bid match for bid B's reference requirement.
    """
    bid_a = (await client.post("/internal/bids/relay", json=dict(SAMPLE_RELAY, source_ref="MD-A"))).json()
    content = b"Comparable references from the last three years, public sector clients."
    files = {"file": ("references-md.txt", io.BytesIO(content), "text/plain")}
    r = await client.post(f"/bids/{bid_a['id']}/documents", files=files, data={"kind": "reference"})
    assert r.status_code == 201, r.text

    bid_b = (await client.post("/internal/bids/relay", json=dict(SAMPLE_RELAY, source_ref="MD-B"))).json()
    matched = (await client.post(f"/bids/{bid_b['id']}/match")).json()
    corpus_matches = [m for m in matched["matches"] if m["from_corpus"]]
    assert corpus_matches, "expected a cross-bid match proposal"

    detail_b = (await client.get(f"/bids/{bid_b['id']}")).json()
    match = corpus_matches[0]
    item = next(i for i in detail_b["checklist_items"] if i["id"] == match["checklist_item_id"])
    return detail_b, item, match


@pytest.mark.asyncio
async def test_accept_corpus_match_records_provenance():
    async with api_client() as client:
        bid_b, item, match = await _bid_with_corpus(client)

        r = await client.post(
            f"/bids/{bid_b['id']}/match/accept",
            json={"checklist_item_id": item["id"], "document_id": match["document_id"]},
            headers={"X-User-ID": "meike"},
        )
        assert r.status_code == 200, r.text
        verification = r.json()["ai_verification"]
        assert verification["status"] == "matched"
        assert verification["from_corpus"] is True
        assert verification["source_document_id"] == match["document_id"]
        assert verification["accepted_by"] == "meike"

        # Accepting evidence does NOT auto-complete the item — a human still adapts it.
        after = (await client.get(f"/bids/{bid_b['id']}")).json()
        item_after = next(i for i in after["checklist_items"] if i["id"] == item["id"])
        assert item_after["status"] == "open"
        assert item_after["ai_verification"]["source_bid_id"] != bid_b["id"]

        # Provenance lands in the audit trail (feeds the contribution ledger).
        acts = (await client.get(f"/bids/{bid_b['id']}/activity")).json()
        accepted = next(a for a in acts if a["action"] == "match.accepted")
        assert accepted["actor_user_id"] == "meike"
        assert accepted["detail"]["filename"] == match["filename"]
        assert accepted["detail"]["from_corpus"] is True


@pytest.mark.asyncio
async def test_reject_corpus_match_keeps_item_and_logs_reason():
    async with api_client() as client:
        bid_b, item, match = await _bid_with_corpus(client)
        before = item.get("ai_verification")

        r = await client.post(
            f"/bids/{bid_b['id']}/match/reject",
            json={
                "checklist_item_id": item["id"],
                "document_id": match["document_id"],
                "reason": "reference too old for the 3-year lookback",
            },
        )
        assert r.status_code == 200, r.text

        after = (await client.get(f"/bids/{bid_b['id']}")).json()
        item_after = next(i for i in after["checklist_items"] if i["id"] == item["id"])
        assert item_after["ai_verification"] == before  # untouched

        acts = (await client.get(f"/bids/{bid_b['id']}/activity")).json()
        rejected = next(a for a in acts if a["action"] == "match.rejected")
        assert rejected["detail"]["reason"] == "reference too old for the 3-year lookback"


@pytest.mark.asyncio
async def test_match_decisions_validate_targets():
    async with api_client() as client:
        bid = (await client.post("/internal/bids/relay", json=dict(SAMPLE_RELAY, source_ref="MD-404"))).json()
        item_id = (await client.get(f"/bids/{bid['id']}")).json()["checklist_items"][0]["id"]

        r = await client.post(
            f"/bids/{bid['id']}/match/accept", json={"checklist_item_id": "nope", "document_id": "nope"}
        )
        assert r.status_code == 404
        r = await client.post(
            f"/bids/{bid['id']}/match/accept", json={"checklist_item_id": item_id, "document_id": "nope"}
        )
        assert r.status_code == 404
