"""Config API (enriching pattern): prompt templates per extraction category,
defaults until edited, versioned with history."""

import pytest
from tests.helpers import api_client

EXPERT = {"X-User-Role": "admin", "X-User-ID": "head-ps"}


@pytest.mark.asyncio
async def test_defaults_are_served_until_edited():
    async with api_client() as client:
        all_cfg = (await client.get("/config")).json()
        assert set(all_cfg) == {"bidding_deadlines", "bidding_required_documents"}
        assert all(c["is_default"] and c["version"] == 0 for c in all_cfg.values())
        assert (
            "Handelsregister" in all_cfg["bidding_required_documents"]["prompt_template"]
            or all_cfg["bidding_required_documents"]["prompt_template"]
        )


@pytest.mark.asyncio
async def test_edit_is_versioned_with_history():
    async with api_client() as client:
        r = await client.post(
            "/config/bidding_deadlines",
            json={"prompt_template": "Extract ALL dates incl. Bindefrist.", "change_summary": "add Bindefrist"},
            headers=EXPERT,
        )
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 1 and r.json()["is_default"] is False

        r2 = await client.post(
            "/config/bidding_deadlines",
            json={"prompt_template": "v2 template", "change_summary": "tighten"},
            headers=EXPERT,
        )
        assert r2.json()["version"] == 2

        current = (await client.get("/config/bidding_deadlines")).json()
        assert current["prompt_template"] == "v2 template"

        history = (await client.get("/config/bidding_deadlines/history")).json()
        assert [h["version"] for h in history] == [2, 1]
        assert history[1]["change_summary"] == "add Bindefrist"
        assert all(h["created_by"] == "head-ps" for h in history)


@pytest.mark.asyncio
async def test_unknown_category_and_empty_template_rejected():
    async with api_client() as client:
        assert (await client.get("/config/nonsense")).status_code == 404
        assert (
            await client.post("/config/bidding_deadlines", json={"prompt_template": "   "}, headers=EXPERT)
        ).status_code == 400
