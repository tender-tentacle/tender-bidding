from unittest.mock import AsyncMock, patch

import pytest
from api.v1.company_summary import run_stage1_solvency


@pytest.mark.asyncio
async def test_run_stage1_solvency_with_aor_wikidata_gnd():
    """Verify that Stage 1 solvency enriches AÖR summaries with Wikidata and DNB GND data."""
    mock_discovered = {
        "company_name": "Stadtwerke München",
        "kununu_url": "https://www.kununu.com/de/swm",
        "northdata_url": None,
        "wikidata_url": "https://www.wikidata.org/wiki/Q881512",
        "gnd_url": "https://d-nb.info/gnd/1007891-2"
    }

    mock_profile = {
        "wikidata": {
            "qid": "Q881512",
            "label": "Stadtwerke München",
            "description": "Anstalt des öffentlichen Rechts der Landeshauptstadt München",
            "gnd_id": "1007891-2",
            "official_website": "https://www.swm.de",
            "wikidata_url": "https://www.wikidata.org/wiki/Q881512",
            "wikipedia_url": "https://de.wikipedia.org/wiki/Stadtwerke_M%C3%BCnchen"
        },
        "gnd": {
            "gnd_id": "1007891-2",
            "preferred_name": "Stadtwerke München",
            "variantName": ["SWM", "Stadtwerke München AöR"],
            "entity_type": ["CorporateBody", "Authority"],
            "gnd_url": "https://d-nb.info/gnd/1007891-2",
            "location": "München",
            "parent_entity": "München. Landeshauptstadt",
            "official_website": "https://www.swm.de"
        }
    }

    with patch("api.v1.company_summary.discover_company_urls_azure", new_callable=AsyncMock) as mock_disc, \
         patch("api.v1.company_summary.fetch_wikidata_gnd_profile", new_callable=AsyncMock) as mock_fetch, \
         patch("api.v1.company_summary.get_company_db_data", new_callable=AsyncMock) as mock_db:

        mock_disc.return_value = mock_discovered
        mock_fetch.return_value = mock_profile
        mock_db.return_value = {}

        result = await run_stage1_solvency(company_name="Stadtwerke München", is_aor=True, db=None)

        assert "Stadtwerke München" in result["short_summary"]
        assert "Anstalt des öffentlichen Rechts" in result["short_summary"] or "Landeshauptstadt München" in result["long_summary"]
        
        badges = result["financial_solvency_badges"]
        assert badges["wikidata_url"] == "https://www.wikidata.org/wiki/Q881512"
        assert badges["gnd_url"] == "https://d-nb.info/gnd/1007891-2"
        assert badges["gnd_id"] == "1007891-2"
        assert any("Wikidata" in flag or "DNB GND" in flag or "AÖR" in flag for flag in result["red_flag_banners"])
