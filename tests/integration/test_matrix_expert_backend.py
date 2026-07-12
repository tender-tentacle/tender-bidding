"""Expert backend for the decision matrix (enriching-config pattern): versioned
edits of threshold/name, category CRUD with headline + explanation, history."""

import io

import pytest
from tests.helpers import api_client

MATRIX_DOC = """# Public Sector Bid/No-Bid Matrix
- Strategic fit (weight 5): fit with cluster strategy and target customers
- Comparable references (weight 4): references from the last three years
threshold: 25
"""

EXPERT = {"X-User-Role": "admin", "X-User-ID": "head-ps"}


async def _upload(client) -> dict:
    files = {"file": ("matrix.md", io.BytesIO(MATRIX_DOC.encode()), "text/markdown")}
    r = await client.post("/matrix", files=files, headers=EXPERT)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_update_threshold_and_name_is_versioned():
    async with api_client() as client:
        m = await _upload(client)
        assert m["version"] == 2  # v1 snapshotted at upload

        r = await client.put(
            "/matrix",
            json={"threshold": 40, "name": "PS Matrix 2026", "change_summary": "Raised bar for H2"},
            headers=EXPERT,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["threshold"] == 40 and out["name"] == "PS Matrix 2026"
        assert out["version"] == 3

        # Threshold beyond 5×Σweights is rejected.
        too_high = await client.put("/matrix", json={"threshold": 999}, headers=EXPERT)
        assert too_high.status_code == 400


@pytest.mark.asyncio
async def test_category_crud_with_headline_and_explanation():
    async with api_client() as client:
        await _upload(client)

        # Add: headline + expert explanation (what the AI grounds scoring on).
        r = await client.post(
            "/matrix/categories",
            json={
                "headline": "Partner ecosystem",
                "explanation": "Do we have partners to close capability gaps? High score = signed partner available.",
                "weight": 2,
            },
            headers=EXPERT,
        )
        assert r.status_code == 201, r.text
        m = r.json()
        added = next(c for c in m["categories"] if c["headline"] == "Partner ecosystem")
        assert added["explanation"].startswith("Do we have partners")
        assert m["max_points"] == 5 * (5 + 4 + 2)

        # Update headline/explanation/weight.
        r = await client.patch(
            f"/matrix/categories/{added['id']}",
            json={"explanation": "Updated intent.", "weight": 3},
            headers=EXPERT,
        )
        assert r.status_code == 200
        upd = next(c for c in r.json()["categories"] if c["id"] == added["id"])
        assert upd["explanation"] == "Updated intent." and upd["weight"] == 3

        # Invalid weight → 400; unknown id → 404.
        assert (
            await client.patch(f"/matrix/categories/{added['id']}", json={"weight": 9}, headers=EXPERT)
        ).status_code == 400
        assert (await client.patch("/matrix/categories/nope", json={"weight": 2}, headers=EXPERT)).status_code == 404

        # Delete removes the category (and its ratings).
        r = await client.delete(f"/matrix/categories/{added['id']}", headers=EXPERT)
        assert r.status_code == 200
        assert all(c["id"] != added["id"] for c in r.json()["categories"])


@pytest.mark.asyncio
async def test_history_records_every_change():
    async with api_client() as client:
        await _upload(client)
        await client.put("/matrix", json={"threshold": 30, "change_summary": "tune"}, headers=EXPERT)
        await client.post("/matrix/categories", json={"headline": "Risk appetite", "weight": 1}, headers=EXPERT)

        history = (await client.get("/matrix/history")).json()
        assert len(history) == 3
        summaries = [h["change_summary"] for h in history]
        assert summaries[0] == "Added category 'Risk appetite'"
        assert summaries[1] == "tune"
        assert summaries[2].startswith("Uploaded from")
        assert all(h["created_by"] == "head-ps" for h in history)
        # Each entry snapshots the full matrix at that version.
        assert history[1]["data"]["threshold"] == 30


@pytest.mark.asyncio
async def test_evaluation_uses_updated_explanation():
    """Sharper explanations change AI scoring — the point of the expert backend."""
    async with api_client() as client:
        await _upload(client)
        from tests.helpers import SAMPLE_RELAY

        r = await client.post("/internal/bids/relay", json=SAMPLE_RELAY)
        bid = r.json()

        ev = (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).json()
        strategic = next(c for c in ev["categories"] if c["headline"] == "Strategic fit")
        before = strategic["ai_score"]

        # Rewrite the explanation with terms present in the bid corpus.
        await client.patch(
            f"/matrix/categories/{strategic['category_id']}",
            json={"explanation": "cloud platform references consortium declaration"},
            headers=EXPERT,
        )
        ev2 = (await client.post(f"/bids/{bid['id']}/matrix-evaluation")).json()
        after = next(c for c in ev2["categories"] if c["headline"] == "Strategic fit")["ai_score"]
        assert after > before
