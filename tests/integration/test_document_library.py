"""US-101 — cross-bid document library search: full-text + semantic ranking,
kind/client/CPV filters, sensitivity via IAM role, and won-bid provenance."""

import io

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


async def _bid(client, **overrides) -> dict:
    payload = dict(SAMPLE_RELAY, **overrides)
    r = await client.post("/internal/bids/relay", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


async def _upload(client, bid_id: str, filename: str, text: str, kind: str, sensitivity: str = "normal") -> dict:
    files = {"file": (filename, io.BytesIO(text.encode()), "text/plain")}
    r = await client.post(f"/bids/{bid_id}/documents", files=files, data={"kind": kind, "sensitivity": sensitivity})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_search_by_topic_ranks_relevant_docs_first():
    async with api_client() as client:
        bid = await _bid(client)
        await _upload(
            client, bid["id"], "cloud-references.txt", "Cloud migration references for public sector", "reference"
        )
        await _upload(client, bid["id"], "catering.txt", "Catering services for the canteen", "supporting")

        res = (await client.get("/library/search", params={"q": "cloud migration references"})).json()
        assert res["results"], "expected at least one hit"
        assert res["results"][0]["filename"] == "cloud-references.txt"
        assert res["results"][0]["score"] > 0
        # The irrelevant catering doc must not outrank (or even match) the topic.
        names = [r["filename"] for r in res["results"]]
        assert names.index("cloud-references.txt") == 0


@pytest.mark.asyncio
async def test_filters_kind_client_and_cpv():
    async with api_client() as client:
        bid_a = await _bid(client, cpv_codes=["72000000-5"])
        bid_b = await _bid(client, source_ref="LIB-B", title="Other Tender", customer="Bund Agentur")
        await _upload(client, bid_a["id"], "iso-cert.txt", "ISO 27001 certificate", "certificate")
        await _upload(client, bid_b["id"], "profile-anna.txt", "Senior architect profile", "profile")

        by_kind = (await client.get("/library/search", params={"kind": "certificate"})).json()
        assert {r["kind"] for r in by_kind["results"]} == {"certificate"}

        by_client = (await client.get("/library/search", params={"client": "Bund"})).json()
        assert {r["filename"] for r in by_client["results"]} == {"profile-anna.txt"}

        by_cpv = (await client.get("/library/search", params={"cpv": "72000000-5"})).json()
        assert {r["filename"] for r in by_cpv["results"]} == {"iso-cert.txt"}

        bad_kind = await client.get("/library/search", params={"kind": "nonsense"})
        assert bad_kind.status_code == 400


@pytest.mark.asyncio
async def test_sensitivity_honours_iam_role():
    async with api_client() as client:
        bid = await _bid(client)
        await _upload(client, bid["id"], "public-ref.txt", "Public reference", "reference", "normal")
        await _upload(client, bid["id"], "team-cv.txt", "CV of key personnel", "profile", "special")

        # No role header → least privilege: only normal docs.
        anon = (await client.get("/library/search")).json()
        assert {r["filename"] for r in anon["results"]} == {"public-ref.txt"}
        assert anon["visible_sensitivities"] == ["normal"]

        # member sees personal but NOT special.
        member = (await client.get("/library/search", headers={"X-User-Role": "member"})).json()
        assert "team-cv.txt" not in {r["filename"] for r in member["results"]}

        # admin sees everything.
        admin = (await client.get("/library/search", headers={"X-User-Role": "admin"})).json()
        assert {"public-ref.txt", "team-cv.txt"} <= {r["filename"] for r in admin["results"]}

        # The uploader always sees their own special doc.
        files = {"file": ("own-cv.txt", io.BytesIO(b"my own cv"), "text/plain")}
        r = await client.post(
            f"/bids/{bid['id']}/documents",
            files=files,
            data={"kind": "profile", "sensitivity": "special"},
            headers={"X-User-ID": "ambika"},
        )
        assert r.status_code == 201
        own = (await client.get("/library/search", headers={"X-User-ID": "ambika"})).json()
        assert "own-cv.txt" in {r["filename"] for r in own["results"]}


@pytest.mark.asyncio
async def test_results_show_bid_usage_and_won_provenance():
    async with api_client() as client:
        # Same file content used in two bids; one of them is WON.
        bid_a = await _bid(client)
        bid_b = await _bid(client, source_ref="LIB-WON", title="Won Tender", customer="Stadt Siegen")
        text = "Framework reference: managed cloud operations 2023–2026."
        await _upload(client, bid_a["id"], "framework-ref.txt", text, "reference")
        await _upload(client, bid_b["id"], "framework-ref.txt", text, "reference")

        detail_b = (await client.get(f"/bids/{bid_b['id']}")).json()
        ok = await client.post(
            f"/bids/{bid_b['id']}/status", json={"status": "won", "expected_version": detail_b["version"]}
        )
        assert ok.status_code == 200, ok.text

        res = (await client.get("/library/search", params={"q": "framework cloud operations"})).json()
        hit = next(r for r in res["results"] if r["filename"] == "framework-ref.txt")
        # Identical files across bids group into one result with both usages.
        assert len(hit["usages"]) == 2
        assert hit["proven"] is True
        won = next(u for u in hit["usages"] if u["won"])
        assert won["bid_title"] == "Won Tender"
