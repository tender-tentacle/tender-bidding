"""Service KPIs for the expert backend."""

import pytest
from tests.helpers import SAMPLE_RELAY, api_client


@pytest.mark.asyncio
async def test_stats_reflect_pipeline_state():
    async with api_client() as client:
        empty = (await client.get("/stats")).json()
        assert empty["bids_total"] == 0 and empty["matrix"] is None

        r = await client.post("/internal/bids/relay", json=SAMPLE_RELAY)
        bid = r.json()
        stats = (await client.get("/stats")).json()
        assert stats["bids_total"] == 1
        assert stats["bids_by_status"] == {"draft": 1}
        assert stats["checklist_items_total"] > 0
        assert stats["checklist_items_open"] == stats["checklist_items_total"]
        assert stats["key_dates_total"] >= 1
        assert stats["activity_events"] >= 1
        assert stats["prompt_versions"] == {}

        # Editing a prompt and completing an item moves the KPIs.
        await client.post("/config/bidding_deadlines", json={"prompt_template": "v1"}, headers={"X-User-Role": "admin"})
        detail = (await client.get(f"/bids/{bid['id']}")).json()
        item = detail["checklist_items"][0]
        await client.patch(f"/bids/{bid['id']}/checklist/{item['id']}", json={"status": "done"})
        after = (await client.get("/stats")).json()
        assert after["prompt_versions"] == {"bidding_deadlines": 1}
        assert after["checklist_items_open"] == after["checklist_items_total"] - 1
