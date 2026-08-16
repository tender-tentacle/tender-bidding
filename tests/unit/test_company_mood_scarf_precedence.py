"""Unit test: Verify individual comment rating precedence (m.rating) over company overall score (m.overall_score) during SCARF enrichment.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_mood import enrich_company_mood_scarf
from models.bid import CompanyMood


@pytest.mark.asyncio
async def test_scarf_enrichment_uses_individual_comment_rating_over_overall_score():
    """Ensure that a 1.0-star review with company overall_score=4.0 passes rating=1.0 to SCARF extraction, resulting in low SCARF scores."""
    
    # 1. Create a 1.0 star comment where company-wide overall_score is 4.0
    mood = CompanyMood(
        id=101,
        company_id="MHP",
        comment_hash="hash-1star",
        title="Auf dem absteigenden Ast",
        content="Schlechte Führung, Ellenbogenmentalität und Ungleichbehandlung.",
        rating=1.0,           # Individual comment rating (1.0 stars)
        overall_score=4.0,    # Company overall average score (4.0 stars)
    )

    db_mock = AsyncMock()
    # Mock db.execute to return our mood record
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mood]
    res_mock = MagicMock()
    res_mock.scalars.return_value = scalars_mock
    db_mock.execute.return_value = res_mock

    # 2. Track what payload was sent to AI MS or local extractor
    captured_payload = {}

    async def mock_post(url, json=None, **kwargs):
        nonlocal captured_payload
        captured_payload = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "enriched_comments": [
                {
                    "id": "hash-1star",
                    "scarf_scores": {
                        "status": 20.0,
                        "certainty": 20.0,
                        "autonomy": 20.0,
                        "relatedness": 10.0,
                        "fairness": 10.0,
                    },
                    "primary_threat": "fairness",
                    "primary_reward": None,
                    "rationale": "Schwere Kritik bezüglich Führung und Ungleichbehandlung.",
                }
            ]
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await enrich_company_mood_scarf("MHP", db=db_mock)

    # 3. Assertions
    assert res["status"] == "success"
    assert captured_payload is not None
    assert "comments" in captured_payload
    sent_comment = captured_payload["comments"][0]
    
    # CRITICAL ASSERTION: The sent rating MUST be 1.0 (m.rating), NOT 4.0 (m.overall_score)
    assert sent_comment["rating"] == 1.0, f"Expected rating=1.0 from individual comment, got rating={sent_comment['rating']}"
    
    # Assert SCARF status score saved on mood object reflects 1.0 star low score (20.0), NOT high score (80.0)
    assert mood.scarf_status == 20.0
    assert mood.scarf_fairness == 10.0
