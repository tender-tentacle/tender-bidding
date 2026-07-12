"""Consumer-driven contract test for the enriching → bidding relay.

Asserts the bidding provider honours the exact request shape the enriching
`BiddingClient.build_bid_snapshot` emits, and returns the fields the consumer
relies on. This is the in-process contract check; a broker-based pact is the CI
upgrade (kept out of the broker to stay hermetic, like the repo's other pacts).
"""

import pytest
from tests.helpers import api_client

# The canonical payload produced by tender-enriching/core/bidding_client.py
# build_bid_snapshot(). Keep in sync with that producer — this IS the contract.
CONSUMER_RELAY_PAYLOAD = {
    "source_ref": "PACT-NID-1",
    "source_kind": "tender",
    "title": "Cloud Platform Services",
    "customer": "Stadt Musterstadt",
    "source_system": "Öffentliche Vergabe",
    "driver_user_id": "u-driver",
    "deadline_at": "2099-09-01T12:00:00Z",
    "description": "Bau und Betrieb",
    "document_text": "Cloud platform, Bietergemeinschaft möglich",
    "cpv_codes": ["72000000-5"],
    "lots": [
        {
            "lot_id": "PACT-NID-1_LOT-0001",
            "lot_number": 1,
            "title": "Los 1",
            "description": None,
            "document_text": "Netz",
        },
    ],
    # triage="bid" → committed; triage="interesting" → provisional (exploring).
    "provisional": False,
}

# Fields the consumer (enriching) depends on in the response.
EXPECTED_RESPONSE_FIELDS = {"id", "source_ref", "title", "status", "version"}


@pytest.mark.asyncio
async def test_relay_provider_honours_consumer_contract():
    async with api_client() as client:
        resp = await client.post("/internal/bids/relay", json=CONSUMER_RELAY_PAYLOAD)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) >= EXPECTED_RESPONSE_FIELDS
        assert body["source_ref"] == "PACT-NID-1"
        assert body["status"] in ("exploring", "draft", "in_progress", "submitted", "won", "lost", "withdrawn")


@pytest.mark.asyncio
async def test_relay_tolerates_minimal_payload():
    """Provider must accept the minimal contract (only required fields)."""
    async with api_client() as client:
        resp = await client.post("/internal/bids/relay", json={"source_ref": "PACT-MIN-1", "title": "Minimal"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["source_ref"] == "PACT-MIN-1"


@pytest.mark.asyncio
async def test_provisional_relay_contract():
    """triage="interesting" sends provisional=True and must yield an exploring workspace."""
    async with api_client() as client:
        payload = dict(CONSUMER_RELAY_PAYLOAD, source_ref="PACT-PROV-1", provisional=True)
        resp = await client.post("/internal/bids/relay", json=payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "exploring"


@pytest.mark.asyncio
async def test_discard_contract():
    """The consumer's no-bid discard: 200 + archived flag for a known ref, 404 otherwise."""
    async with api_client() as client:
        payload = dict(CONSUMER_RELAY_PAYLOAD, source_ref="PACT-DISC-1", provisional=True)
        await client.post("/internal/bids/relay", json=payload)

        resp = await client.post("/internal/bids/discard", json={"source_ref": "PACT-DISC-1"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] is True

        resp = await client.post("/internal/bids/discard", json={"source_ref": "PACT-UNKNOWN"})
        assert resp.status_code == 404
