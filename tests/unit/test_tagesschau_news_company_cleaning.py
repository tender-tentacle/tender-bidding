"""Unit test for company name resolution & cleaning in Tagesschau news scan."""

import pytest
from core.utils import clean_company_name_candidates
from tests.helpers import api_client


def test_clean_company_name_candidates_legal_forms_and_clauses():
    """Verify that candidate generation strips legal form extensions and representation clauses."""
    cands1 = clean_company_name_candidates("Flughafen München GmbH")
    assert "Flughafen München" in cands1

    cands2 = clean_company_name_candidates("Flughafen München GmbH & Co. KG")
    assert "Flughafen München" in cands2

    cands3 = clean_company_name_candidates(
        "Bundesrepublik Deutschland, vertreten durch das Bundesministerium des Innern, "
        "vertreten durch das Beschaffungsamt des BMI"
    )
    assert "Bundesrepublik Deutschland" in cands3

    cands4 = clean_company_name_candidates("Stadtwerke München GmbH")
    assert "Stadtwerke München" in cands4

    cands5 = clean_company_name_candidates("Fraunhofer-Gesellschaft zur Förderung der angewandten Forschung e.V.")
    assert "Fraunhofer" in cands5 or "Fraunhofer-Gesellschaft" in cands5


@pytest.mark.asyncio
async def test_flughafen_muenchen_gmbh_tagesschau_news_scan():
    """Verify that company summary extraction for 'Flughafen München GmbH' populates Tagesschau news scan."""
    async with api_client() as client:
        bid_id = "bid-flughafen-muenchen-001"
        company_name = "Flughafen München GmbH"

        res = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": company_name}
        )
        assert res.status_code == 200
        data = res.json()

        news_scan = data.get("tagesschau_news_scan", {})
        assert news_scan.get("articles_found", 0) > 0
        headlines = news_scan.get("recent_headlines", [])
        assert len(headlines) > 0


@pytest.mark.asyncio
async def test_bundesrepublik_deutschland_vertreten_durch_tagesschau_news_scan():
    """Verify that company summary extraction for long official name populates Tagesschau news scan."""
    async with api_client() as client:
        bid_id = "bid-bundesrepublik-001"
        company_name = "Bundesrepublik Deutschland, vertreten durch das Bundesministerium des Innern, vertreten durch das Beschaffungsamt des BMI"

        res = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": company_name}
        )
        assert res.status_code == 200
        data = res.json()

        news_scan = data.get("tagesschau_news_scan", {})
        assert news_scan.get("articles_found", 0) > 0
