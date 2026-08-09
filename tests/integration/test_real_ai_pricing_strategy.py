import core.ai_client
import core.config
import pytest


@pytest.fixture(autouse=True)
def setup_real_ai(monkeypatch):
    # Set config variables to avoid skipping or using the mock
    monkeypatch.setattr(core.config, "MOCK_MODE", False)
    monkeypatch.setattr(core.config, "AI_URL", "http://localhost:8004")
    monkeypatch.setattr(core.ai_client, "MOCK_MODE", False)
    monkeypatch.setattr(core.ai_client, "AI_URL", "http://localhost:8004")


@pytest.mark.asyncio
async def test_real_ai_pricing_strategy():
    client = core.ai_client.RealAIClient()
    snapshot = {
        "buyer_name": "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ) GmbH",
        "current_value": "€12.5M",
        "current_ratio": "30% Price / 70% Quality",
        "historical_pricing_payload": {
            "award_median": "€8.2M",
            "accepted_rate_corridor": "€850 - €1,100 / day",
            "budget_amendment_rate": "15%",
        },
    }

    result = await client.extract_bidding_strategy(snapshot)

    assert isinstance(result, dict)
    print("Pricing strategy result:", result)

    # Verify the structure matches what we expect from the output_structure
    assert "strategy" in result
    assert "strengths" in result
    assert "warnings" in result

    # We expect the AI to return actual strategy text
    assert len(result["strategy"]) > 0
