"""Consumer contract test: tender-bidding (consumer) → artificial-intelligence-connector (provider).

Validates API contract for SCARF Model Enrichment:
- POST /api/v1/enrich/scarf
"""

import importlib.util
import sys
from pathlib import Path

ai_ms_dir = Path(__file__).resolve().parents[3] / "artificial-intelligence-connector"
if str(ai_ms_dir) not in sys.path:
    sys.path.insert(0, str(ai_ms_dir))

# Explicitly load core/scarf_extractor.py
spec_scarf = importlib.util.spec_from_file_location("scarf_mod", str(ai_ms_dir / "core" / "scarf_extractor.py"))
scarf_mod = importlib.util.module_from_spec(spec_scarf)
sys.modules["scarf_mod"] = scarf_mod
spec_scarf.loader.exec_module(scarf_mod)

# Explicitly load main.py
spec_main = importlib.util.spec_from_file_location("ai_app_main", str(ai_ms_dir / "main.py"))
ai_app_main = importlib.util.module_from_spec(spec_main)
sys.modules["ai_app_main"] = ai_app_main
spec_main.loader.exec_module(ai_app_main)
ai_app = ai_app_main.app

import pytest
from httpx import ASGITransport, AsyncClient

SCARF_SCORES_FIELDS = {"status", "certainty", "autonomy", "relatedness", "fairness"}
ENRICHED_COMMENT_FIELDS = {"id", "scarf_scores", "primary_threat", "primary_reward", "rationale"}


@pytest.mark.asyncio
async def test_scarf_enrichment_pact_contract(mocker):
    """Verify Pact contract compliance for SCARF enrichment endpoint on AI MS."""
    mock_llm = mocker.patch.object(scarf_mod, "evaluate_scarf_with_llm")
    mock_llm.side_effect = [
        {
            "status": None,
            "certainty": None,
            "autonomy": 20.0,
            "relatedness": None,
            "fairness": 30.0,
            "primary_threat": "autonomy",
            "primary_reward": None,
            "rationale": "Mikromanagement und Frust"
        },
        {
            "status": None,
            "certainty": 80.0,
            "autonomy": None,
            "relatedness": 95.0,
            "fairness": 85.0,
            "primary_threat": None,
            "primary_reward": "relatedness",
            "rationale": "Klasse Zusammenhalt"
        }
    ]

    transport = ASGITransport(app=ai_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "comments": [
                {
                    "id": "comment-pact-1",
                    "title": "Mikromanagement und schlechter Umgang",
                    "content": "Keinerlei Entscheidungsspielraum. Führungskräfte üben ständigen Druck aus.",
                    "rating": 1.0
                },
                {
                    "id": "comment-pact-2",
                    "title": "Klasse Team und faire Gehälter",
                    "content": "Wir halten als Kollegen zusammen und das Gehalt ist marktüblich.",
                    "rating": 4.5
                }
            ]
        }

        response = await client.post("/api/v1/enrich/scarf", json=payload)
        assert response.status_code == 200, response.text

        data = response.json()
        assert "enriched_comments" in data
        enriched_list = data["enriched_comments"]
        assert len(enriched_list) == 2

        for item in enriched_list:
            assert set(item.keys()) >= ENRICHED_COMMENT_FIELDS
            scores = item["scarf_scores"]
            assert set(scores.keys()) == SCARF_SCORES_FIELDS

            # Check that scores are either float or None
            for field in SCARF_SCORES_FIELDS:
                val = scores[field]
                assert val is None or isinstance(val, (int, float))

        # Check comment 1 threat detection
        c1 = next(c for c in enriched_list if c["id"] == "comment-pact-1")
        assert c1["scarf_scores"]["autonomy"] == 20.0

        # Check comment 2 reward detection
        c2 = next(c for c in enriched_list if c["id"] == "comment-pact-2")
        assert c2["scarf_scores"]["relatedness"] == 95.0
