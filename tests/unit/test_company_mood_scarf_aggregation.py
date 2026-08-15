from datetime import UTC, datetime
import pytest
from models.bid import CompanyMood
from api.v1.company_summary import calculate_scarf_monthly_timeline


def test_calculate_scarf_monthly_timeline():
    """Verify that calculate_scarf_monthly_timeline aggregates SCARF scores by month over a 24-month window."""
    moods = [
        CompanyMood(
            company_id="test_comp",
            comment_hash="h1",
            published_date="2026-08-01",
            scarf_status=80.0,
            scarf_certainty=70.0,
            scarf_autonomy=60.0,
            scarf_relatedness=90.0,
            scarf_fairness=75.0,
            scarf_primary_threat=None,
            scarf_primary_reward="relatedness",
            scarf_enriched_at=datetime.now(UTC)
        ),
        CompanyMood(
            company_id="test_comp",
            comment_hash="h2",
            published_date="2026-08-15",
            scarf_status=40.0,
            scarf_certainty=30.0,
            scarf_autonomy=20.0,
            scarf_relatedness=50.0,
            scarf_fairness=25.0,
            scarf_primary_threat="autonomy",
            scarf_primary_reward=None,
            scarf_enriched_at=datetime.now(UTC)
        ),
        CompanyMood(
            company_id="test_comp",
            comment_hash="h3",
            published_date="2026-07-10",
            scarf_status=60.0,
            scarf_certainty=60.0,
            scarf_autonomy=60.0,
            scarf_relatedness=60.0,
            scarf_fairness=60.0,
            scarf_primary_threat=None,
            scarf_primary_reward=None,
            scarf_enriched_at=datetime.now(UTC)
        )
    ]

    timeline = calculate_scarf_monthly_timeline(moods)
    assert isinstance(timeline, list)
    assert len(timeline) == 24

    # 2026-08 item should aggregate h1 and h2
    aug_item = next((item for item in timeline if item["year_month"] == "2026-08"), None)
    assert aug_item is not None
    assert aug_item["comment_count"] == 2
    # Status avg = (80 + 40) / 2 = 60
    assert aug_item["status"] == 60.0
    # Autonomy avg = (60 + 20) / 2 = 40
    assert aug_item["autonomy"] == 40.0
    # Overall score = avg of all 5 dimensions = (60 + 50 + 40 + 70 + 50) / 5 = 54.0
    assert aug_item["avg_score"] == 54.0

    # 2026-07 item should aggregate h3
    jul_item = next((item for item in timeline if item["year_month"] == "2026-07"), None)
    assert jul_item is not None
    assert jul_item["comment_count"] == 1
    assert jul_item["avg_score"] == 60.0
