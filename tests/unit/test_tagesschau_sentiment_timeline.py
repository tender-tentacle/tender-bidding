import pytest
from api.v1.company_summary import run_stage2_market_and_news


@pytest.mark.asyncio
async def test_run_stage2_market_and_news_includes_sentiment_and_monthly_timeline():
    """Verify that stage 2 market and news populates articles with sentiment_score and includes a 24-month timeline aggregation."""
    company_name = "Umweltbundesamt"
    res = await run_stage2_market_and_news(company_name)

    assert "tagesschau_news_scan" in res
    scan = res["tagesschau_news_scan"]

    assert "monthly_timeline" in scan
    timeline = scan["monthly_timeline"]
    assert isinstance(timeline, list)
    assert len(timeline) == 24

    for item in timeline:
        assert "year_month" in item
        assert "avg_score" in item
        assert "article_count" in item

    articles = scan.get("articles", [])
    if articles:
        for art in articles:
            assert "sentiment_score" in art
            assert 0 <= art["sentiment_score"] <= 100
            assert "sentiment_label" in art
            assert art["sentiment_label"] in ["Negative", "Neutral", "Positive"]
