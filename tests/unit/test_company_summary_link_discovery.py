from unittest.mock import AsyncMock, patch

import pytest
from api.v1.company_summary import run_stage1_solvency, run_stage2_implicit_needs


@pytest.mark.asyncio
async def test_run_stage1_solvency_fetches_azure_discovered_links():
    """Verify run_stage1_solvency enriches financial_solvency_badges & kununu_sentiment with discovered URLs."""
    mock_db_data = {
        "northdata": None,
        "moods": [],
        "insolvency": None,
    }

    mock_discovery = AsyncMock(return_value={
        "company_name": "Test Company",
        "kununu_url": "https://www.kununu.com/de/test-company",
        "northdata_url": "https://www.northdata.de/Test+Company",
        "newsroom_url": "https://www.test-company.de/presse",
        "financials_url": "https://www.bundesanzeiger.de/test"
    })

    with patch("api.v1.company_summary.get_company_db_data", return_value=mock_db_data):
        with patch("api.v1.company_summary.discover_company_urls_azure", mock_discovery):
            res = await run_stage1_solvency("Test Company", is_aor=False, db=None)

            assert "financial_solvency_badges" in res
            assert res["financial_solvency_badges"].get("northdata_url") == "https://www.northdata.de/Test+Company"
            assert "kununu_sentiment" in res
            assert res["kununu_sentiment"].get("kununu_url") == "https://www.kununu.com/de/test-company"
