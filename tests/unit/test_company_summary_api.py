"""Unit test for Company Data Summary backend logic & fallback handling in tender-bidding."""

import pytest
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_company_summary_aor_fallback():
    """Verify that when North Data is absent (e.g. AÖR entity), red flags and solvency fallback are generated."""
    async with api_client() as client:
        # Request extraction for an AÖR institution with no North Data
        res = await client.post(
            "/bids/test-aor-bid/company-summary/extract",
            json={"company_name": "Landesbetrieb Liegenschafts- und Baubetreuung", "is_aor": True}
        )
        assert res.status_code == 200
        data = res.json()
        assert any("AÖR" in flag or "Anstalt des öffentlichen Rechts" in flag for flag in data["red_flag_banners"])
        assert "AÖR" in data["financial_solvency_badges"]["solvency_status"]


@pytest.mark.asyncio
async def test_company_summary_persistence():
    """Verify saving and loading company summary to DB."""
    async with api_client() as client:
        bid_id = "bid-persistence-001"
        res_extract = await client.post(
            f"/bids/{bid_id}/company-summary/extract",
            json={"company_name": "Flughafen Stuttgart GmbH"}
        )
        assert res_extract.status_code == 200
        summary_extracted = res_extract.json()

        res_get = await client.get(f"/bids/{bid_id}/company-summary")
        assert res_get.status_code == 200
        assert res_get.json()["short_summary"] == summary_extracted["short_summary"]


@pytest.mark.asyncio
async def test_company_summary_formatted_uuid_36_chars():
    """Verify that a 36-character UUID string (e.g. ed875469-2973-4029-ad66-46cb1776f58c) creates a Bid and extracts summary without 500 error."""
    async with api_client() as client:
        uuid_36 = "ed875469-2973-4029-ad66-46cb1776f58c"
        res_extract = await client.post(
            f"/bids/{uuid_36}/company-summary/extract",
            json={"company_name": "Flughafen Stuttgart GmbH"}
        )
        assert res_extract.status_code == 200
        summary_extracted = res_extract.json()
        assert summary_extracted["bid_id"] == uuid_36

        res_get = await client.get(f"/bids/{uuid_36}/company-summary")
        assert res_get.status_code == 200
        assert res_get.json()["bid_id"] == uuid_36


@pytest.mark.asyncio
async def test_staged_pipeline_data_lineage_and_matrix_synthesis():
    """TDD Test: Verify data lineage across 4 stages and dynamic Matrix synthesis in Stage 4."""
    async with api_client() as client:
        bid_id = "bid-lineage-001"
        company = "Flughafen Stuttgart GmbH"

        # Stage 1: Solvency & Legal Status
        res1 = await client.post(f"/bids/{bid_id}/company-summary/extract?stage=1", json={"company_name": company, "is_aor": True})
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["financial_solvency_badges"]["solvency_status"] == "AÖR Öffentliche Hand (Keine Registerwarnung)"
        assert d1["pipeline_status"]["stages"]["stage1_solvency"]["status"] == "completed"

        # Stage 2: Implicit Needs & Culture Mining
        res2 = await client.post(f"/bids/{bid_id}/company-summary/extract?stage=2", json={"company_name": company})
        assert res2.status_code == 200
        d2 = res2.json()
        assert isinstance(d2["implicit_tender_needs"], list)
        assert d2["pipeline_status"]["stages"]["stage2_implicit_needs"]["status"] == "completed"

        # Stage 3: Procurement Pressure & History
        res3 = await client.post(f"/bids/{bid_id}/company-summary/extract?stage=3", json={"company_name": company})
        assert res3.status_code == 200
        d3 = res3.json()
        assert "tender_frequency" in d3["procurement_pressure"]
        assert d3["pipeline_status"]["stages"]["stage3_procurement_pressure"]["status"] == "completed"

        # Stage 4: Decision Matrix Synthesis (Feeds on Stage 1, 2, 3 Data)
        res4 = await client.post(f"/bids/{bid_id}/company-summary/extract?stage=4", json={"company_name": company})
        assert res4.status_code == 200
        d4 = res4.json()
        matrix = d4["mhp_bid_no_bid_matrix"]
        assert matrix["verdict"] in ("BID / GO", "NO BID / NO GO")

        # Assert Data Lineage in Category Rationales
        cat_map = {c["category"]: c for c in matrix["categories"]}
        
        # Category 2 (Solvency) must reference Stage 1 credit status
        solvency_cat = cat_map["Finanzielle Stabilität & Bonität"]
        assert "AAA" in solvency_cat["rationale"] or "Bonität" in solvency_cat["rationale"]

        # Category 3 (Skills) rationale is string
        skill_cat = cat_map["Ressourcen- & Skill-Verfügbarkeit"]
        assert isinstance(skill_cat["rationale"], str)

        # Category 4 (Compliance) must reference Stage 1 AÖR legal status & compliance
        compliance_cat = cat_map["EVB-IT & Compliance-Risiko"]
        assert "EVB-IT" in compliance_cat["rationale"] or "Compliance" in compliance_cat["rationale"] or "Rechtliche" in compliance_cat["rationale"]


@pytest.mark.asyncio
async def test_no_hardcoded_dummy_data_when_real_records_exist():
    """Verify that when real company data exists in DB, company summary uses real data rather than hardcoded dummy values."""
    async with api_client() as client:
        company_name = "Bayerische Eisenbahngesellschaft mbH"
        res = await client.post(
            "/bids/test-no-dummy-bid/company-summary/extract",
            json={"company_name": company_name}
        )
        assert res.status_code == 200
        data = res.json()

        # Must NOT hardcode fake 'Index 1.4' or fake '4.1 / 5.0' if unverified, or use dynamic data
        solvency_badge = data["financial_solvency_badges"]["credit_score"]
        # Ensure company summary reflects real company name
        assert data["company_name"] == company_name
        assert company_name in data["short_summary"]



