"""Service to evaluate pricing quality and manage buyer intelligence cache."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from core.ai_client import get_ai_client
from models.bid import Bid
from models.buyer_cache import BuyerIntelligenceCacheORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def evaluate_pricing_strategy(db: AsyncSession, bid: Bid) -> dict[str, Any]:
    """Evaluate commercial pricing strategy and manage cached buyer intelligence.

    Analyzes historical pricing intelligence and win corridors for the buyer associated
    with the given bid. Inspects the BuyerIntelligenceCacheORM table; if cached data
    is missing or older than 30 days, fetches historical evidence and queries the AI
    pricing strategy prompt, caching the serialized JSON payload for future evaluations.

    Agent Metadata:
      @intent: Provide data-driven commercial pricing guidance and maintain a 30-day buyer intelligence cache.
      @domain: Bidding/Pricing
      @capability: pricing:evaluate_strategy
      @keywords: pricing, strategy, buyer_intelligence, cache, rate_corridor, award_median
      @side_effects: db:mutate (upserts buyer intelligence cache record and commits), network:outbound
      @idempotent: true
      @agent_notes: 30-day cache window per customer_id. Commits session.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async database session.
      @param bid (Bid): The Bid instance containing customer name and financial value context.
      @return (dict[str, Any]): Strategy payload with 'strategy', 'strengths', 'warnings', and 'historical_data'.
      @raises SQLAlchemyError: If cache read/write or commit fails.

    Example:
      >>> strat = await evaluate_pricing_strategy(db, bid)
      >>> print(strat.get("strategy"))
    """
    buyer_name = bid.customer or "Unknown Buyer"
    buyer_name_clean = str(buyer_name).strip()

    # 1. Check cache
    now = datetime.now(UTC)
    cache_record = (
        await db.execute(
            select(BuyerIntelligenceCacheORM).where(BuyerIntelligenceCacheORM.customer_id == buyer_name_clean)
        )
    ).scalar_one_or_none()

    if cache_record and (now - cache_record.created_at.replace(tzinfo=UTC)) < timedelta(days=30):
        try:
            payload = json.loads(cache_record.intelligence_payload)
            if "strategy" in payload:
                return payload
        except json.JSONDecodeError:
            pass

    # 2. Gather context
    snapshot = {
        "buyer_name": buyer_name_clean,
        "current_value": f"€{bid.total_value:,}" if hasattr(bid, "total_value") and bid.total_value else "Unknown",
        "current_ratio": "Unknown",  # The actual tender data will be rendered by the frontend directly for the Current Tender block
    }

    # 3. Call AI to extract historical evidence (crawler)
    ai = get_ai_client()
    historical_data = await ai.extract_historical_evidence(buyer_name_clean)
    snapshot["historical_pricing_payload"] = historical_data

    # 4. Call AI to extract strategy
    result = await ai.extract_bidding_strategy(snapshot)

    # Inject the historic payload so the frontend can display it without hardcoding
    result["historical_data"] = historical_data

    # 4. Cache it
    if cache_record:
        cache_record.intelligence_payload = json.dumps(result)
        cache_record.created_at = now.replace(tzinfo=None)
    else:
        new_record = BuyerIntelligenceCacheORM(
            customer_id=buyer_name_clean, intelligence_payload=json.dumps(result), created_at=now.replace(tzinfo=None)
        )
        db.add(new_record)

    await db.commit()

    return result
